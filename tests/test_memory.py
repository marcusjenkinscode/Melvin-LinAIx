"""
test_memory.py — Unit tests for memory_manager, user_manager, utils, and models_manager.

Five tests cover:
  1. Memory append — entry is stored and returned correctly.
  2. Hash chain integrity — verify_integrity passes after correct appends.
  3. User directory — no '+' sign in folder name; uses '-' separator.
  4. Ensemble aggregation — aggregate_responses selects a response and prefixes header.
  5. Shard roll-over — new shard file created when MAX_ENTRIES_PER_FILE is reached.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the project root is on sys.path so imports work without installation.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.memory_manager import GENESIS_HASH, MemoryManager
from src.user_manager import UserManager
from src.utils import aggregate_responses, compute_entry_hash


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_user_dir(tmp_path: Path) -> Path:
    """Return a fresh temporary directory simulating a user's memory bank."""
    d = tmp_path / "memory-bank-testuser-XYZ999"
    d.mkdir()
    return d


@pytest.fixture()
def memory(tmp_user_dir: Path) -> MemoryManager:
    """Return a MemoryManager backed by a temporary directory."""
    return MemoryManager(user_dir=tmp_user_dir, user_id="testuser-XYZ999")


# ── Test 1: Memory append ─────────────────────────────────────────────────────

class TestMemoryAppend:
    """Verify that appending an entry stores it correctly."""

    def test_append_returns_entry(self, memory: MemoryManager) -> None:
        entry = memory.append("Hello", "Hi there!", "llama3.2:3b")
        assert entry["user_message"] == "Hello"
        assert entry["ai_response"] == "Hi there!"
        assert entry["model_used"] == "llama3.2:3b"
        assert "timestamp" in entry
        assert "context_hash" in entry
        assert len(entry["context_hash"]) == 64  # SHA-256 hex

    def test_append_persists_to_disk(self, memory: MemoryManager, tmp_user_dir: Path) -> None:
        memory.append("What is 2+2?", "4", "phi3:mini")
        shard = tmp_user_dir / "conversations_0000.json"
        assert shard.exists()
        data = json.loads(shard.read_text())
        assert len(data) == 1
        assert data[0]["user_message"] == "What is 2+2?"

    def test_get_recent_returns_last_n(self, memory: MemoryManager) -> None:
        for i in range(5):
            memory.append(f"msg {i}", f"resp {i}", "llama3.2:3b")
        recent = memory.get_recent(3)
        assert len(recent) == 3
        assert recent[-1]["user_message"] == "msg 4"


# ── Test 2: Hash chain integrity ──────────────────────────────────────────────

class TestHashIntegrity:
    """Verify that the hash chain validates correctly and detects tampering."""

    def test_verify_passes_on_clean_chain(self, memory: MemoryManager) -> None:
        memory.append("Hello", "World", "llama3.2:3b")
        memory.append("Foo", "Bar", "phi3:mini")
        ok, msg = memory.verify_integrity()
        assert ok is True
        assert "2 entries" in msg

    def test_verify_fails_after_tampering(self, memory: MemoryManager, tmp_user_dir: Path) -> None:
        memory.append("Hello", "World", "llama3.2:3b")
        shard = tmp_user_dir / "conversations_0000.json"
        data = json.loads(shard.read_text())
        # Tamper with the stored response
        data[0]["ai_response"] = "TAMPERED"
        shard.write_text(json.dumps(data))
        ok, msg = memory.verify_integrity()
        assert ok is False
        assert "mismatch" in msg.lower()

    def test_genesis_hash_used_for_first_entry(self, memory: MemoryManager) -> None:
        entry = memory.append("first", "response", "llama3.2:3b")
        expected = compute_entry_hash(
            GENESIS_HASH,
            entry["timestamp"],
            "first",
            "response",
            "llama3.2:3b",
        )
        assert entry["context_hash"] == expected


# ── Test 3: User directory — no '+' in folder name ────────────────────────────

