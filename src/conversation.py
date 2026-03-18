"""
conversation.py — Interactive chat loop and multi-model querying.

Responsibilities
----------------
* Accept a user prompt.
* Build a context window from recent conversation history.
* Query one or more Ollama models (sequential or parallel).
* Persist the interaction via MemoryManager.
* Return / display the aggregated response.

Throttle / heat level
---------------------
The session maintains a *heat_level* (1–9, default 5) that controls
response verbosity and memory compactness:

* Press **1–9** at the ``You:`` prompt to change the heat level instantly.
* Press **ESC** at the prompt, or type the six-key sequence ``X Y Z X Y Z``
  (each as a separate input), to open the interactive control menu.

Priority detection
------------------
Melvin scans each message for priority keywords defined in
``skills.txt [CORE_DIRECTIVES]`` and auto-classifies entries as
``PRIORITY_HIGH``, ``PRIORITY_LOW``, or ``PRIORITY_NORMAL``.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from src.config import DEFAULT_HISTORY_WINDOW
from src.memory_manager import PRIORITY_HIGH, PRIORITY_LOW, PRIORITY_NORMAL, MemoryManager
from src.models_manager import ModelsManager
from src.skills_manager import SkillsManager
from src.utils import aggregate_responses

# The six-key escape sequence that opens the interactive menu (Step 3)
_MENU_SEQUENCE = ["x", "y", "z", "x", "y", "z"]


class ConversationSession:
    """One interactive session for a single user.

    Args:
        memory:         An initialised ``MemoryManager`` for this user.
        models_mgr:     An initialised ``ModelsManager``.
        model_names:    List of Ollama model names to use.  More than one
                        triggers ensemble mode.
        history_window: Number of past exchanges included in context.
        verbose:        Print extra information when ``True``.
    """

    def __init__(
        self,
        memory: MemoryManager,
        models_mgr: ModelsManager,
        model_names: list[str],
        history_window: int = DEFAULT_HISTORY_WINDOW,
        verbose: bool = False,
        heat_level: int = 5,
        skills_mgr: Optional[SkillsManager] = None,
    ) -> None:
        self.memory = memory
        self.models_mgr = models_mgr
        self.model_names = model_names
        self.history_window = history_window
        self.verbose = verbose
        self.heat_level: int = max(1, min(9, heat_level))
        self._skills = skills_mgr or SkillsManager()
        # Rolling buffer for the XYZ escape sequence detector (Step 3)
        self._seq_buffer: list[str] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def chat(self, user_message: str) -> str:
        """Process *user_message*, store the exchange, and return the reply.

        The priority level is auto-detected from the message text using the
        keyword lists defined in ``skills.txt [CORE_DIRECTIVES]``.

        Args:
            user_message: Raw text input from the user.

        Returns:
            The model(s)' response as a single string.
        """
        messages = self._build_messages(user_message)

        if len(self.model_names) == 1:
            response_text = self._query_single(self.model_names[0], messages)
            model_label = self.model_names[0]
        else:
            responses = self._query_ensemble(messages)
            response_text = aggregate_responses(responses)
            model_label = ",".join(self.model_names)

        priority = self._detect_priority(user_message)

        # Persist
        self.memory.append(
            user_message=user_message,
            ai_response=response_text,
            model_used=model_label,
            priority_level=priority,
            heat_level=self.heat_level,
        )

        return response_text

    def run_interactive(self) -> None:
        """Start an interactive REPL loop until the user exits.

        Special commands
        ~~~~~~~~~~~~~~~~
        ``/quit`` or ``/exit``      — End the session.
        ``/history [N]``            — Print the last N entries (default 5).
        ``/search <term>``          — Full-text search across all history.
        ``/verify``                 — Run hash-chain integrity check.
        ``/models``                 — Show models in use.
        ``/heat [1-9]``             — Get or set the throttle / heat level.
        ``/priority``               — Show recent high-priority entries.
        ``/help``                   — List available commands.

        Throttle shortcuts
        ~~~~~~~~~~~~~~~~~~
        Typing a single digit (1–9) at the prompt changes the heat level.
        Typing ESC, or the sequence ``x y z x y z`` (each on its own line),
        opens the interactive control menu.
        """
        models_str = ", ".join(self.model_names)
        print(f"\n🤖  Melvin-LinAIx — model(s): {models_str}")
        print(f"    Heat level: {self.heat_level}/9  |  Type /help for commands.\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[Goodbye!]")
                break

            if not user_input:
                continue

            # ── Throttle: single digit 1–9 changes heat level (Step 3) ───────
            if user_input in "123456789" and len(user_input) == 1:
                self.heat_level = int(user_input)
                desc = self._skills.get_heat_description(self.heat_level)
                print(f"[Heat level set to {self.heat_level}: {desc}]")
                continue

            # ── ESC key detection ─────────────────────────────────────────────
            if user_input == "\x1b" or user_input.lower() == "esc":
                self._show_control_menu()
                continue

            # ── XYZ sequence detection (Step 3) ───────────────────────────────
            if self._check_xyz_sequence(user_input):
                self._show_control_menu()
                continue

            # ── Built-in slash commands ───────────────────────────────────────
            if user_input.startswith("/"):
                self._handle_command(user_input)
                continue

            print("Melvin: ", end="", flush=True)
            response = self.chat(user_input)
            print(response)
            print()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_messages(self, user_message: str) -> list[dict]:
        """Build the OpenAI-style message list for the current turn.

        Includes up to ``history_window`` previous exchanges as context.
        """
        messages: list[dict] = [
            {
                "role": "system",
                "content": (
                    "You are Melvin, a helpful, concise, and honest AI assistant "
                    "running entirely on the user's local machine. "
                    "You have no internet access. Answer accurately and helpfully."
                ),
            }
        ]

        for entry in self.memory.get_recent(self.history_window):
            messages.append({"role": "user", "content": entry["user_message"]})
            messages.append({"role": "assistant", "content": entry["ai_response"]})

        messages.append({"role": "user", "content": user_message})
        return messages

    def _query_single(self, model_name: str, messages: list[dict]) -> str:
        """Query one model and return its raw response string."""
        if self.verbose:
            print(f"  [querying {model_name}]", file=sys.stderr)
        try:
            return self.models_mgr.query(model_name, messages)
        except Exception as exc:
            return f"[ERROR querying {model_name}: {exc}]"

    def _query_ensemble(self, messages: list[dict]) -> list[dict[str, Any]]:
        """Query all models in parallel and collect their responses."""
        results: list[dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=len(self.model_names)) as executor:
            future_to_model = {
                executor.submit(self._query_single, name, messages): name
                for name in self.model_names
            }
            for future in as_completed(future_to_model):
                model = future_to_model[future]
                try:
                    text = future.result()
                except Exception as exc:
                    text = f"[ERROR: {exc}]"
                results.append({"model": model, "response": text})

        return results

    def _detect_priority(self, message: str) -> int:
        """Classify *message* as high, low, or normal priority.

        Uses keyword lists from ``skills.txt [CORE_DIRECTIVES]``.

        Returns:
            ``PRIORITY_HIGH``, ``PRIORITY_LOW``, or ``PRIORITY_NORMAL``.
        """
        message_lower = message.lower()
        for phrase in self._skills.get_priority_keywords():
            if phrase in message_lower:
                return PRIORITY_HIGH
        for phrase in self._skills.get_low_priority_phrases():
            if phrase in message_lower:
                return PRIORITY_LOW
        return PRIORITY_NORMAL

    def _check_xyz_sequence(self, token: str) -> bool:
        """Update the XYZ escape-sequence buffer and return True when matched.

        The sequence is ``x y z x y z`` entered as six consecutive single-
        character inputs.  The buffer is reset on any non-matching input.

        Args:
            token: The latest user input token.

        Returns:
            ``True`` when the full sequence has just been completed.
        """
        expected = _MENU_SEQUENCE[len(self._seq_buffer)]
        if token.lower() == expected:
            self._seq_buffer.append(token.lower())
            if self._seq_buffer == _MENU_SEQUENCE:
                self._seq_buffer = []
                return True
        else:
            self._seq_buffer = []
        return False

    def _show_control_menu(self) -> None:
        """Display the interactive control menu (Step 3)."""
        print(
            "\n╔══════════════════════════════════════╗\n"
            "║  Melvin Interactive Control Menu     ║\n"
            "╠══════════════════════════════════════╣\n"
            f"║  Current heat level: {self.heat_level}/9              ║\n"
            "║                                      ║\n"
            "║  [1-9]  Set heat level               ║\n"
            "║  [h]    Show /help                   ║\n"
            "║  [p]    Show priority memories       ║\n"
            "║  [v]    Verify hash chain            ║\n"
            "║  [q]    Quit                         ║\n"
            "╚══════════════════════════════════════╝"
        )
        try:
            choice = input("Menu choice: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return

        if choice in "123456789" and len(choice) == 1:
            self.heat_level = int(choice)
            desc = self._skills.get_heat_description(self.heat_level)
            print(f"[Heat level set to {self.heat_level}: {desc}]")
        elif choice == "h":
            self._handle_command("/help")
        elif choice == "p":
            self._handle_command("/priority")
        elif choice == "v":
            self._handle_command("/verify")
        elif choice == "q":
            print("[Goodbye!]")
            raise SystemExit(0)
        else:
            print("[Menu closed]")

    def _handle_command(self, cmd: str) -> None:
        """Dispatch a slash-command entered by the user."""
        parts = cmd.split(maxsplit=1)
        verb = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if verb in ("/quit", "/exit"):
            print("[Goodbye!]")
            raise SystemExit(0)

        elif verb == "/help":
            print(
                "\nAvailable commands:\n"
                "  /help              — Show this message\n"
                "  /quit  /exit       — End the session\n"
                "  /history [N]       — Show last N exchanges (default 5)\n"
                "  /search <term>     — Search conversation history\n"
                "  /verify            — Verify memory hash chain\n"
                "  /models            — Show active model(s)\n"
                "  /heat [1-9]        — Get or set the heat/throttle level\n"
                "  /priority          — Show recent high-priority memories\n"
                "\nShortcuts:\n"
                "  1–9  (alone)       — Change heat level instantly\n"
                "  ESC  or  x y z x y z  — Open interactive control menu\n"
            )

        elif verb == "/history":
            n = int(arg) if arg.isdigit() else 5
            entries = self.memory.get_recent(n)
            if not entries:
                print("[No history yet]")
            for e in entries:
                print(f"\n[{e['timestamp']}] ({e['model_used']})")
                print(f"  You:    {e['user_message']}")
                print(f"  Melvin: {e['ai_response']}")

        elif verb == "/search":
            if not arg:
                print("[Usage: /search <term>]")
                return
            results = self.memory.search(arg)
            if not results:
                print(f"[No results for '{arg}']")
            for e in results:
                print(f"\n[{e['timestamp']}] ({e['model_used']})")
                print(f"  You:    {e['user_message']}")
                print(f"  Melvin: {e['ai_response']}")

        elif verb == "/verify":
            ok, msg = self.memory.verify_integrity()
            icon = "✓" if ok else "✗"
            print(f"[{icon}] {msg}")

        elif verb == "/models":
            print(f"Active models: {', '.join(self.model_names)}")

        elif verb == "/heat":
            if arg.isdigit() and 1 <= int(arg) <= 9:
                self.heat_level = int(arg)
                desc = self._skills.get_heat_description(self.heat_level)
                print(f"[Heat level set to {self.heat_level}: {desc}]")
            else:
                desc = self._skills.get_heat_description(self.heat_level)
                print(f"[Current heat level: {self.heat_level}/9 — {desc}]")
                print("[Usage: /heat <1-9>]")

        elif verb == "/priority":
            entries = self.memory.get_priority_entries(PRIORITY_HIGH)
            if not entries:
                print("[No high-priority memories stored yet]")
            else:
                print(f"\n[{len(entries)} high-priority memory entries]\n")
                for e in entries:
                    print(f"  [{e['timestamp']}] You: {e['user_message']}")

        else:
            print(f"[Unknown command: {verb}. Type /help for options.]")
