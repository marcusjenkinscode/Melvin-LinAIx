#!/usr/bin/env python3
"""
melvin.py — CLI entry point for Melvin-LinAIx.

Usage examples
--------------
    python src/melvin.py --user alice
    python src/melvin.py --user alice --model llama3.2:3b
    python src/melvin.py --user alice --model all
    python src/melvin.py --user alice --model "llama3.2:3b,phi3:mini"
    python src/melvin.py --list-models
    python src/melvin.py --pull llama3.2:3b
    python src/melvin.py --verify --user alice
    python src/melvin.py --history 10 --user alice

Once the ``melvin`` alias is registered via ``setup.sh``, replace
``python src/melvin.py`` with ``melvin``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running directly from the repo root without installing the package.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.config import DEFAULT_MODEL
from src.conversation import ConversationSession
from src.memory_manager import MemoryManager
from src.models_manager import ModelsManager
from src.user_manager import UserManager


def build_parser() -> argparse.ArgumentParser:
    """Construct and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="melvin",
        description="Melvin-LinAIx — local AI agent powered by Ollama.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  melvin --user alice
  melvin --user alice --model all
  melvin --user alice --model llama3.2:3b
  melvin --list-models
  melvin --pull llama3.2:3b
  melvin --verify --user alice
  melvin --history 5 --user alice
        """,
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    parser.add_argument(
        "--user",
        metavar="NAME",
        default="default",
        help="Your name / identity (default: 'default').",
    )

    # ── Model selection ───────────────────────────────────────────────────────
    parser.add_argument(
        "--model",
        metavar="MODEL",
        default=DEFAULT_MODEL,
        help=(
            "Model to use.  Pass 'all' for ensemble mode, a comma-separated "
            f"list for multiple, or a single model name.  Default: {DEFAULT_MODEL}"
        ),
    )

    # ── Utility flags ─────────────────────────────────────────────────────────
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List all locally installed Ollama models and exit.",
    )
    parser.add_argument(
        "--pull",
        metavar="MODEL",
        help="Pull (download) a model from the Ollama registry and exit.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify memory hash-chain integrity for --user and exit.",
    )
    parser.add_argument(
        "--history",
        metavar="N",
        type=int,
        help="Print the last N conversation entries for --user and exit.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print extra debug information.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate handler.

    Returns:
        Exit code (0 = success, non-zero = error).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    models_mgr = ModelsManager()

    # ── --list-models ─────────────────────────────────────────────────────────
    if args.list_models:
        if not models_mgr.is_ollama_available():
            print("ERROR: Ollama is not running. Start it with: ollama serve", file=sys.stderr)
            return 1
        installed = models_mgr.list_installed()
        if not installed:
            print("No models installed. Pull one with: melvin --pull llama3.2:3b")
        else:
            print("Installed models:")
            for name in installed:
                print(f"  • {name}")
        return 0

    # ── --pull ────────────────────────────────────────────────────────────────
    if args.pull:
        try:
            models_mgr.pull(args.pull)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        return 0

    # ── All other commands require Ollama to be running ───────────────────────
    if not models_mgr.is_ollama_available():
        print(
            "ERROR: Ollama is not running or not reachable.\n"
            "  Start it with:  ollama serve\n"
            "  Then try again.",
            file=sys.stderr,
        )
        return 1

    # ── Resolve user & memory ─────────────────────────────────────────────────
    user_mgr = UserManager(raw_username=args.user)
    memory = MemoryManager(
        user_dir=user_mgr.user_dir,
        user_id=user_mgr.user_id,
        user_manager=user_mgr,
    )

    if args.verbose:
        print(f"[User dir] {user_mgr.user_dir}", file=sys.stderr)

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
            print(f"\n[{e['timestamp']}] ({e['model_used']})")
            print(f"  You:    {e['user_message']}")
            print(f"  Melvin: {e['ai_response']}")
        return 0

    # ── Interactive chat ──────────────────────────────────────────────────────
    try:
        model_names = models_mgr.select_model(args.model)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    session = ConversationSession(
        memory=memory,
        models_mgr=models_mgr,
        model_names=model_names,
        verbose=args.verbose,
    )
    session.run_interactive()
    return 0


if __name__ == "__main__":
    sys.exit(main())
