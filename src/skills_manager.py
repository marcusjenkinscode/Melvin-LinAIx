"""
skills_manager.py — Load and query Melvin's skills knowledge base.

The skills base is stored in ``skills.txt`` (project root) as a flat text
file divided into ``[SECTION]`` blocks.  Each block contains entries of the
form::

    KEY: value text (possibly spanning several indented continuation lines)

The manager loads all sections on first access (lazy-loaded, cached) and
exposes fast keyword search across all entries.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# Default location of the skills file (project root)
_DEFAULT_SKILLS_PATH = Path(__file__).resolve().parent.parent / "skills.txt"


class SkillsManager:
    """Load and query the skills knowledge base from ``skills.txt``.

    Args:
        skills_path: Path to the skills file.  Defaults to the ``skills.txt``
                     in the project root.

    Attributes:
        sections:  ``dict[section_name, dict[key, value]]`` of all parsed data.
    """

    def __init__(self, skills_path: Optional[Path] = None) -> None:
        self._path: Path = skills_path or _DEFAULT_SKILLS_PATH
        self._sections: Optional[dict[str, dict[str, str]]] = None

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def sections(self) -> dict[str, dict[str, str]]:
        """Return all sections (lazy-loaded on first access)."""
        if self._sections is None:
            self._sections = self._parse(self._path)
        return self._sections

    def get_section(self, name: str) -> dict[str, str]:
        """Return the entries for *name* (case-insensitive section lookup).

        Args:
            name: Section name such as ``"PUNCTUATION_AND_WRITING"``.

        Returns:
            Dict of ``{key: value}`` entries, or an empty dict if not found.
        """
        name_upper = name.upper()
        for section_name, entries in self.sections.items():
            if section_name.upper() == name_upper:
                return entries
        return {}

    def search(self, query: str, limit: int = 10) -> list[dict[str, str]]:
        """Search all entries for *query* (case-insensitive).

        For single-word queries, a simple substring match is used.
        For multi-word queries, every word in the query must appear
        somewhere in the key or value (AND logic), so that a query such
        as ``"python variable"`` matches the ``PYTHON_VARIABLE`` entry.

        Args:
            query: Search term (may contain spaces).
            limit: Maximum number of results.

        Returns:
            List of dicts, each with keys ``section``, ``key``, and ``value``.
        """
        query_lower = query.lower().strip()
        words = query_lower.split()
        results: list[dict[str, str]] = []

        for section_name, entries in self.sections.items():
            for key, value in entries.items():
                haystack = (key + " " + value).lower()
                # All query words must appear in the combined key+value text
                if all(w in haystack for w in words):
                    results.append(
                        {"section": section_name, "key": key, "value": value}
                    )
                    if len(results) >= limit:
                        return results

        return results

    def get_core_directives(self) -> list[str]:
        """Return the list of core directive values from CORE_DIRECTIVES.

        Returns:
            List of directive value strings.
        """
        directives = self.get_section("CORE_DIRECTIVES")
        return [
            value
            for key, value in directives.items()
            if key.startswith("DIRECTIVE_")
        ]

    def get_priority_keywords(self) -> list[str]:
        """Return the list of phrases that mark a message as high-priority.

        Returns:
            List of lowercased keyword/phrase strings.
        """
        directives = self.get_section("CORE_DIRECTIVES")
        keywords: list[str] = []
        for key, value in directives.items():
            if key == "PRIORITY_KEYWORD":
                # Multiple entries are stored newline-joined; split them
                for phrase in value.split("\n"):
                    phrase = phrase.strip().lower()
                    if phrase:
                        keywords.append(phrase)
        return keywords

    def get_low_priority_phrases(self) -> list[str]:
        """Return phrases that mark a message as low-priority.

        Returns:
            List of lowercased phrase strings.
        """
        directives = self.get_section("CORE_DIRECTIVES")
        phrases: list[str] = []
        for key, value in directives.items():
            if key == "LOW_PRIORITY_PHRASE":
                for phrase in value.split("\n"):
                    phrase = phrase.strip().lower()
                    if phrase:
                        phrases.append(phrase)
        return phrases

    def get_heat_description(self, level: int) -> str:
        """Return the description for a given heat/throttle level.

        Args:
            level: Integer 1–9.

        Returns:
            Description string, or a generic note if out of range.
        """
        key = f"HEAT_LEVEL_{level}"
        throttle = self.get_section("THROTTLE_SETTINGS")
        return throttle.get(key, f"Heat level {level}")

    def is_loaded(self) -> bool:
        """Return ``True`` if the skills file has been loaded."""
        return self._sections is not None

    def reload(self) -> None:
        """Force a reload of the skills file from disk."""
        self._sections = self._parse(self._path)

    # ── Parsing ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse(path: Path) -> dict[str, dict[str, str]]:
        """Parse the skills text file into a nested dict.

        Parsing rules:
        - Lines beginning with ``#`` are comments (skipped).
        - ``[SECTION_NAME]`` lines start a new section.
        - ``KEY: value`` lines start a new entry; the key is the text before
          the first colon and the value is everything after.
        - Lines indented with 4+ spaces are continuation lines appended to
          the most recent entry's value.
        - Blank lines are ignored inside sections.

        Returns:
            ``{section_name: {key: value_text, ...}, ...}``
        """
        sections: dict[str, dict[str, str]] = {}
        current_section: Optional[str] = None
        current_key: Optional[str] = None
        current_value_lines: list[str] = []

        def flush() -> None:
            """Commit accumulated value lines to the current section/key."""
            if current_section is not None and current_key is not None:
                value = " ".join(
                    line.strip() for line in current_value_lines
                ).strip()
                if current_key in sections[current_section]:
                    # Duplicate key: append as a list-style multi-value entry
                    existing = sections[current_section][current_key]
                    sections[current_section][current_key] = (
                        existing + "\n" + value
                    )
                else:
                    sections[current_section][current_key] = value

        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.rstrip("\n")

                # Skip comments
                if line.lstrip().startswith("#"):
                    continue

                # Section header  [SECTION_NAME]
                section_match = re.match(r"^\[([A-Z_0-9]+)\]", line.strip())
                if section_match:
                    flush()
                    current_section = section_match.group(1)
                    current_key = None
                    current_value_lines = []
                    sections.setdefault(current_section, {})
                    continue

                if current_section is None:
                    continue

                # Continuation line (4+ leading spaces)
                if line.startswith("    ") and current_key is not None:
                    current_value_lines.append(line)
                    continue

                # Blank line — flush and reset
                if not line.strip():
                    if current_key is not None:
                        flush()
                        current_key = None
                        current_value_lines = []
                    continue

                # KEY: value line
                if ":" in line:
                    flush()
                    colon_idx = line.index(":")
                    current_key = line[:colon_idx].strip()
                    rest = line[colon_idx + 1:].strip()
                    current_value_lines = [rest] if rest else []
                    continue

        flush()
        return sections
