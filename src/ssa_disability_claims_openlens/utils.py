"""
Shared utility functions for SSA Disability Claims OpenLens.

Utilities are intentionally side-effect free and independently testable.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from rich.console import Console
from rich.logging import RichHandler

from .config import get_settings
from .models import CoverageRating, FreshnessStatus, UpdateFrequency

# ── Logging ────────────────────────────────────────────────────────────────────


def get_logger(name: str) -> logging.Logger:
    """
    Return a Rich-formatted logger.

    All output goes to stderr so stdout stays clean for the MCP stdio transport.
    """
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True, console=Console(stderr=True))],
    )
    logger = logging.getLogger(name)
    logger.setLevel(level)
    return logger


# ── Score helpers ──────────────────────────────────────────────────────────────


def score_to_coverage_rating(score: float) -> CoverageRating:
    """Map a 0–100 numeric score to a qualitative CoverageRating."""
    settings = get_settings()
    if score >= settings.coverage_complete_threshold:
        return CoverageRating.COMPLETE
    if score >= settings.coverage_high_threshold:
        return CoverageRating.HIGH
    if score >= settings.coverage_partial_threshold:
        return CoverageRating.PARTIAL
    if score >= settings.coverage_limited_threshold:
        return CoverageRating.LIMITED
    return CoverageRating.UNSUPPORTED


def days_since(d: date | None) -> int | None:
    """Return the number of calendar days since a given date, or None."""
    if d is None:
        return None
    return (date.today() - d).days


def frequency_to_expected_days(freq: UpdateFrequency) -> int | None:
    """Return the expected maximum days between updates for a given frequency."""
    mapping: dict[UpdateFrequency, int] = {
        UpdateFrequency.REAL_TIME: 1,
        UpdateFrequency.DAILY: 1,
        UpdateFrequency.WEEKLY: 7,
        UpdateFrequency.MONTHLY: 31,
        UpdateFrequency.QUARTERLY: 92,
        UpdateFrequency.ANNUALLY: 366,
        UpdateFrequency.IRREGULAR: 180,
    }
    return mapping.get(freq)


def compute_freshness_score(
    last_updated: date | None, frequency: UpdateFrequency
) -> tuple[float, FreshnessStatus, list[str]]:
    """
    Compute a 0–100 freshness score and qualitative status.

    Returns (score, status, staleness_indicators).
    """
    staleness: list[str] = []
    elapsed = days_since(last_updated)
    expected = frequency_to_expected_days(frequency)

    if elapsed is None or last_updated is None:
        return 0.0, FreshnessStatus.UNKNOWN, ["Last update date is unknown"]

    if expected is None:
        # Irregular cadence — use 180-day heuristic
        expected = 180

    ratio = elapsed / expected  # > 1 means overdue

    if ratio <= 1.0:
        score = 100.0
        status = FreshnessStatus.CURRENT
    elif ratio <= 1.5:
        score = max(0.0, 100.0 - (ratio - 1.0) * 100)
        status = FreshnessStatus.AGING
        staleness.append(
            f"Dataset is {elapsed} days old; expected update every ~{expected} days"
        )
    else:
        score = max(0.0, 100.0 - (ratio - 1.0) * 60)
        status = FreshnessStatus.STALE
        overdue = elapsed - expected
        staleness.append(
            f"Dataset is {overdue} day(s) overdue for update (last updated {last_updated})"
        )

    if elapsed > 365:
        staleness.append("No update in over 12 months — data may no longer reflect current conditions")
    if elapsed > 730:
        staleness.append("No update in over 24 months — dataset may be deprecated or abandoned")

    return round(max(0.0, min(100.0, score)), 1), status, staleness


def keyword_match_score(text: str, keywords: list[str]) -> float:
    """
    Return a 0.0–1.0 relevance score based on keyword presence.

    Used to filter datasets by relevance to a question.
    """
    if not keywords:
        return 1.0
    text_lower = text.lower()
    matches = sum(1 for kw in keywords if kw.lower() in text_lower)
    return matches / len(keywords)


def extract_keywords(text: str) -> list[str]:
    """
    Extract meaningful keywords from a natural language string.

    Simple stop-word removal — good enough for catalog search without
    requiring an NLP dependency.
    """
    stop_words = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "to", "of", "in", "on",
        "at", "by", "for", "with", "about", "against", "between", "into",
        "through", "during", "before", "after", "above", "below", "from",
        "up", "down", "and", "but", "or", "nor", "so", "yet", "not", "no",
        "how", "what", "when", "where", "who", "which", "why", "i", "me",
        "my", "we", "our", "you", "your", "it", "its", "this", "that",
        "these", "those", "long", "many", "much", "more", "most",
    }
    words = text.lower().split()
    return [w.strip("?.!,;:\"'()[]") for w in words if w not in stop_words and len(w) > 2]


def truncate(text: str, max_len: int = 200) -> str:
    """Truncate a string with an ellipsis if it exceeds max_len."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def safe_get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely traverse nested dict keys, returning default if any key is missing."""
    current: Any = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current
