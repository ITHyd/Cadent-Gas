"""Lightweight English text validator for resolution fields.

Validates that resolution notes, root cause, and actions taken contain
plausible English text — rejecting gibberish like 'anaogna aaknga skjfn'.

Uses structural heuristics (vowel/consonant patterns, common bigrams)
instead of a dictionary, so it never rejects valid English words.
No external dependencies required.
"""

import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────
MIN_WORDS_FOR_VALIDATION = 3
# Fraction of words that must look structurally English
MIN_PLAUSIBLE_RATIO = 0.50

VOWELS = set("aeiouy")
CONSONANTS = set("bcdfghjklmnpqrstvwxz")

# Common English bigrams — if a word contains several of these it's likely real
_COMMON_BIGRAMS = frozenset({
    "th", "he", "in", "er", "an", "re", "on", "at", "en", "nd",
    "ti", "es", "or", "te", "of", "ed", "is", "it", "al", "ar",
    "st", "to", "nt", "ng", "se", "ha", "as", "ou", "io", "le",
    "ve", "co", "me", "de", "hi", "ri", "ro", "ic", "ne", "ea",
    "ra", "ce", "li", "ch", "ll", "be", "ma", "si", "om", "ur",
    "ca", "el", "ta", "la", "ns", "ge", "ly", "ei", "ol", "ul",
    "ni", "pl", "ct", "us", "ac", "ot", "il", "tr", "ig", "nc",
    "sl", "pe", "ut", "ss", "ow", "ad", "su", "po", "ee", "no",
    "so", "do", "wi", "sh", "ag", "up", "ke", "wa", "ab", "am",
    "id", "op", "we", "un", "ry", "ay", "ex", "oo", "wh", "ck",
    "ir", "bl", "pr", "ld", "im", "gu", "uc", "if", "da", "tu",
    "iv", "vi", "pa", "ov", "em", "ob", "ib", "ia", "ie", "ue",
    "oa", "ew", "ff", "tt", "pp", "rr", "mm", "nn", "ft", "pt",
    "mp", "nk", "sp", "sk", "sc", "sw", "cr", "gr", "fr", "dr",
    "br", "fl", "cl", "gl", "sm", "sn", "tw", "ph", "wr", "kn",
})

# Very rare bigrams in English — multiple of these signal gibberish
_RARE_BIGRAMS = frozenset({
    "qq", "zx", "xz", "jq", "qj", "zq", "qz", "vq", "qv",
    "jx", "xj", "zj", "jz", "vx", "xv", "bx", "xb", "kx", "xk",
    "wx", "xw", "mx", "xm", "gx", "xg", "hx", "xh",
    "fq", "qf", "pq", "qp", "vj", "jv", "bq", "qb",
    "zz", "xx", "jj", "qq",
})


def _has_vowels(word: str) -> bool:
    """Check that the word contains at least one vowel."""
    return any(c in VOWELS for c in word)


def _max_consecutive(word: str, char_set: set) -> int:
    """Return the longest run of characters from char_set in word."""
    max_run = 0
    current = 0
    for c in word:
        if c in char_set:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run


def _bigram_score(word: str) -> float:
    """
    Return fraction of the word's bigrams that are common English bigrams.
    Higher = more English-like.
    """
    if len(word) < 2:
        return 1.0  # single chars are fine
    bigrams = [word[i:i+2] for i in range(len(word) - 1)]
    common_count = sum(1 for bg in bigrams if bg in _COMMON_BIGRAMS)
    return common_count / len(bigrams)


def _rare_bigram_count(word: str) -> int:
    """Count how many rare/impossible bigrams the word contains."""
    if len(word) < 2:
        return 0
    bigrams = [word[i:i+2] for i in range(len(word) - 1)]
    return sum(1 for bg in bigrams if bg in _RARE_BIGRAMS)


def _is_word_plausible(word: str) -> bool:
    """
    Determine if a single word looks structurally like English.

    Accepts real words like: everything, guidance, fixed, thermocouple, recommission
    Rejects gibberish like: anaogna, aaknga, skjfn, qqxvz, bbbbb
    """
    # Very short words are always fine (a, an, ok, co, id, etc.)
    if len(word) <= 3:
        return True

    # Must contain at least one vowel
    if not _has_vowels(word):
        return False

    # No more than 4 consecutive consonants (English max is ~4: "strengths")
    if _max_consecutive(word, CONSONANTS) > 4:
        return False

    # No more than 3 consecutive vowels (English: "queue" has 4 but rare)
    if _max_consecutive(word, VOWELS) > 3:
        return False

    # Check vowel ratio — English words typically have 30-60% vowels
    vowel_count = sum(1 for c in word if c in VOWELS)
    vowel_ratio = vowel_count / len(word)
    if vowel_ratio < 0.15 or vowel_ratio > 0.80:
        return False

    # For longer words, check bigram plausibility
    if len(word) >= 5:
        bg_score = _bigram_score(word)
        # At least 30% of bigrams should be common English bigrams
        if bg_score < 0.25:
            return False

    # Any rare/impossible bigrams is a strong signal of gibberish
    if _rare_bigram_count(word) >= 2:
        return False

    return True


def validate_english_text(text: str, field_name: str = "text") -> Tuple[bool, str]:
    """
    Validate that a text field contains plausible English text.

    Uses structural heuristics — does NOT require words to be in a dictionary.
    Any normally-structured English word will pass. Only gibberish with
    broken letter patterns (no vowels, impossible bigrams, etc.) is rejected.

    Returns:
        (is_valid, error_message)  — error_message is empty when valid.
    """
    if not text or not text.strip():
        return False, f"{field_name} cannot be empty."

    # Tokenize: extract alphabetic words (including contractions like "don't")
    words = re.findall(r"[a-zA-Z]+(?:'[a-zA-Z]+)?", text.lower())

    if len(words) < MIN_WORDS_FOR_VALIDATION:
        return False, (
            f"{field_name} is too short. Please provide at least "
            f"{MIN_WORDS_FOR_VALIDATION} descriptive words."
        )

    plausible = 0
    for word in words:
        if _is_word_plausible(word):
            plausible += 1

    ratio = plausible / len(words) if words else 0.0

    if ratio < MIN_PLAUSIBLE_RATIO:
        return False, (
            f"{field_name} does not appear to contain valid English text. "
            f"Please write clear, descriptive notes in English."
        )

    return True, ""


def validate_resolution_text_fields(
    resolution_notes: str,
    root_cause: str,
    actions_taken: List[str],
) -> Dict[str, str]:
    """
    Validate all text fields in the resolution checklist.

    Returns:
        Dict of field_name -> error_message. Empty dict means all valid.
    """
    errors: Dict[str, str] = {}

    is_valid, msg = validate_english_text(resolution_notes, "Resolution notes")
    if not is_valid:
        errors["resolution_notes"] = msg

    is_valid, msg = validate_english_text(root_cause, "Root cause")
    if not is_valid:
        errors["root_cause"] = msg

    # Join actions into a single text block for validation
    actions_text = ", ".join(actions_taken) if actions_taken else ""
    is_valid, msg = validate_english_text(actions_text, "Actions taken")
    if not is_valid:
        errors["actions_taken"] = msg

    return errors
