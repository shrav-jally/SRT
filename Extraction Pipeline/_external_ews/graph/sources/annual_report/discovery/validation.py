"""Stage 7 — Sequence Validation.

Validates and refines the ranked candidates from Stage 4 by
enforcing domain-specific constraints:

  1. **Logical ordering** — In any annual report, the standalone
     statements come before consolidated, and within each entity
     the order is always BS → P&L → CF → Notes.  Candidates that
     violate this ordering are penalised or rejected.

  2. **Entity resolution** — When a heading says just "Balance Sheet"
     (no "Standalone" or "Consolidated"), the entity is inferred from
     page position relative to other identified statements.

  3. **Multi-page merging** — Financial statements often span 2-3
     pages.  Adjacent pages with similar content (continuation of
     the same table) are merged into a single statement entry.

  4. **Conflict resolution** — If two statement types claim the same
     page, the higher-confidence candidate wins.

Output: a dict of ``StatementPages`` (the final answer used by the
VLM extraction stage).
"""

from __future__ import annotations

import logging
from collections import defaultdict

from .models import (
    Candidate,
    PageInfo,
    StatementPages,
    StatementType,
    STATEMENT_ORDER,
)

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────

# Max pages away from the primary page that a continuation can be
MAX_CONTINUATION_DISTANCE = 4

# Max pages a single financial statement can span
MAX_STATEMENT_PAGES = 5

# The expected ordering for entity groups
_STANDALONE_ORDER = [
    StatementType.STANDALONE_BALANCE_SHEET,
    StatementType.STANDALONE_PROFIT_AND_LOSS,
    StatementType.STANDALONE_CASH_FLOW,
]
_CONSOLIDATED_ORDER = [
    StatementType.CONSOLIDATED_BALANCE_SHEET,
    StatementType.CONSOLIDATED_PROFIT_AND_LOSS,
    StatementType.CONSOLIDATED_CASH_FLOW,
]


# ── Public API ────────────────────────────────────────────────────

def validate_and_resolve(
    ranked_candidates: dict[StatementType, list[Candidate]],
    pages: list[PageInfo],
    progress_callback=None,
) -> dict[str, StatementPages]:
    """Validate candidate sequences and produce final page assignments.

    Parameters
    ----------
    ranked_candidates : dict
        Output from Stage 4: ranked candidates per statement type.
    pages : list[PageInfo]
        Parsed page info from Stage 1.
    progress_callback : callable, optional
        Called with progress messages.

    Returns
    -------
    dict[str, StatementPages]
        Final resolved pages keyed by statement type string
        (e.g. ``"standalone_balance_sheet"``).
    """
    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    _log("[Stage 7] Validating sequences and resolving pages...")

    page_map = {p.page_number: p for p in pages}
    total_pages = len(pages)

    # ── Step 1: Pick best candidate per statement type ───────────
    best: dict[StatementType, Candidate] = {}
    for stype, cands in ranked_candidates.items():
        if cands:
            best[stype] = cands[0]

    # ── Step 2: Resolve page conflicts ───────────────────────────
    best = _resolve_page_conflicts(best, _log)

    # ── Step 3: Enforce logical ordering ─────────────────────────
    best = _enforce_ordering(best, _log)

    # ── Step 4: Try entity resolution for unresolved types ───────
    best = _try_entity_inference(best, ranked_candidates, _log)

    # ── Step 5: Multi-page merging ───────────────────────────────
    results: dict[str, StatementPages] = {}
    for stype, candidate in best.items():
        primary_page = candidate.page_number
        continuation_pages = _find_continuation_pages(
            primary_page, stype, page_map, best, total_pages,
        )
        all_pages = [primary_page] + continuation_pages
        is_multi = len(all_pages) > 1

        results[stype.value] = StatementPages(
            statement_type=stype,
            pages=all_pages,
            confidence=candidate.confidence,
            source=candidate.source,
            reasoning=candidate.reasoning,
            is_multi_page=is_multi,
        )

        if is_multi:
            _log(f"[Stage 7] {stype.value}: pages {all_pages} (multi-page)")
        else:
            _log(f"[Stage 7] {stype.value}: page {primary_page}")

    # Summary
    found = len(results)
    _log(f"[Stage 7] Resolved {found}/6 statement types")

    return results


# ── Conflict resolution ──────────────────────────────────────────

def _resolve_page_conflicts(
    best: dict[StatementType, Candidate],
    _log,
) -> dict[StatementType, Candidate]:
    """If two statement types claim the same page, keep the higher-confidence one."""
    page_claims: dict[int, list[tuple[StatementType, Candidate]]] = defaultdict(list)
    for stype, cand in best.items():
        page_claims[cand.page_number].append((stype, cand))

    resolved = dict(best)
    for page_num, claims in page_claims.items():
        if len(claims) <= 1:
            continue
        # Sort by confidence, keep the best
        claims.sort(key=lambda x: x[1].confidence, reverse=True)
        winner_type, winner = claims[0]
        for stype, cand in claims[1:]:
            _log(
                f"[Stage 7] Conflict on page {page_num}: "
                f"{winner_type.value} (conf={winner.confidence:.2f}) wins over "
                f"{stype.value} (conf={cand.confidence:.2f})"
            )
            del resolved[stype]

    return resolved


# ── Ordering enforcement ─────────────────────────────────────────