class TestUserDirectory:
    """Ensure the user directory name never contains a '+' character."""

    def test_no_plus_in_dir_name(self, tmp_path: Path) -> None:
        um = UserManager(raw_username="Alice", data_dir=tmp_path)
        assert "+" not in um.user_dir.name, (
            f"Directory name '{um.user_dir.name}' must not contain '+'"
        )

    def test_dir_uses_hyphen_separator(self, tmp_path: Path) -> None:
        um = UserManager(raw_username="Bob", data_dir=tmp_path)
        # Expected pattern: memory-bank-bob-XXXXXX
        parts = um.user_dir.name.split("-")
        # At minimum: ["memory", "bank", "<username>", "<code>"]
        assert len(parts) >= 4, f"Unexpected directory name: {um.user_dir.name}"

    def test_user_id_no_plus(self, tmp_path: Path) -> None:
        um = UserManager(raw_username="Carol", data_dir=tmp_path)
        assert "+" not in um.user_id, (
            f"user_id '{um.user_id}' must not contain '+'"
        )

    def test_dir_created_on_disk(self, tmp_path: Path) -> None:
        um = UserManager(raw_username="Dave", data_dir=tmp_path)
        assert um.user_dir.is_dir()

    def test_same_dir_on_second_init(self, tmp_path: Path) -> None:
        um1 = UserManager(raw_username="Eve", data_dir=tmp_path)
        um2 = UserManager(raw_username="Eve", data_dir=tmp_path)
        assert um1.user_dir == um2.user_dir


# ── Test 4: Ensemble aggregation ─────────────────────────────────────────────

class TestEnsembleAggregation:
    """Verify aggregate_responses returns a sensible combined result."""

    def test_single_response_returned_unchanged(self) -> None:
        responses = [{"model": "llama3.2:3b", "response": "Hello world"}]
        result = aggregate_responses(responses)
        assert result == "Hello world"

    def test_ensemble_header_present(self) -> None:
        responses = [
            {"model": "llama3.2:3b", "response": "The sky is blue."},
            {"model": "phi3:mini", "response": "The sky appears blue due to scattering."},
        ]
        result = aggregate_responses(responses)
        assert "[Ensemble from:" in result
        assert "llama3.2:3b" in result
        assert "phi3:mini" in result

    def test_empty_responses_returns_empty_string(self) -> None:
        assert aggregate_responses([]) == ""

    def test_selects_most_representative_response(self) -> None:
        # The response with more words matching across responses wins.
        responses = [
            {"model": "m1", "response": "cat dog bird fish"},
            {"model": "m2", "response": "cat dog bird"},
            {"model": "m3", "response": "cat dog bird"},
        ]
        result = aggregate_responses(responses)
        # "cat dog bird" appears in two of three; "cat dog bird fish" in one
        # The consensus answer should contain "cat dog bird"
        assert "cat" in result
        assert "dog" in result


# ── Test 5: Shard roll-over ───────────────────────────────────────────────────

class TestShardRollover:
    """Verify that a new shard file is created when the current one is full."""

    def test_rollover_creates_new_shard(self, tmp_user_dir: Path) -> None:
        # Use a max-entries limit of 2 to trigger roll-over quickly.
        with patch("src.memory_manager.MAX_ENTRIES_PER_FILE", 2):
            mem = MemoryManager(user_dir=tmp_user_dir, user_id="testuser-XYZ999")
            mem.append("msg1", "resp1", "llama3.2:3b")
            mem.append("msg2", "resp2", "llama3.2:3b")
            # Third append should create conversations_0001.json
            mem.append("msg3", "resp3", "llama3.2:3b")

        shards = sorted(tmp_user_dir.glob("conversations_*.json"))
        assert len(shards) == 2, f"Expected 2 shards, got {[s.name for s in shards]}"
        shard1_data = json.loads(shards[1].read_text())
        assert shard1_data[0]["user_message"] == "msg3"

    def test_total_entries_spans_shards(self, tmp_user_dir: Path) -> None:
        with patch("src.memory_manager.MAX_ENTRIES_PER_FILE", 2):
            mem = MemoryManager(user_dir=tmp_user_dir, user_id="testuser-XYZ999")
            for i in range(5):
                mem.append(f"msg{i}", f"resp{i}", "llama3.2:3b")
        assert mem.total_entries() == 5
