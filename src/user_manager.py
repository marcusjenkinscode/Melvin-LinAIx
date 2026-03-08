"""
user_manager.py — User identity and memory-bank directory management.

Each user gets a unique directory named:
    memory-bank-<sanitized_username>-<6-char-code>/

An ``index.json`` file inside tracks metadata.  If the directory
already exists (on a subsequent run) the manager re-reads the stored
unique code from ``index.json`` so the path is stable across sessions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.config import (
    DATA_DIR,
    INDEX_FILENAME,
    MEMORY_BANK_PREFIX,
    UNIQUE_CODE_LENGTH,
)
from src.utils import generate_unique_code, get_timestamp, sanitize_username


class UserManager:
    """Manage per-user identity and memory-bank directory creation.

    Attributes:
        raw_username:       The original, unsanitized name.
        username:           Sanitized version used in the directory name.
        unique_code:        6-character alphanumeric code for this user.
        user_dir:           ``Path`` to the user's memory-bank directory.
        user_id:            Combined identifier ``username-unique_code``.
    """

    def __init__(self, raw_username: str, data_dir: Optional[Path] = None) -> None:
        """Initialise (or load) a user identity.

        If a matching directory already exists the stored unique code is
        loaded from ``index.json``; otherwise a new directory and code
        are created.

        Args:
            raw_username: Name as supplied by the user (e.g. from CLI).
            data_dir:     Root directory for all memory banks.
                          Defaults to ``config.DATA_DIR``.
        """
        self.raw_username = raw_username
        self.username: str = sanitize_username(raw_username)
        self._data_dir: Path = data_dir or DATA_DIR

        existing_dir = self._find_existing_dir()
        if existing_dir is not None:
            self.user_dir: Path = existing_dir
            index = self._load_index()
            self.unique_code: str = index.get("unique_code", self._extract_code_from_dir(existing_dir))
        else:
            self.unique_code = generate_unique_code(UNIQUE_CODE_LENGTH)
            self.user_dir = self._data_dir / f"{MEMORY_BANK_PREFIX}{self.username}-{self.unique_code}"
            self.user_dir.mkdir(parents=True, exist_ok=True)
            self._write_index(total_conversations=0, current_file="conversations_0000.json")

    # ── Public helpers ────────────────────────────────────────────────────────

    @property
    def user_id(self) -> str:
        """Stable user identifier: ``<username>-<unique_code>``."""
        return f"{self.username}-{self.unique_code}"

    def get_index(self) -> dict:
        """Return the parsed contents of the user's ``index.json``."""
        return self._load_index()

    def update_index(self, **kwargs: object) -> None:
        """Merge *kwargs* into the index and persist it.

        Always refreshes ``last_updated`` to the current UTC time.
        """
        index = self._load_index()
        index.update(kwargs)
        index["last_updated"] = get_timestamp()
        self._write_index_raw(index)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _find_existing_dir(self) -> Optional[Path]:
        """Scan DATA_DIR for an existing directory for this username."""
        prefix = f"{MEMORY_BANK_PREFIX}{self.username}-"
        for candidate in self._data_dir.iterdir():
            if candidate.is_dir() and candidate.name.startswith(prefix):
                return candidate
        return None

    def _extract_code_from_dir(self, directory: Path) -> str:
        """Extract the unique code from a directory name."""
        # e.g. memory-bank-alice-ABC123 → strip the known prefix, take last 6 chars
        prefix = f"{MEMORY_BANK_PREFIX}{self.username}-"
        name = directory.name
        if name.startswith(prefix):
            return name[len(prefix):]
        return generate_unique_code(UNIQUE_CODE_LENGTH)

    def _load_index(self) -> dict:
        """Read and parse ``index.json``, returning an empty dict on error."""
        index_path = self.user_dir / INDEX_FILENAME
        if not index_path.exists():
            return {}
        try:
            with index_path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_index(self, total_conversations: int, current_file: str) -> None:
        """Create a fresh ``index.json`` with the provided values."""
        data = {
            "user_id": self.user_id,
            "username": self.username,
            "unique_code": self.unique_code,
            "current_file": current_file,
            "total_conversations": total_conversations,
            "last_updated": get_timestamp(),
        }
        self._write_index_raw(data)

    def _write_index_raw(self, data: dict) -> None:
        """Serialize *data* to ``index.json``."""
        index_path = self.user_dir / INDEX_FILENAME
        with index_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
