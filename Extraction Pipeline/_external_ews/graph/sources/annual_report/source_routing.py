"""Source Routing — Priority-based section selection for extraction fields.

This module defines the preferred source section search order for each
Intelligence Report field.  It solves the problem where the wrong source
section is selected (e.g., Dividend extracted from AGM Notice instead of
Directors Report) because the pipeline processes sections in arbitrary order.

Usage::

    from .source_routing import select_best_source, FIELD_SOURCE_PRIORITY

    best = select_best_source("Dividend Information", text_extractions)
    if best:
        extracted = extract_subcategory_content(
            best["category"], best["subcategory"], best["extracted_text"], llm
        )
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# =====================================================================
# Field → Source Priority Mapping
# =====================================================================
# For each Intelligence Report field, defines the preferred order of
# source sections to search.  The first matching section is used.
# This prevents wrong-source extraction (e.g., AGM Notice for Dividend
# instead of Directors Report).

FIELD_SOURCE_PRIORITY: dict[str, list[str]] = {
    "Board of Directors": [
        "board of directors",
        "board structure",
        "directors profile",
        "corporate governance",
        "corporate governance report",
        "governance report",
        "management discussion",
    ],
    "Key Management Personnel": [
        "key management personnel",
        "kmp",
        "corporate governance",
        "corporate governance report",
        "governance report",
        "management discussion",
    ],
    "Board Committees": [
        "board committees",
        "audit committee",
        "corporate governance",
        "corporate governance report",
        "governance report",
        "management discussion",
    ],
    "Corporate Governance": [
        "corporate governance",
        "corporate governance report",
        "governance report",
        "governance section",
        "management discussion",
    ],
    "Share Capital": [
        "share capital",
        "balance sheet",
        "share capital note",
    ],
    "Shareholding Pattern": [
        "shareholding pattern",
        "shareholding",
        "corporate governance",
    ],
    "Major Shareholders": [
        "shareholding pattern",
        "shareholding",
        "corporate governance",
    ],
    "Dividend Information": [
        "directors report",
        "dividend",
        "financial statements",
        "notice",
        "agm",
    ],
    "Company Profile": [
        "company profile",
        "company overview",
        "about the company",
        "directors report",
    ],
    "Business Overview": [
        "business overview",
        "business review",
        "directors report",
        "management discussion",
    ],
    "Products & Services": [
        "products and services",
        "business overview",
        "directors report",
    ],
    "Subsidiaries & Group Structure": [
        "subsidiaries",
        "group structure",
        "subsidiary",
        "directors report",
        "annexure",
    ],
    "Industry Overview": [
        "industry overview",
        "management discussion",
        "directors report",
    ],
    "Business Review": [
        "business review",
        "performance review",
        "management discussion",
        "directors report",
    ],
    "Opportunities & Challenges": [
        "opportunities",
        "risk factors",
        "management discussion",
        "directors report",
    ],
    "Future Outlook": [
        "future outlook",
        "outlook",
        "management discussion",
        "directors report",
    ],
}


def _match_score(alias: str, text: str) -> int:
    """Score how well an alias matches a text string.

    Returns
    -------
    int
        3 = normalized exact match
        2 = word-boundary regex match
        1 = substring match (weaker, may be false positive)
        0 = no match
    """
    alias_lower = alias.lower().strip()
    text_lower = text.lower().strip()

    # Normalized exact match (highest confidence)
    if alias_lower == text_lower:
        return 3

    # Word-boundary regex match: alias words must appear as whole words
    # e.g., "directors report" matches "Directors' Report" but not "Independent Directors"
    try:
        # Build a pattern that requires each significant word in the alias
        # to appear as a word boundary in the text
        alias_words = re.findall(r'[a-z0-9]+', alias_lower)
        if alias_words:
            # All alias words must be present as word boundaries
            pattern = r'\b' + r'\b.*\b'.join(re.escape(w) for w in alias_words) + r'\b'
            if re.search(pattern, text_lower, re.DOTALL):
                return 2
    except re.error:
        pass

    # Substring match (weakest — prone to false positives)
    if alias_lower in text_lower:
        return 1

    return 0


def select_best_source(
    field_name: str,
    text_extractions: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Select the highest-priority source section for a given field.

    Searches ``text_extractions`` in the priority order defined by
    :data:`FIELD_SOURCE_PRIORITY`.  Returns the first extraction whose
    ``subcategory`` or ``category`` matches a priority alias.

    FIX 6: Uses scored matching instead of raw substring matching.
    Score 3 (exact) and 2 (word-boundary) are accepted immediately.
    Score 1 (substring) is accepted only if no higher-score match exists.

    Parameters
    ----------
    field_name : str
        The canonical field name (e.g., ``"Dividend Information"``).
    text_extractions : list[dict]
        The list of text extraction dicts from the pipeline, each with
        at least ``"category"`` and ``"subcategory"`` keys.

    Returns
    -------
    dict | None
        The best-matching extraction dict, or ``None`` if no match found.
    """
    priorities = FIELD_SOURCE_PRIORITY.get(field_name, [])
    if not priorities:
        # No priority defined — return None, caller should use fallback
        return None

    # Collect all matches with scores, then pick the best
    best_match: dict[str, Any] | None = None
    best_score = 0
    best_alias = ""
    best_sub = ""
    best_cat = ""

    for priority_alias in priorities:
        for extraction in text_extractions:
            sub = extraction.get("subcategory", "")
            cat = extraction.get("category", "")

            sub_score = _match_score(priority_alias, sub)
            cat_score = _match_score(priority_alias, cat)
            score = max(sub_score, cat_score)

            if score > best_score:
                best_score = score
                best_match = extraction
                best_alias = priority_alias
                best_sub = sub
                best_cat = cat

            # Early exit on exact match — can't do better
            if best_score >= 3:
                break
        if best_score >= 3:
            break

    # Only accept matches with score >= 2 (exact or word-boundary)
    # Score 1 (substring) is too weak and causes false routing
    if best_match and best_score >= 2:
        logger.info(
            "[SourceRouting] Field '%s' matched priority '%s' → section '%s' "
            "(category: '%s', score: %d)",
            field_name, best_alias, best_sub, best_cat, best_score,
        )
        return best_match

    if best_score == 1:
        logger.info(
            "[SourceRouting] Field '%s' weak substring match '%s' → section '%s' "
            "(score: 1, rejected — requires score >= 2)",
            field_name, best_alias, best_sub,
        )

    logger.info("[SourceRouting] No priority match for field '%s'", field_name)
    return None


def get_all_field_names() -> list[str]:
    """Return all field names that have source priority definitions."""
    return list(FIELD_SOURCE_PRIORITY.keys())
