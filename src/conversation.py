"""
conversation.py — Interactive chat loop and multi-model querying.

Responsibilities
----------------
* Accept a user prompt.
* Build a context window from recent conversation history.
* Query one or more Ollama models (sequential or parallel).
* Persist the interaction via MemoryManager.
* Return / display the aggregated response.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from src.config import DEFAULT_HISTORY_WINDOW
from src.memory_manager import MemoryManager
from src.models_manager import ModelsManager
from src.utils import aggregate_responses


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
    ) -> None:
        self.memory = memory
        self.models_mgr = models_mgr
        self.model_names = model_names
        self.history_window = history_window
        self.verbose = verbose

    # ── Public API ────────────────────────────────────────────────────────────

    def chat(self, user_message: str) -> str:
        """Process *user_message*, store the exchange, and return the reply.

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

        # Persist
        self.memory.append(
            user_message=user_message,
            ai_response=response_text,
            model_used=model_label,
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
        ``/help``                   — List available commands.
        """
        models_str = ", ".join(self.model_names)
        print(f"\n🤖  Melvin-LinAIx — model(s): {models_str}")
        print("    Type /help for commands, or just chat!\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[Goodbye!]")
                break

            if not user_input:
                continue

            # ── Built-in commands ──────────────────────────────────────────
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

        else:
            print(f"[Unknown command: {verb}. Type /help for options.]")
