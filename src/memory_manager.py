"""
memory_manager.py — Append-only JSON "blockchain" conversation store.

Design
------
* One JSON array file per conversation shard, capped at MAX_ENTRIES_PER_FILE
  entries (default 1 000 000).
* Files are named ``conversations_0000.json``, ``conversations_0001.json`` …
* Each entry is a dict::

      {
          "timestamp":       "<ISO-8601 UTC>",
          "user_message":    "<string>",
          "ai_response":     "<string>",
          "model_used":      "<ollama model name>",
          "context_hash":    "<SHA-256 hex>",   # chain hash
          "priority_level":  <int 0–2>,          # 0=normal, 1=priority, 2=low-priority
          "keywords_binary": "<str|None>"        # binary-encoded keywords at heat level 1
      }

* A lightweight ``index.json`` in the user directory tracks::

      {
          "user_id":              "<username-code>",
          "current_file":         "conversations_NNNN.json",
          "total_conversations":  <int>,
          "last_updated":         "<ISO-8601 UTC>",
          ...
      }

* On load the entire chain can be verified with ``verify_integrity()``.

Priority levels
---------------
* ``PRIORITY_NORMAL``  (0) — default entry.
* ``PRIORITY_HIGH``    (1) — user indicated importance (saved near top of search).
* ``PRIORITY_LOW``     (2) — user indicated "it's OK if you can't".  At heat
  level 1 only keyword hashes are stored to save space.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.config import (
    CONVERSATION_FILE_EXT,
    CONVERSATION_FILE_PREFIX,
    MAX_ENTRIES_PER_FILE,
)
from src.utils import compute_entry_hash, encode_keywords_binary, get_timestamp

# Sentinel hash used as the "previous hash" for the very first entry
GENESIS_HASH = "0" * 64

# Priority level constants
PRIORITY_NORMAL: int = 0   # default conversation entry
PRIORITY_HIGH: int = 1     # user marked as important/critical
PRIORITY_LOW: int = 2      # user said "it's OK if you can't"


class MemoryManager:
    """Manages append-only conversation shards for a single user.

    Args:
        user_dir:  Path to the user's memory-bank directory
                   (e.g. ``memory-bank-alice-ABC123/``).
        user_id:   The stable ``<username>-<code>`` identifier.
        user_manager: Optional ``UserManager`` instance for updating the
                   shared ``index.json``.  When provided, the index is kept
                   in sync automatically.
    """

    def __init__(
        self,
        user_dir: Path,
        user_id: str,
        user_manager: Optional[object] = None,
    ) -> None:
        self.user_dir = user_dir
        self.user_id = user_id
        self._um = user_manager  # may be None in isolated tests

        self._current_shard_path: Path = self._resolve_current_shard()

    # ── Public API ────────────────────────────────────────────────────────────

    def append(
        self,
        user_message: str,
        ai_response: str,
        model_used: str,
        priority_level: int = PRIORITY_NORMAL,
        heat_level: int = 5,
    ) -> dict:
        """Append a new conversation entry and return it.

        Automatically rolls over to a new shard file when the current one
        reaches MAX_ENTRIES_PER_FILE entries.

        At *heat_level* 1 and *priority_level* ``PRIORITY_LOW``, only
        binary-encoded keywords are stored in ``keywords_binary`` and the
        full message text is replaced with a compact placeholder to save
        space.

        Args:
            user_message:   The user's raw prompt text.
            ai_response:    The model's reply.
            model_used:     The Ollama model name (e.g. ``"llama3.2:3b"``).
            priority_level: One of ``PRIORITY_NORMAL``, ``PRIORITY_HIGH``, or
                            ``PRIORITY_LOW``.
            heat_level:     Current throttle setting (1–9).  Level 1 enables
                            compact keyword-only storage for low-priority entries.

        Returns:
            The newly created entry dict (including ``context_hash``).
        """
        entries = self._load_shard(self._current_shard_path)

        if len(entries) >= MAX_ENTRIES_PER_FILE:
            self._current_shard_path = self._next_shard()
            entries = []

        previous_hash = entries[-1]["context_hash"] if entries else GENESIS_HASH
        timestamp = get_timestamp()

        # Compact storage for low-priority, low-heat entries (Step 5)
        stored_user = user_message
        stored_ai = ai_response
        keywords_binary: str | None = None
        if heat_level <= 1 and priority_level == PRIORITY_LOW:
            keywords_binary = encode_keywords_binary(user_message)
            stored_user = f"[compact:{len(user_message)}chars]"
            stored_ai = f"[compact:{len(ai_response)}chars]"

        entry = {
            "timestamp": timestamp,
            "user_message": stored_user,
            "ai_response": stored_ai,
            "model_used": model_used,
            "priority_level": priority_level,
            "keywords_binary": keywords_binary,
            "context_hash": compute_entry_hash(
                previous_hash,
                timestamp,
                stored_user,
                stored_ai,
                model_used,
            ),
        }

        entries.append(entry)
        self._save_shard(self._current_shard_path, entries)
        self._sync_index(entries)

        return entry

    def get_recent(self, n: int = 10) -> list[dict]:
        """Return the most recent *n* entries (across the current shard only).

        For a full cross-shard history search use ``search()``.

        Args:
            n: Maximum number of entries to return.

        Returns:
            List of entry dicts, oldest-first.
        """
        entries = self._load_shard(self._current_shard_path)
        return entries[-n:]

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Simple full-text search across ALL shards for *query*.

        Case-insensitive substring match against both ``user_message`` and
        ``ai_response`` fields.

        Args:
            query: Search term.
            limit: Maximum number of results.

        Returns:
            Matching entries (most-recent-first), up to *limit*.
        """
        query_lower = query.lower()
        results: list[dict] = []

        for shard_path in sorted(self._all_shard_paths(), reverse=True):
            for entry in reversed(self._load_shard(shard_path)):
                if (
                    query_lower in entry.get("user_message", "").lower()
                    or query_lower in entry.get("ai_response", "").lower()
                ):
                    results.append(entry)
                    if len(results) >= limit:
                        return results

        return results

    def verify_integrity(self) -> tuple[bool, str]:
        """Verify the hash chain across all shards.

        Walks every entry in order and re-computes the expected
        ``context_hash``.  Returns on the first mismatch.

        Returns:
            A ``(ok, message)`` tuple where ``ok`` is ``True`` iff the
            chain is intact and ``message`` is a human-readable summary.
        """
        previous_hash = GENESIS_HASH
        total = 0

        for shard_path in sorted(self._all_shard_paths()):
            entries = self._load_shard(shard_path)
            for idx, entry in enumerate(entries):
                expected = compute_entry_hash(
                    previous_hash,
                    entry["timestamp"],
                    entry["user_message"],
                    entry["ai_response"],
                    entry["model_used"],
                )
                if entry.get("context_hash") != expected:
                    return (
                        False,
                        f"Hash mismatch at entry {idx} in {shard_path.name}. "
                        f"Expected {expected!r}, got {entry.get('context_hash')!r}.",
                    )
                previous_hash = entry["context_hash"]
                total += 1

        return True, f"Integrity OK — {total} entries verified."

    def total_entries(self) -> int:
        """Return the total number of stored entries across all shards."""
        return sum(
            len(self._load_shard(p)) for p in self._all_shard_paths()
        )

    def get_priority_entries(
        self,
        priority_level: int = PRIORITY_HIGH,
        limit: int = 50,
    ) -> list[dict]:
        """Return entries matching *priority_level*, most-recent-first.

        Args:
            priority_level: Filter by this priority level
                            (``PRIORITY_HIGH`` by default).
            limit:          Maximum number of results.

        Returns:
            List of matching entry dicts, most-recent-first.
        """
        results: list[dict] = []
        for shard_path in sorted(self._all_shard_paths(), reverse=True):
            for entry in reversed(self._load_shard(shard_path)):
                if entry.get("priority_level") == priority_level:
                    results.append(entry)
                    if len(results) >= limit:
                        return results
        return results

    # ── Private helpers ───────────────────────────────────────────────────────

    def _resolve_current_shard(self) -> Path:
        """Determine (or create) the path for the current shard file."""
        existing = sorted(self._all_shard_paths())
        if not existing:
            path = self._shard_path(0)
            self._save_shard(path, [])
            return path
        # Use the last shard unless it is already full
        last = existing[-1]
        if len(self._load_shard(last)) >= MAX_ENTRIES_PER_FILE:
            return self._next_shard()
        return last

    def _next_shard(self) -> Path:
        """Create and return the path for the next shard file."""
        existing = sorted(self._all_shard_paths())
        if not existing:
            next_index = 0
        else:
            last_name = existing[-1].stem  # e.g. "conversations_0002"
            last_index = int(last_name.split("_")[-1])
            next_index = last_index + 1
        path = self._shard_path(next_index)
        self._save_shard(path, [])
        return path

    def _shard_path(self, index: int) -> Path:
        name = f"{CONVERSATION_FILE_PREFIX}{index:04d}{CONVERSATION_FILE_EXT}"
        return self.user_dir / name

    def _all_shard_paths(self) -> list[Path]:
        pattern = f"{CONVERSATION_FILE_PREFIX}*{CONVERSATION_FILE_EXT}"
        return sorted(self.user_dir.glob(pattern))

    @staticmethod
    def _load_shard(path: Path) -> list[dict]:
        """Load a shard JSON file, returning an empty list on any error."""
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    @staticmethod
    def _save_shard(path: Path, entries: list[dict]) -> None:
        """Persist *entries* to *path* atomically-ish via a temp file."""
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(entries, fh, indent=2, ensure_ascii=False)
        tmp.replace(path)

    def _sync_index(self, current_entries: list[dict]) -> None:
        """Update index.json via the UserManager if one is attached."""
        if self._um is None:
            return
        total = self.total_entries()
        self._um.update_index(
            current_file=self._current_shard_path.name,
            total_conversations=total,
        )
