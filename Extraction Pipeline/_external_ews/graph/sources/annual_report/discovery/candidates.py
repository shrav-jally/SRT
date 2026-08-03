"""Stage 3 — Candidate Page Generation.

Casts a wide net to identify pages that *might* contain each of the
six target financial statements.  Uses multiple independent signals:

  1. **PDF Bookmarks/Outlines** — instant, 100% accurate when present
  2. **Table of Contents parsing** — reuses existing ``toc_parser.py``
  3. **Heading detection** — matches known heading variations in the
     first few lines of each page
  4. **Financial keyword density** — pages dense in financial terms
  5. **Content-based section headings** — characteristic section markers
     like "ASSETS", "EQUITY AND LIABILITIES", "OPERATING ACTIVITIES"

Each source produces ``Candidate`` objects that are forwarded to
Stage 4 (Scoring) for confidence ranking.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .models import (
    Candidate,
    PageInfo,
    ScoreBreakdown,
    StatementType,
)

logger = logging.getLogger(__name__)


# ===================================================================
# Heading variation lists
# ===================================================================

# Comprehensive list of Balance Sheet heading variations
BALANCE_SHEET_HEADINGS: list[str] = [
    "balance sheet",
    "statement of financial position",
    "balance sheet as at",
    "statement of assets and liabilities",
    # Indian / Ind AS
    "standalone balance sheet",
    "consolidated balance sheet",
    "standalone statement of financial position",
    "consolidated statement of financial position",
]

# Comprehensive list of Profit & Loss heading variations
PROFIT_LOSS_HEADINGS: list[str] = [
    "profit and loss",
    "profit & loss",
    "statement of profit and loss",
    "statement of profit & loss",
    "statement of profit or loss",
    "profit and loss account",
    "profit & loss account",
    "income statement",
    "statement of income",
    "statement of comprehensive income",
    "statement of operations",
    # Indian / Ind AS
    "standalone statement of profit and loss",
    "consolidated statement of profit and loss",
    "standalone statement of profit & loss",
    "consolidated statement of profit & loss",
    "standalone profit and loss",
    "consolidated profit and loss",
]

# Comprehensive list of Cash Flow heading variations
CASH_FLOW_HEADINGS: list[str] = [
    "cash flow statement",
    "cash flow",
    "statement of cash flows",
    "statement of cash flow",
    "cash flows",
    # Indian / Ind AS
    "standalone cash flow statement",
    "consolidated cash flow statement",
    "standalone statement of cash flows",
    "consolidated statement of cash flows",
]

# Section headings that confirm statement type
BS_SECTION_KEYWORDS = [
    "equity and liabilities",
    "shareholders' funds",
    "non-current assets",
    "current assets",
    "non-current liabilities",
    "current liabilities",
    "total equity and liabilities",
    "total assets",
    "share capital",
    "reserves and surplus",
]

PL_SECTION_KEYWORDS = [
    "revenue from operations",
    "other income",
    "total revenue",
    "total income",
    "total expenses",
    "profit before tax",
    "profit after tax",
    "profit for the year",
    "profit for the period",
    "earnings per share",
    "basic earnings per share",
    "diluted earnings per share",
    "cost of materials consumed",
    "employee benefit expense",
    "employee benefits expense",
    "depreciation and amortisation",
    "depreciation and amortization",
    "finance costs",
    "other expenses",
]

CF_SECTION_KEYWORDS = [
    "operating activities",
    "investing activities",
    "financing activities",
    "cash flows from operating",
    "cash flows from investing",
    "cash flows from financing",
    "cash flow from operating",
    "cash flow from investing",
    "cash flow from financing",
    "net increase in cash",
    "net decrease in cash",
    "cash and cash equivalents at the beginning",
    "cash and cash equivalents at the end",
]

# Notes page keywords (for rejection)
NOTES_REJECTION_KEYWORDS = [
    "notes forming part of",
    "notes to the financial",
    "notes on financial statements",
    "notes accompanying the",
    "significant accounting policies",
    "statement of changes in equity",
    "changes in equity",
]


# ===================================================================
# Bookmark-based candidate generation
# ===================================================================

def _candidates_from_bookmarks(
    bookmarks: list[dict[str, Any]],
) -> list[Candidate]:
    """Generate candidates from PDF bookmarks/outlines.

    PDF bookmarks give exact page numbers with near 100% accuracy.
    """
    candidates: list[Candidate] = []

    for bm in bookmarks:
        title = bm.get("title", "")
        page = bm.get("page", 0)
        if not title or page < 1:
            continue

        title_lower = title.lower().strip()

        # Skip notes/equity bookmarks
        if any(kw in title_lower for kw in NOTES_REJECTION_KEYWORDS):
            continue

        matched_type = _match_heading_to_statement(title_lower)
        if not matched_type:
            continue

        score = ScoreBreakdown(bookmark_score=1.0, heading_score=1.0)
        candidates.append(Candidate(
            statement_type=matched_type,
            page_number=page,
            score=score,
            source="bookmark",
            matched_features=[f"bookmark: {title}"],
            reasoning=f"PDF bookmark '{title}' on page {page}",
        ))

    if candidates:
        logger.info(f"[Stage 3] Bookmarks: {len(candidates)} candidate(s)")
    return candidates


# ===================================================================
# TOC-based candidate generation
# ===================================================================

def _candidates_from_toc(
    pdf_path,
    pages: list[PageInfo],
    progress_callback=None,
) -> list[Candidate]:
    """Generate candidates from Table of Contents parsing.

    Reuses the existing ``toc_parser.py`` module.
    """
    import sys
    from pathlib import Path

    # Import the existing TOC parser
    graph_dir = str(Path(__file__).resolve().parent.parent.parent)
    if graph_dir not in sys.path:
        sys.path.insert(0, graph_dir)

    from sources.annual_report.toc_parser import parse_toc_for_page_hints

    # Convert PageInfo list to the format toc_parser expects
    page_dicts = [{"page": p.page_number, "text": p.raw_text} for p in pages]

    toc_result = parse_toc_for_page_hints(
        pdf_path, page_dicts, progress_callback=progress_callback,
    )

    candidates: list[Candidate] = []
    if not toc_result.hints:
        logger.info("[Stage 3] TOC: no hints found")
        return candidates

    for stype_str, page_list in toc_result.hints.items():
        try:
            stype = StatementType(stype_str)
        except ValueError:
            continue

        for page_num in page_list:
            score = ScoreBreakdown(toc_score=1.0)
            candidates.append(Candidate(
                statement_type=stype,
                page_number=page_num,
                score=score,
                source="toc",
                matched_features=[f"toc_hint: {stype_str} -> page {page_num}"],
                reasoning=f"Table of Contents references {stype_str} near page {page_num}",
            ))

    logger.info(f"[Stage 3] TOC: {len(candidates)} candidate(s)")
    return candidates


# ===================================================================
# Heading-based candidate generation
# ===================================================================

def _candidates_from_headings(
    pages: list[PageInfo],
) -> list[Candidate]:
    """Generate candidates by scanning page headings for statement titles.

    Checks the first ~10 lines of each page for heading matches.
    Also verifies the page has enough numeric content to be a real
    financial statement (filters out director's reports mentioning
    "balance sheet" in prose).
    """
    candidates: list[Candidate] = []

    for page in pages:
        # Skip pages with very little text
        if page.word_count < 20:
            continue

        # Check heading candidates (first N lines)
        heading_text = " ".join(page.heading_candidates).lower()

        # Skip notes pages
        if any(kw in heading_text for kw in NOTES_REJECTION_KEYWORDS):
            continue

        matched_type = _match_heading_to_statement(heading_text)
        if not matched_type:
            continue

        # Quality gate: need some numbers on the page
        if page.amount_count < 3:
            continue

        # Quality gate: need at least one section heading
        section_score = _compute_section_heading_score(page, matched_type)
        if section_score < 0.3:
            continue

        score = ScoreBreakdown(
            heading_score=1.0,
            section_heading_score=section_score,
            numeric_density_score=min(page.numeric_density * 5, 1.0),
            table_structure_score=min(page.amount_count / 10, 1.0),
        )

        # Check for date header
        if page.date_count >= 2:
            score.date_header_score = 1.0

        candidates.append(Candidate(
            statement_type=matched_type,
            page_number=page.page_number,
            score=score,
            source="heading",
            matched_features=[f"heading match on page {page.page_number}"],
            reasoning=f"Heading detection matched {matched_type.value}",
        ))

    logger.info(f"[Stage 3] Headings: {len(candidates)} candidate(s)")
    return candidates


# ===================================================================
# Content-based candidate generation
# ===================================================================

def _candidates_from_content(
    pages: list[PageInfo],
    existing_types: set[StatementType] | None = None,
) -> list[Candidate]:
    """Generate candidates by analyzing page content for financial keywords.

    This is a fallback for pages where headings aren't detectable
    (e.g. scanned pages with partial OCR, or unusual heading formats).
    Only searches for statement types not already found.
    """
    existing = existing_types or set()
    candidates: list[Candidate] = []

    # Map statement types to their section keywords
    type_keywords: dict[StatementType, list[str]] = {}

    # Only search for types we haven't found yet
    bs_types = [StatementType.STANDALONE_BALANCE_SHEET, StatementType.CONSOLIDATED_BALANCE_SHEET]
    pl_types = [StatementType.STANDALONE_PROFIT_AND_LOSS, StatementType.CONSOLIDATED_PROFIT_AND_LOSS]
    cf_types = [StatementType.STANDALONE_CASH_FLOW, StatementType.CONSOLIDATED_CASH_FLOW]

    for st in bs_types:
        if st not in existing:
            type_keywords[st] = BS_SECTION_KEYWORDS
    for st in pl_types:
        if st not in existing:
            type_keywords[st] = PL_SECTION_KEYWORDS
    for st in cf_types:
        if st not in existing:
            type_keywords[st] = CF_SECTION_KEYWORDS

    if not type_keywords:
        return candidates

    for page in pages:
        if page.word_count < 20 or page.amount_count < 3:
            continue

        text_lower = page.raw_text.lower()

        # Skip notes pages
        if any(kw in text_lower for kw in NOTES_REJECTION_KEYWORDS):
            continue

        for stype, keywords in type_keywords.items():
            # Count how many section keywords appear
            keyword_hits = sum(1 for kw in keywords if kw in text_lower)
            if keyword_hits < 3:
                continue

            # Determine entity from text
            is_consolidated = "consolidated" in text_lower[:500]
            is_standalone = "standalone" in text_lower[:500]

            # Skip if entity doesn't match
            if "consolidated" in stype.value and is_standalone and not is_consolidated:
                continue
            if "standalone" in stype.value and is_consolidated and not is_standalone:
                continue

            keyword_score = min(keyword_hits / 5, 1.0)
            score = ScoreBreakdown(
                keyword_score=keyword_score,
                numeric_density_score=min(page.numeric_density * 5, 1.0),
                table_structure_score=min(page.amount_count / 10, 1.0),
            )

            candidates.append(Candidate(
                statement_type=stype,
                page_number=page.page_number,
                score=score,
                source="content",
                matched_features=[f"content: {keyword_hits} keywords for {stype.value}"],
                reasoning=f"Content analysis found {keyword_hits} financial keywords",
            ))

    logger.info(f"[Stage 3] Content: {len(candidates)} candidate(s)")
    return candidates


# ===================================================================
# Master candidate generator
# ===================================================================

def generate_candidates(
    pdf_path,
    pages: list[PageInfo],
    bookmarks: list[dict[str, Any]],
    progress_callback=None,
) -> list[Candidate]:
    """Run all candidate generation strategies and merge results.

    Priority order:
      1. PDF Bookmarks (highest reliability)
      2. TOC parsing
      3. Heading detection
      4. Content-based detection (fallback)

    Returns all candidates; Stage 4 handles deduplication and scoring.
    """
    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    _log("[Stage 3] Generating candidates...")

    all_candidates: list[Candidate] = []

    # 1. Bookmarks
    bm_candidates = _candidates_from_bookmarks(bookmarks)
    all_candidates.extend(bm_candidates)

    # 2. TOC
    toc_candidates = _candidates_from_toc(pdf_path, pages, progress_callback)
    all_candidates.extend(toc_candidates)

    # 3. Headings
    heading_candidates = _candidates_from_headings(pages)
    all_candidates.extend(heading_candidates)

    # 4. Content (only for types not already found by 1-3)
    found_types = {c.statement_type for c in all_candidates if c.confidence > 0.3}
    content_candidates = _candidates_from_content(pages, found_types)
    all_candidates.extend(content_candidates)

    # 5. Targeted VLM Fallback for corrupted pages in the TOC zone
    vlm_candidates = _candidates_from_vlm(pdf_path, pages, toc_candidates, progress_callback)
    all_candidates.extend(vlm_candidates)

    _log(f"  [Stage 3] Total candidates: {len(all_candidates)}")
    return all_candidates


def _candidates_from_vlm(
    pdf_path,
    pages: list[PageInfo],
    toc_candidates: list[Candidate],
    progress_callback=None
) -> list[Candidate]:
    """Uses VLM to classify corrupted pages that fall within TOC boundaries."""
    from .vlm_classifier import classify_pages_with_vlm

    candidates = []
    
    # 1. Identify corrupted pages that are in the TOC list
    toc_page_nums = {c.page_number for c in toc_candidates}
    corrupted_pages_to_check = []
    
    for p in pages:
        if p.is_corrupted and p.page_number in toc_page_nums:
            corrupted_pages_to_check.append(p.page_number)
            
    if not corrupted_pages_to_check:
        return candidates
        
    if progress_callback:
        progress_callback(f"  [Stage 3] VLM Fallback checking {len(corrupted_pages_to_check)} corrupted pages...")
        
    # 2. Call VLM
    classifications = classify_pages_with_vlm(pdf_path, corrupted_pages_to_check)
    
    # 3. Create candidates for positive identifications
    for page_num, stype in classifications.items():
        if stype:
            score = ScoreBreakdown(vlm_score=1.0)
            candidates.append(Candidate(
                statement_type=stype,
                page_number=page_num,
                score=score,
                source="vlm_fallback",
                reasoning="VLM classification on corrupted page"
            ))
            
    return candidates


# ===================================================================
# Helpers
# ===================================================================

def _match_heading_to_statement(heading_text: str) -> StatementType | None:
    """Match heading text to a StatementType.

    Checks heading variations and determines standalone/consolidated
    entity based on keywords in the text.
    """
    heading_lower = heading_text.lower()

    is_consolidated = "consolidated" in heading_lower
    # Default to standalone unless explicitly consolidated
    entity_prefix = "consolidated" if is_consolidated else "standalone"

    # Check Balance Sheet
    for h in BALANCE_SHEET_HEADINGS:
        if h in heading_lower:
            return StatementType(f"{entity_prefix}_balance_sheet")

    # Check P&L
    for h in PROFIT_LOSS_HEADINGS:
        if h in heading_lower:
            return StatementType(f"{entity_prefix}_profit_and_loss")

    # Check Cash Flow
    for h in CASH_FLOW_HEADINGS:
        if h in heading_lower:
            return StatementType(f"{entity_prefix}_cash_flow")

    return None


def _compute_section_heading_score(
    page: PageInfo, statement_type: StatementType,
) -> float:
    """Compute how many expected section headings appear on the page."""
    text_lower = page.raw_text.lower()

    if "balance_sheet" in statement_type.value:
        keywords = BS_SECTION_KEYWORDS
    elif "profit_and_loss" in statement_type.value:
        keywords = PL_SECTION_KEYWORDS
    elif "cash_flow" in statement_type.value:
        keywords = CF_SECTION_KEYWORDS
    else:
        return 0.0

    hits = sum(1 for kw in keywords if kw in text_lower)
    # Need at least 2 hits for a reasonable score
    if hits < 2:
        return 0.0
    return min(hits / 4, 1.0)
