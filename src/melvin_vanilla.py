#!/usr/bin/env python3
"""
melvin_vanilla.py — Vanilla version of Melvin, written from scratch.

This file is the "simple to understand" companion to the Ollama-powered
``melvin.py``.  It does NOT require Ollama or any external AI service.
Instead it uses:

  * A rule-based knowledge lookup against ``skills.txt``
  * Keyword matching for topic detection
  * A JSON memory bank (same format as the Ollama version)
  * The same priority memory, throttle, and XYZ-menu features

How it works (plain English)
-----------------------------
1. The program loads all sections of ``skills.txt`` into memory.
2. When the user types a message, the program searches ``skills.txt``
   for entries whose key or value text contains the user's words.
3. The best matching entries are returned as Melvin's response.
4. Every conversation is saved to a JSON file so that nothing is lost.
5. The user can control verbosity by pressing keys 1–9, and can open
   the control menu with ESC or by typing X, Y, Z, X, Y, Z in order.

Usage
-----
    python src/melvin_vanilla.py --user yourname
    python src/melvin_vanilla.py --user yourname --heat 7
    python src/melvin_vanilla.py --user yourname --history 10
    python src/melvin_vanilla.py --user yourname --search python
    python src/melvin_vanilla.py --user yourname --verify
"""

from __future__ import annotations

# ── Standard library imports ──────────────────────────────────────────────────
import argparse   # parses command-line arguments
import json       # reads and writes JSON files
import sys        # system utilities (exit codes, stderr)
from pathlib import Path  # cross-platform file paths

# ── Make sure the project root is importable ─────────────────────────────────
# This allows the script to be run directly: python src/melvin_vanilla.py
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Project imports ───────────────────────────────────────────────────────────
from src.config import DATA_DIR                   # where memory banks live
from src.memory_manager import (                  # memory / conversation storage
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    MemoryManager,
)
from src.skills_manager import SkillsManager      # loads skills.txt
from src.user_manager import UserManager          # manages per-user directories
from src.utils import get_timestamp               # current UTC timestamp

# ── Constants ─────────────────────────────────────────────────────────────────
MODEL_NAME = "vanilla"          # label used in memory entries
DEFAULT_HEAT = 5                # default throttle level (1 = terse, 9 = verbose)
MAX_RESULTS = 5                 # maximum number of skills results to show
# The six-key escape sequence that opens the interactive menu
_MENU_SEQUENCE = ["x", "y", "z", "x", "y", "z"]


# ─────────────────────────────────────────────────────────────────────────────
# MelvinVanilla — the core chatbot class
# ─────────────────────────────────────────────────────────────────────────────