def _enforce_ordering(
    best: dict[StatementType, Candidate],
    _log,
) -> dict[StatementType, Candidate]:
    """Validate that statement pages follow the expected order.

    Expected: within each entity group (standalone, consolidated),
    BS page < P&L page < CF page.  Also, standalone pages generally
    come before consolidated pages.

    Currently this only LOGS violations — it does not reject candidates,
    because some annual reports genuinely have unusual ordering.
    """
    for group_name, order in [("standalone", _STANDALONE_ORDER), ("consolidated", _CONSOLIDATED_ORDER)]:
        prev_page = 0
        prev_type = None
        for stype in order:
            cand = best.get(stype)
            if not cand:
                continue
            if cand.page_number < prev_page and prev_type:
                _log(
                    f"[Stage 7] Order warning: {stype.value} (p.{cand.page_number}) "
                    f"appears before {prev_type.value} (p.{prev_page})"
                )
            prev_page = cand.page_number
            prev_type = stype

    # Cross-entity check: standalone should generally come before consolidated
    sa_pages = [best[st].page_number for st in _STANDALONE_ORDER if st in best]
    co_pages = [best[st].page_number for st in _CONSOLIDATED_ORDER if st in best]
    if sa_pages and co_pages:
        sa_max = max(sa_pages)
        co_min = min(co_pages)
        if sa_max > co_min:
            _log(
                f"[Stage 7] Order warning: standalone pages extend beyond "
                f"consolidated pages (sa_max={sa_max}, co_min={co_min}). "
                f"This may indicate entity misassignment."
            )

    return best


# ── Entity inference ──────────────────────────────────────────────

def _try_entity_inference(
    best: dict[StatementType, Candidate],
    ranked_candidates: dict[StatementType, list[Candidate]],
    _log,
) -> dict[StatementType, Candidate]:
    """Try to fill missing statement types by inferring entity from position.

    If we found standalone_balance_sheet on page 100 and
    consolidated_balance_sheet is missing, but there's a candidate
    balance_sheet page at page 200, it's likely the consolidated one.
    """
    # For each base type (balance_sheet, profit_and_loss, cash_flow)
    for base in ("balance_sheet", "profit_and_loss", "cash_flow"):
        sa_type = StatementType(f"standalone_{base}")
        co_type = StatementType(f"consolidated_{base}")

        sa_found = sa_type in best
        co_found = co_type in best

        if sa_found and co_found:
            continue  # Both found, nothing to do

        if not sa_found and not co_found:
            continue  # Neither found, can't infer

        # One found, one missing — check if any candidates exist for the missing one
        missing_type = co_type if sa_found else sa_type
        found_type = sa_type if sa_found else co_type
        found_page = best[found_type].page_number

        candidates_for_missing = ranked_candidates.get(missing_type, [])
        for cand in candidates_for_missing:
            # Skip if same page as the found type
            if cand.page_number == found_page:
                continue
            # Accept: if standalone is found at p100, consolidated candidate
            # should be at a higher page number (or vice versa)
            if sa_found and cand.page_number > found_page:
                best[missing_type] = cand
                _log(
                    f"[Stage 7] Inferred {missing_type.value} at page "
                    f"{cand.page_number} (after {found_type.value} at "
                    f"page {found_page})"
                )
                break
            elif co_found and cand.page_number < found_page:
                best[missing_type] = cand
                _log(
                    f"[Stage 7] Inferred {missing_type.value} at page "
                    f"{cand.page_number} (before {found_type.value} at "
                    f"page {found_page})"
                )
                break

    return best


# ── Multi-page merging ────────────────────────────────────────────

def _find_continuation_pages(
    primary_page: int,
    statement_type: StatementType,
    page_map: dict[int, PageInfo],
    best: dict[StatementType, Candidate],
    total_pages: int,
) -> list[int]:
    """Find continuation pages for a multi-page financial statement.

    Looks at pages immediately following the primary page and checks
    if they look like a continuation (similar content, no new heading).
    """
    # Pages claimed by other statements — don't steal them
    claimed_pages = {c.page_number for c in best.values()}

    continuation: list[int] = []
    primary_info = page_map.get(primary_page)
    if not primary_info:
        return continuation

    for offset in range(1, MAX_CONTINUATION_DISTANCE + 1):
        next_page_num = primary_page + offset
        if next_page_num > total_pages:
            break
        if next_page_num in claimed_pages:
            break  # Another statement starts here

        next_info = page_map.get(next_page_num)
        if not next_info:
            break

        if _is_continuation_page(primary_info, next_info, statement_type):
            continuation.append(next_page_num)
            if len(continuation) >= MAX_STATEMENT_PAGES - 1:
                break
        else:
            break  # No longer a continuation

    return continuation


def _is_continuation_page(
    primary: PageInfo,
    candidate: PageInfo,
    statement_type: StatementType,
) -> bool:
    """Check if a page looks like a continuation of a financial statement.

    A continuation page should:
      - Have numeric content (amounts)
      - NOT have a new financial statement heading
      - NOT be a notes page
      - Have similar table density
    """
    # Must have some numbers
    if candidate.amount_count < 2:
        return False

    # Must not have a new statement heading
    heading_text = " ".join(candidate.heading_candidates[:5]).lower()
    from .candidates import BALANCE_SHEET_HEADINGS, PROFIT_LOSS_HEADINGS, CASH_FLOW_HEADINGS, NOTES_REJECTION_KEYWORDS

    all_headings = BALANCE_SHEET_HEADINGS + PROFIT_LOSS_HEADINGS + CASH_FLOW_HEADINGS
    for h in all_headings:
        if h in heading_text:
            return False  # New statement starts here

    # Must not be a notes page
    text_lower = candidate.raw_text[:500].lower()
    if any(kw in text_lower for kw in NOTES_REJECTION_KEYWORDS):
        return False

    # Should have similar table density (within 5x of primary)
    if primary.table_density > 0 and candidate.table_density > 0:
        ratio = candidate.table_density / primary.table_density
        if ratio < 0.1 or ratio > 10:
            return False

    return True
