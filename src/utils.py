"""
utils.py — Shared helper utilities for Melvin-LinAIx.

Provides:
  - get_timestamp()         ISO-8601 UTC timestamp string
  - sanitize_username()     Makes a raw name safe for directory names
  - generate_unique_code()  Random alphanumeric code for user directories
  - compute_hash()          SHA-256 of an arbitrary string
  - compute_entry_hash()    Chain hash for a single conversation entry
  - aggregate_responses()   Combine multiple model outputs (ensemble helper)
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import string
from datetime import datetime, timezone
from typing import Any


# ── Timestamp ─────────────────────────────────────────────────────────────────

def get_timestamp() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ── Username / directory helpers ──────────────────────────────────────────────

def sanitize_username(name: str) -> str:
    """Sanitize a raw user-supplied name for use in a directory name.

    Rules:
    - Convert to lowercase
    - Replace any run of non-alphanumeric characters with a single underscore
    - Strip leading / trailing underscores
    - Truncate to 32 characters

    Args:
        name: Raw username string.

    Returns:
        Sanitized lowercase alphanumeric (plus underscore) string.
    """
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = name.strip("_")
    return name[:32] or "user"


def generate_unique_code(length: int = 6) -> str:
    """Generate a random alphanumeric code.

    Args:
        length: Number of characters (default 6).

    Returns:
        Upper-case alphanumeric string of the requested length.
    """
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choices(alphabet, k=length))


# ── Cryptographic helpers ─────────────────────────────────────────────────────

def compute_hash(data: str) -> str:
    """Compute the SHA-256 hex digest of a UTF-8 string.

    Args:
        data: Input string.

    Returns:
        64-character hex digest.
    """
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def compute_entry_hash(
    previous_hash: str,
    timestamp: str,
    user_message: str,
    ai_response: str,
    model_used: str,
) -> str:
    """Compute the chained hash for a single conversation entry.

    The hash is: SHA-256(previous_hash + JSON(entry_data))

    Args:
        previous_hash: Context hash of the immediately preceding entry
            (use an empty string or all-zeros for the genesis entry).
        timestamp:    ISO-8601 timestamp of the entry.
        user_message: The user's message text.
        ai_response:  The model's response text.
        model_used:   Name of the Ollama model that generated the response.

    Returns:
        64-character hex digest.
    """
    entry_data = json.dumps(
        {
            "timestamp": timestamp,
            "user_message": user_message,
            "ai_response": ai_response,
            "model_used": model_used,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return compute_hash(previous_hash + entry_data)


def encode_keywords_binary(text: str, max_words: int = 20) -> str:
    """Encode the most significant keywords of *text* as binary bit strings.

    This compact representation is used at heat level 1 for low-priority
    entries so that key information is retained in minimal space.

    Strategy:
    1. Tokenise *text* into words, strip punctuation, lowercase.
    2. Keep only the longest ``max_words`` unique words (they tend to carry
       the most meaning).
    3. Encode each selected word as a space-separated sequence of 8-bit
       binary strings (UTF-8 byte values).

    Args:
        text:      Input string to encode.
        max_words: Maximum number of words to retain (default 20).

    Returns:
        A pipe-delimited (``|``) string of binary representations, one per
        selected word.  Returns an empty string if no words are found.

    Example::

        encode_keywords_binary("Hello world")
        # 'hello:01101000 01100101 01101100 01101100 01101111|world:01110111 01101111 01110010 01101100 01100100'
    """
    tokens = re.sub(r"[^a-zA-Z0-9 ]", "", text).lower().split()
    # De-duplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            unique.append(token)

    # Keep the longest (most informative) words
    selected = sorted(unique, key=len, reverse=True)[:max_words]

    parts: list[str] = []
    for word in selected:
        bits = " ".join(format(b, "08b") for b in word.encode("utf-8"))
        parts.append(f"{word}:{bits}")

    return "|".join(parts)


def decode_keywords_binary(encoded: str) -> list[str]:
    """Decode a binary-encoded keyword string produced by :func:`encode_keywords_binary`.

    Args:
        encoded: Pipe-delimited binary keyword string.

    Returns:
        List of decoded keyword strings.  Entries that cannot be decoded are
        silently skipped.
    """
    if not encoded:
        return []
    words: list[str] = []
    for part in encoded.split("|"):
        if ":" not in part:
            continue
        word_part, bits_part = part.split(":", 1)
        try:
            byte_values = [int(b, 2) for b in bits_part.split()]
            decoded = bytes(byte_values).decode("utf-8")
            words.append(decoded)
        except (ValueError, UnicodeDecodeError):
            words.append(word_part)  # fall back to the plain-text prefix
    return words

def aggregate_responses(responses: list[dict[str, Any]]) -> str:
    """Aggregate multiple model responses into a single answer.

    Strategy (simple majority-length vote):
    1. If only one response is available, return it directly.
    2. Otherwise use a token-frequency vote:
       - Split each response into words.
       - Build a frequency map.
       - Select the response whose word set is most representative
         (highest mean frequency score).

    In practice this tends to surface the most "consensus" response
    without requiring a separate scoring model.

    Args:
        responses: List of dicts with keys ``model`` and ``response``.

    Returns:
        The aggregated / selected response string.
    """
    if not responses:
        return ""
    if len(responses) == 1:
        return responses[0]["response"]

    texts: list[str] = [r["response"] for r in responses if r.get("response")]
    if not texts:
        return ""

    # Build word frequency across all responses
    freq: dict[str, int] = {}
    for text in texts:
        for word in text.lower().split():
            freq[word] = freq.get(word, 0) + 1

    # Score each response by mean word frequency
    best_text = texts[0]
    best_score = -1.0
    for text in texts:
        words = text.lower().split()
        if not words:
            continue
        score = sum(freq.get(w, 0) for w in words) / len(words)
        if score > best_score:
            best_score = score
            best_text = text

    # Prepend a summary header so the user sees which models answered
    model_names = ", ".join(r["model"] for r in responses if r.get("model"))
    header = f"[Ensemble from: {model_names}]\n\n"
    return header + best_text
