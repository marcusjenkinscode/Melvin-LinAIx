"""
test_skills_and_vanilla.py — Tests for skills_manager, priority memory,
throttle/heat level, and the vanilla chatbot.

All tests run offline — no Ollama connection required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.memory_manager import (
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    MemoryManager,
)
from src.melvin_vanilla import MelvinVanilla
from src.skills_manager import SkillsManager
from src.utils import decode_keywords_binary, encode_keywords_binary


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def skills() -> SkillsManager:
    """Return a SkillsManager loaded from the real skills.txt."""
    return SkillsManager()


@pytest.fixture()
def tmp_memory(tmp_path: Path) -> MemoryManager:
    """Return a MemoryManager backed by a temporary directory."""
    d = tmp_path / "memory-bank-testuser-TST000"
    d.mkdir()
    return MemoryManager(user_dir=d, user_id="testuser-TST000")


@pytest.fixture()
def vanilla(tmp_memory: MemoryManager, skills: SkillsManager) -> MelvinVanilla:
    """Return a MelvinVanilla instance using a temporary memory bank."""
    return MelvinVanilla(memory=tmp_memory, skills=skills, heat_level=5)


# ── Test 1: SkillsManager — loading and section access ───────────────────────

class TestSkillsManager:
    """Verify that skills.txt is parsed correctly."""

    def test_sections_not_empty(self, skills: SkillsManager) -> None:
        assert len(skills.sections) > 0, "skills.txt should have at least one section"

    def test_core_directives_section_present(self, skills: SkillsManager) -> None:
        section = skills.get_section("CORE_DIRECTIVES")
        assert section, "CORE_DIRECTIVES section must be present"

    def test_punctuation_section_present(self, skills: SkillsManager) -> None:
        section = skills.get_section("PUNCTUATION_AND_WRITING")
        assert section, "PUNCTUATION_AND_WRITING section must be present"

    def test_programming_languages_section_present(self, skills: SkillsManager) -> None:
        section = skills.get_section("PROGRAMMING_LANGUAGES")
        assert section, "PROGRAMMING_LANGUAGES section must be present"

    def test_mathematics_section_present(self, skills: SkillsManager) -> None:
        section = skills.get_section("MATHEMATICS_AND_NUMBERS")
        assert section, "MATHEMATICS_AND_NUMBERS section must be present"

    def test_astronomy_section_present(self, skills: SkillsManager) -> None:
        section = skills.get_section("ASTRONOMY")
        assert section, "ASTRONOMY section must be present"

    def test_level_system_section_present(self, skills: SkillsManager) -> None:
        section = skills.get_section("LEVEL_SYSTEM")
        assert section, "LEVEL_SYSTEM section must be present"

    def test_throttle_settings_section_present(self, skills: SkillsManager) -> None:
        section = skills.get_section("THROTTLE_SETTINGS")
        assert section, "THROTTLE_SETTINGS section must be present"

    def test_core_directives_returns_list(self, skills: SkillsManager) -> None:
        directives = skills.get_core_directives()
        assert isinstance(directives, list)
        assert len(directives) >= 3, "Should have at least 3 core directives"

    def test_priority_keywords_not_empty(self, skills: SkillsManager) -> None:
        keywords = skills.get_priority_keywords()
        assert len(keywords) > 0
        assert "important" in keywords

    def test_low_priority_phrases_not_empty(self, skills: SkillsManager) -> None:
        phrases = skills.get_low_priority_phrases()
        assert len(phrases) > 0

    def test_search_returns_results(self, skills: SkillsManager) -> None:
        results = skills.search("python")
        assert len(results) > 0
        assert all("section" in r and "key" in r and "value" in r for r in results)

    def test_search_limit_respected(self, skills: SkillsManager) -> None:
        results = skills.search("a", limit=3)
        assert len(results) <= 3

    def test_search_no_results_for_nonsense(self, skills: SkillsManager) -> None:
        results = skills.search("xyzqrstuvwxyz_no_match_guaranteed_9999")
        assert results == []

    def test_heat_description_level_1(self, skills: SkillsManager) -> None:
        desc = skills.get_heat_description(1)
        assert "1" in desc or "minimal" in desc.lower() or len(desc) > 0

    def test_heat_description_level_9(self, skills: SkillsManager) -> None:
        desc = skills.get_heat_description(9)
        assert len(desc) > 0

    def test_case_insensitive_section_lookup(self, skills: SkillsManager) -> None:
        upper = skills.get_section("ASTRONOMY")
        lower = skills.get_section("astronomy")
        assert upper == lower

    def test_missing_section_returns_empty(self, skills: SkillsManager) -> None:
        result = skills.get_section("NONEXISTENT_SECTION_XYZ")
        assert result == {}

    def test_skills_file_loads_from_default_path(self) -> None:
        sm = SkillsManager()
        assert sm.is_loaded() is False  # not yet loaded (lazy)
        _ = sm.sections            # trigger load
        assert sm.is_loaded() is True

    def test_reload_clears_cache(self, skills: SkillsManager) -> None:
        _ = skills.sections  # load once
        skills.reload()
        assert skills.is_loaded() is True  # re-loaded immediately


# ── Test 2: Priority memory ───────────────────────────────────────────────────

class TestPriorityMemory:
    """Verify that priority levels are stored and retrieved correctly."""

    def test_normal_entry_has_priority_normal(self, tmp_memory: MemoryManager) -> None:
        entry = tmp_memory.append("Hello", "Hi", "vanilla", priority_level=PRIORITY_NORMAL)
        assert entry["priority_level"] == PRIORITY_NORMAL

    def test_high_priority_entry_stored(self, tmp_memory: MemoryManager) -> None:
        entry = tmp_memory.append("Important!", "Noted.", "vanilla", priority_level=PRIORITY_HIGH)
        assert entry["priority_level"] == PRIORITY_HIGH

    def test_low_priority_entry_stored(self, tmp_memory: MemoryManager) -> None:
        entry = tmp_memory.append("Minor", "OK", "vanilla", priority_level=PRIORITY_LOW)
        assert entry["priority_level"] == PRIORITY_LOW

    def test_get_priority_entries_returns_only_high(self, tmp_memory: MemoryManager) -> None:
        tmp_memory.append("Normal msg", "resp", "vanilla", priority_level=PRIORITY_NORMAL)
        tmp_memory.append("Important msg", "resp", "vanilla", priority_level=PRIORITY_HIGH)
        tmp_memory.append("Low msg", "resp", "vanilla", priority_level=PRIORITY_LOW)
        high_entries = tmp_memory.get_priority_entries(PRIORITY_HIGH)
        assert len(high_entries) == 1
        assert high_entries[0]["user_message"] == "Important msg"

    def test_get_priority_entries_limit_respected(self, tmp_memory: MemoryManager) -> None:
        for i in range(10):
            tmp_memory.append(f"msg {i}", "resp", "vanilla", priority_level=PRIORITY_HIGH)
        results = tmp_memory.get_priority_entries(PRIORITY_HIGH, limit=3)
        assert len(results) == 3

    def test_keywords_binary_set_at_heat_1_low_priority(
        self, tmp_memory: MemoryManager
    ) -> None:
        entry = tmp_memory.append(
            "minor thing",
            "ok",
            "vanilla",
            priority_level=PRIORITY_LOW,
            heat_level=1,
        )
        # At heat 1 + low priority, binary encoding should be set
        assert entry["keywords_binary"] is not None
        assert len(entry["keywords_binary"]) > 0

    def test_keywords_binary_none_at_normal_heat(self, tmp_memory: MemoryManager) -> None:
        entry = tmp_memory.append(
            "normal message",
            "response",
            "vanilla",
            priority_level=PRIORITY_LOW,
            heat_level=5,
        )
        # At heat 5, no binary encoding even for low priority
        assert entry["keywords_binary"] is None

    def test_hash_chain_valid_with_priority_fields(self, tmp_memory: MemoryManager) -> None:
        tmp_memory.append("msg1", "resp1", "vanilla", priority_level=PRIORITY_HIGH)
        tmp_memory.append("msg2", "resp2", "vanilla", priority_level=PRIORITY_LOW)
        ok, msg = tmp_memory.verify_integrity()
        assert ok is True, f"Hash chain should be valid: {msg}"


# ── Test 3: Binary keyword encoding/decoding ──────────────────────────────────

class TestBinaryEncoding:
    """Verify the encode/decode helpers in utils."""

    def test_encode_returns_string(self) -> None:
        result = encode_keywords_binary("hello world")
        assert isinstance(result, str)

    def test_encode_empty_string(self) -> None:
        result = encode_keywords_binary("")
        assert result == ""

    def test_decode_roundtrip(self) -> None:
        original = "python programming language"
        encoded = encode_keywords_binary(original)
        decoded = decode_keywords_binary(encoded)
        # All decoded words should be present in the original text
        for word in decoded:
            assert word in original

    def test_decode_empty_string(self) -> None:
        result = decode_keywords_binary("")
        assert result == []

    def test_encode_respects_max_words(self) -> None:
        # More than 20 words; should keep only max_words longest ones
        text = " ".join([f"word{i}" for i in range(30)])
        encoded = encode_keywords_binary(text, max_words=5)
        decoded = decode_keywords_binary(encoded)
        assert len(decoded) <= 5


# ── Test 4: Vanilla chatbot ────────────────────────────────────────────────────

class TestMelvinVanilla:
    """Verify the vanilla chatbot answers and memory behaviour."""

    def test_answer_returns_string(self, vanilla: MelvinVanilla) -> None:
        response = vanilla.answer("python")
        assert isinstance(response, str)
        assert len(response) > 0

    def test_answer_stored_in_memory(
        self, vanilla: MelvinVanilla, tmp_memory: MemoryManager
    ) -> None:
        vanilla.answer("python function")
        entries = tmp_memory.get_recent(1)
        assert len(entries) == 1
        assert "python" in entries[0]["user_message"].lower()

    def test_answer_model_label_is_vanilla(
        self, vanilla: MelvinVanilla, tmp_memory: MemoryManager
    ) -> None:
        vanilla.answer("bash variable")
        entries = tmp_memory.get_recent(1)
        assert entries[0]["model_used"] == "vanilla"

    def test_no_match_returns_helpful_fallback(self, vanilla: MelvinVanilla) -> None:
        response = vanilla.answer("zzznosuchtopicxxx99999")
        assert "don't have" in response.lower() or "no" in response.lower()

    def test_priority_detected_from_important_keyword(
        self, vanilla: MelvinVanilla, tmp_memory: MemoryManager
    ) -> None:
        vanilla.answer("This is important: remember python loops")
        entries = tmp_memory.get_priority_entries(PRIORITY_HIGH)
        assert len(entries) == 1

    def test_heat_level_affects_results_count(
        self, tmp_memory: MemoryManager, skills: SkillsManager
    ) -> None:
        bot_low = MelvinVanilla(memory=tmp_memory, skills=skills, heat_level=1)
        bot_high = MelvinVanilla(memory=tmp_memory, skills=skills, heat_level=9)
        # At heat 1, only 1 result requested; at heat 9, up to 9 results
        assert bot_low._results_for_heat() == 1
        assert bot_high._results_for_heat() == 9

    def test_heat_level_clamps_to_1_9(
        self, tmp_memory: MemoryManager, skills: SkillsManager
    ) -> None:
        bot_low = MelvinVanilla(memory=tmp_memory, skills=skills, heat_level=0)
        bot_high = MelvinVanilla(memory=tmp_memory, skills=skills, heat_level=99)
        assert bot_low.heat_level == 1
        assert bot_high.heat_level == 9

    def test_xyz_sequence_detection(self, vanilla: MelvinVanilla) -> None:
        # The sequence is x, y, z, x, y, z — six separate inputs
        tokens = ["x", "y", "z", "x", "y"]
        for token in tokens:
            assert vanilla._check_xyz_sequence(token) is False
        # Sixth token completes the sequence
        assert vanilla._check_xyz_sequence("z") is True

    def test_xyz_sequence_resets_on_mismatch(self, vanilla: MelvinVanilla) -> None:
        vanilla._check_xyz_sequence("x")
        vanilla._check_xyz_sequence("y")
        vanilla._check_xyz_sequence("a")  # mismatch — should reset
        # After reset, the sequence must start again from the beginning
        assert vanilla._seq_buffer == []

    def test_detect_priority_normal(self, vanilla: MelvinVanilla) -> None:
        assert vanilla._detect_priority("Just a normal question") == PRIORITY_NORMAL

    def test_detect_priority_high(self, vanilla: MelvinVanilla) -> None:
        assert vanilla._detect_priority("This is important please remember") == PRIORITY_HIGH

    def test_detect_priority_low(self, vanilla: MelvinVanilla) -> None:
        result = vanilla._detect_priority("it's ok if you can't do this")
        assert result == PRIORITY_LOW


# ── Test 5: Vanilla CLI ────────────────────────────────────────────────────────

class TestVanillaCLI:
    """Test command-line argument parsing for melvin_vanilla.py."""

    def test_verify_flag_exits_0_on_empty_memory(self, tmp_path: Path) -> None:
        from src.melvin_vanilla import main
        with patch("src.user_manager.DATA_DIR", tmp_path):
            exit_code = main(["--user", "clitest", "--verify"])
        assert exit_code == 0

    def test_history_flag_exits_0_on_empty_memory(self, tmp_path: Path) -> None:
        from src.melvin_vanilla import main
        with patch("src.user_manager.DATA_DIR", tmp_path):
            exit_code = main(["--user", "clitest2", "--history", "5"])
        assert exit_code == 0

    def test_search_flag_exits_0(self, tmp_path: Path) -> None:
        from src.melvin_vanilla import main
        with patch("src.user_manager.DATA_DIR", tmp_path):
            exit_code = main(["--user", "clitest3", "--search", "python"])
        assert exit_code == 0