class MelvinVanilla:
    """A simple, standalone chatbot that answers questions using skills.txt.

    This class contains all the logic needed to:
    - Accept user messages
    - Search the knowledge base
    - Generate a plain-English response
    - Save conversations to a JSON memory bank
    - Manage throttle/heat level
    - Open the interactive control menu

    Args:
        memory:     Initialised MemoryManager for this user.
        skills:     Initialised SkillsManager (loaded from skills.txt).
        heat_level: Starting throttle level (1–9).
        verbose:    If True, print extra debug information.
    """

    def __init__(
        self,
        memory: MemoryManager,
        skills: SkillsManager,
        heat_level: int = DEFAULT_HEAT,
        verbose: bool = False,
    ) -> None:
        # Store the injected dependencies
        self.memory = memory
        self.skills = skills
        self.heat_level = max(1, min(9, heat_level))
        self.verbose = verbose

        # Buffer used to detect the X Y Z X Y Z escape sequence
        self._seq_buffer: list[str] = []

    # ── Answering questions ───────────────────────────────────────────────────

    def answer(self, user_message: str) -> str:
        """Generate a response to *user_message* from the knowledge base.

        Steps:
        1. Search skills.txt for matching entries.
        2. Format the matches based on the current heat level.
        3. Detect priority level (high/low/normal).
        4. Save the exchange to memory.
        5. Return the formatted response.

        Args:
            user_message: Text typed by the user.

        Returns:
            Response string to display to the user.
        """
        # Step 1 — search the knowledge base
        limit = self._results_for_heat()
        results = self.skills.search(user_message, limit=limit)

        if not results:
            # No matching entries — give a polite fallback
            response = self._no_match_response(user_message)
        else:
            # Step 2 — format results based on heat level
            response = self._format_results(results)

        # Step 3 — detect priority
        priority = self._detect_priority(user_message)

        # Step 4 — save to memory
        self.memory.append(
            user_message=user_message,
            ai_response=response,
            model_used=MODEL_NAME,
            priority_level=priority,
            heat_level=self.heat_level,
        )

        return response

    # ── Interactive loop ──────────────────────────────────────────────────────

    def run_interactive(self) -> None:
        """Start the interactive chat loop.

        Throttle shortcuts:
        - Type a single digit 1–9 to change heat level.
        - Type ESC or the sequence x y z x y z to open the control menu.
        - Type /help for all available commands.
        """
        print(
            "\n🤖  Melvin Vanilla — knowledge-base chatbot\n"
            f"    Heat level: {self.heat_level}/9  |  Type /help for commands.\n"
            "    (No Ollama required — answers come from skills.txt)\n"
        )

        # Main loop — keep asking for input until the user quits
        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                # Ctrl-C or Ctrl-D — exit gracefully
                print("\n[Goodbye!]")
                break

            if not user_input:
                continue  # skip blank lines

            # ── Throttle: single digit 1–9 changes heat level ─────────────
            if user_input in "123456789" and len(user_input) == 1:
                self.heat_level = int(user_input)
                desc = self.skills.get_heat_description(self.heat_level)
                print(f"[Heat level → {self.heat_level}: {desc}]")
                continue

            # ── ESC key or literal 'esc' ──────────────────────────────────
            if user_input in ("\x1b", "esc"):
                self._show_control_menu()
                continue

            # ── XYZ sequence check ────────────────────────────────────────
            if self._check_xyz_sequence(user_input):
                self._show_control_menu()
                continue

            # ── Slash commands ────────────────────────────────────────────
            if user_input.startswith("/"):
                self._handle_command(user_input)
                continue

            # ── Normal question — answer and print ────────────────────────
            print("Melvin: ", end="", flush=True)
            response = self.answer(user_input)
            print(response)
            print()

    # ── Private helpers — formatting ──────────────────────────────────────────

    def _results_for_heat(self) -> int:
        """Return the number of results to show based on the heat level.

        Lower heat = fewer results (more compact).
        Higher heat = more results (more detailed).
        """
        # Heat 1 → 1 result, heat 9 → 9 results
        return self.heat_level

    def _format_results(self, results: list[dict]) -> str:
        """Turn a list of skill search results into a human-readable response.

        The verbosity depends on the current heat level:
        - Heat 1–3: Just the value of the first result.
        - Heat 4–6: Key + value for each result.
        - Heat 7–9: Section, key, value, and a separator for each result.

        Args:
            results: List of dicts with keys 'section', 'key', 'value'.

        Returns:
            Formatted response string.
        """
        lines: list[str] = []

        for r in results:
            section = r["section"]
            key = r["key"]
            value = r["value"]

            if self.heat_level <= 3:
                # Terse — just the value
                lines.append(value)
            elif self.heat_level <= 6:
                # Moderate — key and value
                lines.append(f"{key}: {value}")
            else:
                # Verbose — full detail with section header
                lines.append(f"[{section}] {key}")
                lines.append(f"  {value}")
                lines.append("")  # blank line between entries

        return "\n".join(lines).strip()

    def _no_match_response(self, message: str) -> str:
        """Generate a fallback response when no skills match *message*.

        Args:
            message: The user's original message.

        Returns:
            A polite, informative fallback string.
        """
        return (
            f"I don't have a specific entry for '{message}' in my knowledge base.\n"
            "Try searching for a keyword, or ask about:\n"
            "  • Programming languages (python, bash, javascript, etc.)\n"
            "  • Punctuation and writing styles\n"
            "  • Mathematics history\n"
            "  • Astronomy and planets\n"
            "  • Core directives and level system\n"
            "Type /help for available commands."
        )

    # ── Private helpers — priority detection ──────────────────────────────────

    def _detect_priority(self, message: str) -> int:
        """Return the priority level of *message*.

        Checks the message text against priority keywords loaded from
        skills.txt.  Returns PRIORITY_HIGH, PRIORITY_LOW, or PRIORITY_NORMAL.

        Args:
            message: User's message text.

        Returns:
            One of the PRIORITY_* constants from memory_manager.
        """
        msg_lower = message.lower()

        # Check for high-priority keywords
        for phrase in self.skills.get_priority_keywords():
            if phrase in msg_lower:
                return PRIORITY_HIGH

        # Check for low-priority phrases
        for phrase in self.skills.get_low_priority_phrases():
            if phrase in msg_lower:
                return PRIORITY_LOW

        return PRIORITY_NORMAL

    # ── Private helpers — XYZ escape sequence ────────────────────────────────

    def _check_xyz_sequence(self, token: str) -> bool:
        """Check whether *token* advances or completes the X Y Z sequence.

        The sequence is x y z x y z entered as six consecutive inputs.
        Any input that doesn't match the expected next character resets
        the buffer.

        Args:
            token: Latest user input.

        Returns:
            True when the full sequence has just been completed.
        """
        expected = _MENU_SEQUENCE[len(self._seq_buffer)]
        if token.lower() == expected:
            self._seq_buffer.append(token.lower())
            if self._seq_buffer == _MENU_SEQUENCE:
                self._seq_buffer = []
                return True
        else:
            self._seq_buffer = []  # reset on mismatch
        return False

    # ── Interactive control menu ──────────────────────────────────────────────

    def _show_control_menu(self) -> None:
        """Display the interactive control menu and handle the user's choice."""
        print(
            "\n╔══════════════════════════════════════╗\n"
            "║  Melvin Vanilla — Control Menu       ║\n"
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
            desc = self.skills.get_heat_description(self.heat_level)
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

    # ── Slash-command dispatcher ──────────────────────────────────────────────

    def _handle_command(self, cmd: str) -> None:
        """Handle a / command typed by the user.

        Available commands:
        /help              — list available commands
        /quit  /exit       — end the session
        /history [N]       — show last N conversations (default 5)
        /search <term>     — search conversation memory
        /verify            — verify hash-chain integrity
        /heat [1-9]        — get or set the throttle level
        /priority          — show high-priority memories
        /skills <query>    — search the skills knowledge base directly

        Args:
            cmd: Full command string including the leading slash.
        """
        # Split into the verb (/help) and any argument after it
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
                "  /history [N]       — Show last N conversations (default 5)\n"
                "  /search <term>     — Search conversation memory\n"
                "  /skills <query>    — Search the skills knowledge base\n"
                "  /verify            — Verify memory hash chain\n"
                "  /heat [1-9]        — Get or set the heat/throttle level\n"
                "  /priority          — Show recent high-priority memories\n"
                "\nShortcuts:\n"
                "  1–9  (alone)       — Change heat level instantly\n"
                "  ESC  or  x y z x y z  — Open interactive control menu\n"
            )

        elif verb == "/history":
            # Show the last N conversation entries
            n = int(arg) if arg.isdigit() else 5
            entries = self.memory.get_recent(n)
            if not entries:
                print("[No history yet]")
            for e in entries:
                print(f"\n[{e['timestamp']}]")
                print(f"  You:    {e['user_message']}")
                print(f"  Melvin: {e['ai_response'][:120]}...")  # truncate long replies

        elif verb == "/search":
            if not arg:
                print("[Usage: /search <term>]")
                return
            results = self.memory.search(arg)
            if not results:
                print(f"[No conversation history matches '{arg}']")
            for e in results:
                print(f"\n[{e['timestamp']}] You: {e['user_message']}")

        elif verb == "/skills":
            # Search the skills knowledge base directly
            if not arg:
                print("[Usage: /skills <query>]")
                return
            results = self.skills.search(arg, limit=5)
            if not results:
                print(f"[No skills entries match '{arg}']")
            for r in results:
                print(f"\n[{r['section']}] {r['key']}:")
                print(f"  {r['value']}")

        elif verb == "/verify":
            ok, msg = self.memory.verify_integrity()
            icon = "✓" if ok else "✗"
            print(f"[{icon}] {msg}")

        elif verb == "/heat":
            if arg.isdigit() and 1 <= int(arg) <= 9:
                self.heat_level = int(arg)
                desc = self.skills.get_heat_description(self.heat_level)
                print(f"[Heat level set to {self.heat_level}: {desc}]")
            else:
                desc = self.skills.get_heat_description(self.heat_level)
                print(f"[Current heat level: {self.heat_level}/9 — {desc}]")
                print("[Usage: /heat <1-9>]")

        elif verb == "/priority":
            entries = self.memory.get_priority_entries(PRIORITY_HIGH)
            if not entries:
                print("[No high-priority memories stored yet]")
            else:
                print(f"\n[{len(entries)} high-priority entries]\n")
                for e in entries:
                    print(f"  [{e['timestamp']}] You: {e['user_message']}")

        else:
            print(f"[Unknown command: {verb}. Type /help for options.]")


