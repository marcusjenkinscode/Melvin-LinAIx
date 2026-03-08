"""
config.py — Central configuration for Melvin-LinAIx.

All tuneable constants and environment-variable overrides live here so
that no other module hard-codes paths, hostnames, or magic numbers.
"""

from __future__ import annotations

import os
from pathlib import Path

# ── Repository / data root ───────────────────────────────────────────────────
# By default memory banks are created inside the project root.
# Override with the MELVIN_DATA_DIR environment variable.
_HERE = Path(__file__).resolve().parent.parent  # project root
DATA_DIR: Path = Path(os.environ.get("MELVIN_DATA_DIR", str(_HERE)))

# ── Ollama settings ───────────────────────────────────────────────────────────
OLLAMA_HOST: str = os.environ.get("OLLAMA_HOST", "http://localhost")
OLLAMA_PORT: int = int(os.environ.get("OLLAMA_PORT", "11434"))
OLLAMA_BASE_URL: str = f"{OLLAMA_HOST}:{OLLAMA_PORT}"

# ── Default / recommended models ─────────────────────────────────────────────
DEFAULT_MODEL: str = os.environ.get("MELVIN_DEFAULT_MODEL", "llama3.2:3b")
RECOMMENDED_MODELS: list[str] = [
    "llama3.2:3b",
    "qwen2.5:7b",
    "mistral:7b",
    "phi3:mini",
]

# ── Memory bank settings ──────────────────────────────────────────────────────
MAX_ENTRIES_PER_FILE: int = int(os.environ.get("MELVIN_MAX_ENTRIES", "1_000_000"))
MEMORY_BANK_PREFIX: str = "memory-bank-"
INDEX_FILENAME: str = "index.json"
CONVERSATION_FILE_PREFIX: str = "conversations_"
CONVERSATION_FILE_EXT: str = ".json"

# ── Retrieval settings ────────────────────────────────────────────────────────
DEFAULT_HISTORY_WINDOW: int = 10  # last N messages sent as context

# ── Unique-code length ────────────────────────────────────────────────────────
UNIQUE_CODE_LENGTH: int = 6
