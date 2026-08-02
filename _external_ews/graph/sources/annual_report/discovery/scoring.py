"""Stage 4 — Confidence Scoring.

Takes raw candidates from Stage 3 and:
  1. Merges duplicate candidates for the same (statement_type, page)
  2. Computes a final weighted confidence score
  3. Rejects candidates below a configurable threshold
  4. Selects the best candidate per statement type

The scoring logic rewards candidates that are confirmed by *multiple*
independent signals (e.g. both bookmarks AND headings point to the
same page → very high confidence).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from .models import (
    Candidate,
    PageInfo,
    ScoreBreakdown,
    StatementType,
)

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────

# Minimum confidence to keep a candidate
MIN_CONFIDENCE_THRESHOLD = 0.15

# Bonus for multi-signal confirmation
MULTI_SIGNAL_BONUS = 0.10


# ── Public API ────────────────────────────────────────────────────

def score_and_rank_candidates(
    candidates: list[Candidate],
    pages: list[PageInfo],
    progress_callback=None,
) -> dict[StatementType, list[Candidate]]:
    """Score, merge, filter, and rank candidates.

    Parameters
    ----------
    candidates : list[Candidate]
        Raw candidates from Stage 3.
    pages : list[PageInfo]
        Parsed page info from Stage 1 (for additional scoring context).
    progress_callback : callable, optional
        Called with progress messages.

    Returns
    -------
    dict[StatementType, list[Candidate]]
        Ranked candidates per statement type, sorted by confidence
        (highest first).  Low-confidence candidates are filtered out.
    """
    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    _log("[Stage 4] Scoring and ranking candidates...")

    # Build page lookup for enrichment
    page_map = {p.page_number: p for p in pages}

    # ── Step 1: Group by (statement_type, page_number) ───────────
    groups: dict[tuple[StatementType, int], list[Candidate]] = defaultdict(list)
    for c in candidates:
        groups[(c.statement_type, c.page_number)].append(c)

    # ── Step 2: Merge and enrich each group ──────────────────────
    merged: list[Candidate] = []
    for (stype, page_num), group in groups.items():
        merged_candidate = _merge_candidate_group(stype, page_num, group, page_map)
        merged.append(merged_candidate)

    # ── Step 3: Filter by confidence threshold ───────────────────
    kept = [c for c in merged if c.confidence >= MIN_CONFIDENCE_THRESHOLD]
    rejected = len(merged) - len(kept)
    if rejected:
        _log(f"[Stage 4] Rejected {rejected} candidate(s) below threshold {MIN_CONFIDENCE_THRESHOLD}")

    # ── Step 4: Group by statement type and sort by confidence ───
    ranked: dict[StatementType, list[Candidate]] = defaultdict(list)
    for c in kept:
        ranked[c.statement_type].append(c)

    for stype in ranked:
        ranked[stype].sort(key=lambda c: c.confidence, reverse=True)

    # Log summary
    for stype, cands in ranked.items():
        top = cands[0]
        _log(
            f"[Stage 4] {stype.value}: {len(cands)} candidate(s), "
            f"best=page {top.page_number} (conf={top.confidence:.2f}, "
            f"source={top.source})"
        )

    return dict(ranked)


# ── Merge logic ───────────────────────────────────────────────────

def _merge_candidate_group(
    stype: StatementType,
    page_number: int,
    group: list[Candidate],
    page_map: dict[int, PageInfo],
) -> Candidate:
    """Merge multiple candidates for the same (statement, page) into one.

    When multiple detection signals (bookmark, TOC, heading, content)
    point to the same page for the same statement type, merge their
    scores and add a multi-signal bonus.
    """
    # Start with the highest-scoring candidate as base
    group.sort(key=lambda c: c.confidence, reverse=True)
    base = group[0]

    if len(group) == 1:
        return base

    # Merge scores: take the max for each component across all signals
    merged_score = ScoreBreakdown(
        heading_score=max(c.score.heading_score for c in group),
        keyword_score=max(c.score.keyword_score for c in group),
        numeric_density_score=max(c.score.numeric_density_score for c in group),
        table_structure_score=max(c.score.table_structure_score for c in group),
        toc_score=max(c.score.toc_score for c in group),
        bookmark_score=max(c.score.bookmark_score for c in group),
        section_heading_score=max(c.score.section_heading_score for c in group),
        date_header_score=max(c.score.date_header_score for c in group),
        continuation_score=max(c.score.continuation_score for c in group),
    )

    # Multi-signal bonus: more independent sources → higher confidence
    unique_sources = {c.source for c in group}
    if len(unique_sources) >= 3:
        bonus = MULTI_SIGNAL_BONUS * 2
    elif len(unique_sources) >= 2:
        bonus = MULTI_SIGNAL_BONUS
    else:
        bonus = 0.0

    # Apply bonus by boosting the weakest non-zero scores
    if bonus > 0:
        # Add bonus to keyword_score (often the weakest)
        merged_score.keyword_score = min(
            merged_score.keyword_score + bonus, 1.0
        )

    # Merge features and reasoning
    all_features: list[str] = []
    all_sources: list[str] = []
    for c in group:
        all_features.extend(c.matched_features)
        all_sources.append(c.source)

    return Candidate(
        statement_type=stype,
        page_number=page_number,
        score=merged_score,
        source="+".join(sorted(set(all_sources))),
        matched_features=all_features,
        reasoning=f"Merged from {len(group)} signals: {', '.join(sorted(set(all_sources)))}",
    )