# ─────────────────────────────────────────────────────────────────────────────
# CLI argument parser
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Construct and return the argument parser for melvin_vanilla.py."""
    parser = argparse.ArgumentParser(
        prog="melvin_vanilla",
        description=(
            "Melvin Vanilla — standalone AI chatbot.\n"
            "No Ollama required.  Answers come from skills.txt."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/melvin_vanilla.py --user alice
  python src/melvin_vanilla.py --user alice --heat 7
  python src/melvin_vanilla.py --user alice --history 10
  python src/melvin_vanilla.py --user alice --search python
  python src/melvin_vanilla.py --user alice --verify
        """,
    )

    parser.add_argument(
        "--user",
        metavar="NAME",
        default="default",
        help="Your identity name (default: 'default').",
    )
    parser.add_argument(
        "--heat",
        metavar="N",
        type=int,
        default=DEFAULT_HEAT,
        choices=range(1, 10),
        help="Initial heat/throttle level 1–9 (default: 5).",
    )
    parser.add_argument(
        "--history",
        metavar="N",
        type=int,
        help="Print last N conversation entries and exit.",
    )
    parser.add_argument(
        "--search",
        metavar="TERM",
        help="Search conversation memory for TERM and exit.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify memory hash-chain integrity and exit.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print extra debug information.",
    )

    return parser


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """Parse arguments and start the appropriate mode.

    Returns:
        Exit code (0 = success, non-zero = error).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # ── Set up user directory and memory ─────────────────────────────────────
    user_mgr = UserManager(raw_username=args.user)
    memory = MemoryManager(
        user_dir=user_mgr.user_dir,
        user_id=user_mgr.user_id,
        user_manager=user_mgr,
    )

    if args.verbose:
        print(f"[User dir] {user_mgr.user_dir}", file=sys.stderr)

    # ── Load the skills knowledge base ────────────────────────────────────────
    skills = SkillsManager()

    if args.verbose:
        total_sections = len(skills.sections)
        total_entries = sum(len(v) for v in skills.sections.values())
        print(
            f"[Skills] {total_sections} sections, {total_entries} entries loaded.",
            file=sys.stderr,
        )

    # ── --verify ──────────────────────────────────────────────────────────────
    if args.verify:
        ok, msg = memory.verify_integrity()
        icon = "✓" if ok else "✗"
        print(f"[{icon}] {msg}")
        return 0 if ok else 1

    # ── --history ─────────────────────────────────────────────────────────────
    if args.history is not None:
        entries = memory.get_recent(args.history)
        if not entries:
            print("[No history yet for this user]")
        for e in entries:
            print(f"\n[{e['timestamp']}]")
            print(f"  You:    {e['user_message']}")
            print(f"  Melvin: {e['ai_response']}")
        return 0

    # ── --search ──────────────────────────────────────────────────────────────
    if args.search:
        results = memory.search(args.search)
        if not results:
            print(f"[No results for '{args.search}']")
        for e in results:
            print(f"\n[{e['timestamp']}] You: {e['user_message']}")
        return 0

    # ── Interactive chat ──────────────────────────────────────────────────────
    bot = MelvinVanilla(
        memory=memory,
        skills=skills,
        heat_level=args.heat,
        verbose=args.verbose,
    )
    bot.run_interactive()
    return 0


if __name__ == "__main__":
    sys.exit(main())
