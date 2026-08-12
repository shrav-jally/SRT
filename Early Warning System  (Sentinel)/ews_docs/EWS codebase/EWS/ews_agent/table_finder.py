"""
Table Finder Module

Identifies which pages in an annual report PDF contain the key financial
statements: Balance Sheet, Profit & Loss, and Cash Flow.

Strategy (LLM-first with deterministic validation):
    1. QUICK DETERMINISTIC CHECK: Optimization for highly standard cases
       (exact "Standalone Balance Sheet as at March 31" titles). If all 3
       statements found with high confidence, skip LLM (cost optimization).
    2. LLM PAGE IDENTIFICATION (PRIMARY): Send page snippets to LLM which
       identifies BS/P&L/CF pages and statement type (Standalone/Consolidated).
       LLM understands context, abbreviations, and non-standard titles that
       regex patterns may miss.
    3. DETERMINISTIC VALIDATION (SECONDARY): Validate LLM results against
       title patterns and content indicators. Add any pages found by
       deterministic methods but missed by LLM (e.g., continuation pages).
    4. CONTINUATION EXPANSION: Expand page lists to include continuation
       pages (deterministic — looks for "(continued)" and content matches).
    5. NOTES PAGE DETECTION: Broad search for Notes to Accounts pages
       (deterministic — regex-based).

    If LLM is unavailable, falls back to full deterministic scan:
    title scan → full-page scan → content-based detection.

Fully automatic — no manual page input required.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import pdfplumber

logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class FinancialStatementPages:
    """Identified pages for each financial statement."""
    balance_sheet: list[int] = field(default_factory=list)
    profit_and_loss: list[int] = field(default_factory=list)
    cash_flow: list[int] = field(default_factory=list)
    changes_in_equity: list[int] = field(default_factory=list)
    notes_pages: list[int] = field(default_factory=list)  # Notes to Accounts pages

    # Metadata
    detection_method: str = "unknown"  # "llm_primary", "deterministic_fallback", "hybrid", "title", "content"
    confidence: float = 0.0
    statement_type: str = "Not specified"  # "Standalone" or "Consolidated" (detected by LLM or deterministic)

    @property
    def all_pages(self) -> list[int]:
        """All identified financial statement pages (sorted, unique)."""
        pages = set()
        pages.update(self.balance_sheet)
        pages.update(self.profit_and_loss)
        pages.update(self.cash_flow)
        pages.update(self.changes_in_equity)
        pages.update(self.notes_pages)
        return sorted(pages)

    @property
    def is_complete(self) -> bool:
        """Check if all three main statements were found."""
        return bool(self.balance_sheet and self.profit_and_loss and self.cash_flow)


# ============================================================================
# TITLE PATTERNS
# ============================================================================

# STRICT patterns — checked line-by-line against the title area (first 10 lines).
# These are the standard Schedule III titles used in Indian annual reports.
# IMPORTANT: Each line is checked individually. A match is only considered a
# TITLE if it appears at or near the START of the line (not mid-sentence).
# This prevents false positives from references like "Refer to the Balance Sheet".
TITLE_PATTERNS = {
    "balance_sheet": [
        # With "Standalone" / "Consolidated" prefix (very specific)
        r"standalone\s+balance\s+sheet",
        r"consolidated\s+balance\s+sheet",
        # Standard Schedule III format with "as at" context
        r"balance\s+sheet\s+as\s+at\s+\d",
        r"balance\s+sheet\s+as\s+at",
        # Simple form — must be at start of line (checked via position validation)
        r"balance\s+sheet\b",
        # Dated form — very specific, unlikely to be a reference
        r"balance\s+sheet\s*(?:as\s+at)?\s*\d{1,2}\s*(?:st|nd|rd|th)?\s*(?:january|february|march|april|may|june|july|august|september|october|november|december)",
        # Alternative naming (very specific)
        r"statement\s+of\s+financial\s+position",
        r"statement\s+of\s+assets\s+and\s+liabilities",
    ],
    "profit_and_loss": [
        # With "Standalone" / "Consolidated" prefix (very specific)
        r"standalone\s+statement\s+of\s+profit\s+(?:and|&)\s+loss",
        r"consolidated\s+statement\s+of\s+profit\s+(?:and|&)\s+loss",
        # Standard Schedule III format
        r"statement\s+of\s+profit\s+(?:and|&)\s+loss\s+for",
        r"statement\s+of\s+profit\s+(?:and|&)\s+loss",
        # Simple form — position-validated
        r"profit\s+(?:and|&)\s+loss\s+(?:statement|account)\s+for",
        r"profit\s+(?:and|&)\s+loss\s+(?:statement|account)\b",
        r"profit\s+(?:and|&)\s+loss\b",
        # Alternative naming (very specific)
        r"statement\s+of\s+comprehensive\s+income",
        r"income\s+statement\s+for",
        r"income\s+statement\b",
        r"statement\s+of\s+income\s+for",
        r"statement\s+of\s+income\b",
    ],
    "cash_flow": [
        # With "Standalone" / "Consolidated" prefix (very specific)
        r"standalone\s+(?:statement\s+of\s+)?cash\s+flows?",
        r"consolidated\s+(?:statement\s+of\s+)?cash\s+flows?",
        # Standard Schedule III format
        r"statement\s+of\s+cash\s+flows?\s+for",
        r"statement\s+of\s+cash\s+flows?\s+ended",
        r"statement\s+of\s+cash\s+flows?\b",
        # Simple form — position-validated
        r"cash\s+flows?\s+statement\s+for",
        r"cash\s+flows?\s+statement\b",
        r"cash\s+flows?\b",
        r"cash\s+flow\s+(?:statement|for)\b",
        # Alternative naming
        r"statement\s+of\s+changes\s+in\s+cash",
    ],
    "changes_in_equity": [
        r"standalone\s+statement\s+of\s+changes?\s+in\s+equity",
        r"consolidated\s+statement\s+of\s+changes?\s+in\s+equity",
        r"statement\s+of\s+changes?\s+in\s+equity\s+for",
        r"statement\s+of\s+changes?\s+in\s+equity\b",
        r"changes?\s+in\s+equity\s+(?:statement|for)",
        r"statement\s+of\s+shareholders?\s+equity",
    ],
}

# LENIENT patterns — checked against the first 30% of page text as a fallback.
# These require MORE context than the strict patterns to avoid false positives
# from references like "Refer to the Balance Sheet" or "As per Cash Flow Statement".
# Only used in Pass 2 when Pass 1 (title-area scan) is incomplete.
LENIENT_TITLE_PATTERNS = {
    "balance_sheet": [
        # Requires "standalone"/"consolidated" prefix OR "as at" context
        r"(?:standalone|consolidated)\s+balance\s+sheet",
        r"balance\s+sheet\s+as\s+at",
    ],
    "profit_and_loss": [
        # Requires "statement of" prefix or "standalone"/"consolidated"
        r"(?:standalone|consolidated)\s+(?:statement\s+of\s+)?profit\s+(?:and|&)\s+loss",
        r"statement\s+of\s+profit\s+(?:and|&)\s+loss",
        r"statement\s+of\s+comprehensive\s+income",
    ],
    "cash_flow": [
        # Requires "statement of" prefix or "standalone"/"consolidated"
        r"(?:standalone|consolidated)\s+(?:statement\s+of\s+)?cash\s+flows?",
        r"statement\s+of\s+cash\s+flows?",
    ],
    "changes_in_equity": [
        r"(?:standalone|consolidated)\s+statement\s+of\s+changes?\s+in\s+equity",
        r"statement\s+of\s+changes?\s+in\s+equity",
    ],
}

# Consolidated versions (fallback if standalone not found)
CONSOLIDATED_TITLE_PATTERNS = {
    "balance_sheet": [r"consolidated\s+balance\s+sheet"],
    "profit_and_loss": [r"consolidated\s+statement\s+of\s+profit\s+(?:and|&)\s+loss", r"consolidated\s+profit\s+(?:and|&)\s+loss"],
    "cash_flow": [r"consolidated\s+(?:statement\s+of\s+)?cash\s+flows?", r"consolidated\s+cash\s+flows?\s+statement"],
    "changes_in_equity": [r"consolidated\s+statement\s+of\s+changes?\s+in\s+equity"],
}

# Notes page title patterns — if these appear as the PRIMARY title (first
# FEW lines) of a page, the page is a Notes page, NOT a primary financial
# statement. We use a smaller line limit for this check to avoid being
# over-aggressive in excluding pages.
NOTES_TITLE_PATTERNS = [
    r"notes?\s+to\s+(?:the\s+)?(?:standalone|consolidated)\s+financial\s+statements?",
    r"notes?\s+to\s+(?:the\s+)?financial\s+statements?",
    r"significant\s+accounting\s+policies",
    r"auditors?\s*[''']?\s*report",  # Handles "Auditor's Report", "Auditors' Report", "Auditor Report"
    r"independent\s+auditors?\s*[''']?\s*report",  # "Independent Auditors' Report"
    r"directors?\s+report",
    r"management\s+report",
    r"corporate\s+governance",
    r"business\s+responsibility",
    r"annual\s+general\s+meeting",
    r"notice\s+of\s+annual",
]

# Line limit for checking if a page is a Notes/other page (NOT a statement).
# This is intentionally SMALLER than TITLE_LINE_LIMIT so we only exclude
# pages where the notes title is the PRIMARY content at the very top.
# A page with "Balance Sheet" on line 3 and "Notes to Financial Statements"
# on line 15 should NOT be excluded.
NOTES_EXCLUSION_LINE_LIMIT = 5

# Continuation page indicators
CONTINUATION_PATTERNS = [
    r"\(continued\)",
    r"continued\)",
    r"\bcontd\.?\b",
    r"\bcont\b",
]

# Number of lines from the top of the page to check for titles.
# Kept at 10 — titles should appear in the first 10 lines. Lines 11-20
# are body text that may mention statement names in passing (references),
# which must NOT be mistaken for titles.
TITLE_LINE_LIMIT = 10

# Number of pages to look ahead for continuation pages.
# Kept at 4 — going beyond 4 pages risks including unrelated content.
CONTINUATION_LOOK_AHEAD = 4

# Maximum position (as fraction of line length) where a title pattern match
# can start and still be considered a title (not a reference).
# E.g., if match starts at position 20 in a 100-char line (0.2), it's a title.
# If it starts at position 60 (0.6), it's likely a reference like
# "Refer to the Balance Sheet on page 47".
TITLE_MATCH_MAX_POS_RATIO = 0.4

# Maximum line length for a line to be considered a title line without
# position validation. Short lines (≤ 70 chars) containing a pattern
# match are almost always titles, not references.
TITLE_MATCH_SHORT_LINE_LIMIT = 70


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _get_title_area(text: str, line_limit: int = TITLE_LINE_LIMIT) -> str:
    """Extract the first N lines of a page (the title area)."""
    lines = text.split('\n')
    return '\n'.join(lines[:line_limit])


def _line_contains_title(line: str, patterns: list[str]) -> bool:
    """
    Check if a single line contains a financial statement TITLE.
    
    A match is only considered a TITLE (not a reference) if:
    1. The match starts within the first few characters of the line, OR
    2. The line is short (≤ TITLE_MATCH_SHORT_LINE_LIMIT chars), OR
    3. The match starts within the first TITLE_MATCH_MAX_POS_RATIO of the line.
    
    This prevents false positives from lines like:
    - "Refer to the Balance Sheet on page 47"  (match too far into line)
    - "As per the Cash Flow Statement, the company..."  (match too far)
    While allowing true titles like:
    - "Balance Sheet"  (short line, match at start)
    - "Godrej Properties Limited Balance Sheet"  (match within first 40%)
    - "Standalone Statement of Profit and Loss"  (match at start)
    """
    line_stripped = line.strip()
    if not line_stripped:
        return False
    line_lower = line_stripped.lower()
    line_len = len(line_lower)
    
    for pattern in patterns:
        match = re.search(pattern, line_lower)
        if match:
            match_start = match.start()
            # Title if match is at/near start of line
            if match_start <= 5:
                return True
            # Title if line is short (titles are usually short lines)
            if line_len <= TITLE_MATCH_SHORT_LINE_LIMIT:
                return True
            # Title if match is in first 40% of line (allows company name prefix)
            if line_len > 0 and match_start / line_len <= TITLE_MATCH_MAX_POS_RATIO:
                return True
            # Otherwise, this is likely a reference, not a title
    
    return False


def _page_has_statement_title(text: str, stmt_type: str, consolidated: bool = False) -> bool:
    """
    Check if page text contains a title for the given statement type.
    
    Checks the first TITLE_LINE_LIMIT lines INDIVIDUALLY. Each line is
    validated to ensure the pattern match is a TITLE (at/near start of line)
    and not a REFERENCE (mid-sentence mention like "Refer to the Balance Sheet").
    """
    lines = text.split('\n')[:TITLE_LINE_LIMIT]
    patterns = TITLE_PATTERNS.get(stmt_type, [])
    if consolidated:
        patterns = CONSOLIDATED_TITLE_PATTERNS.get(stmt_type, [])
    
    for line in lines:
        if _line_contains_title(line, patterns):
            return True
    return False


def _page_has_statement_title_fullpage(text: str, stmt_type: str) -> bool:
    """
    Check if the first 30% of page text contains a lenient title pattern.
    
    This is a fallback for cases where the title is pushed down by
    company headers, decorative elements, or unusual formatting.
    Uses LENIENT_TITLE_PATTERNS which require more context than strict patterns.
    
    Only checks the first 30% of the page to avoid false positives from
    references that appear later in the page text.
    Each line is validated using _line_contains_title().
    """
    lines = text.split('\n')
    check_limit = max(TITLE_LINE_LIMIT, int(len(lines) * 0.3))
    check_lines = lines[:check_limit]
    
    patterns = LENIENT_TITLE_PATTERNS.get(stmt_type, [])
    
    for line in check_lines:
        if _line_contains_title(line, patterns):
            return True
    return False


def _page_has_notes_title(text: str) -> bool:
    """
    Check if a page has a Notes/other title as its PRIMARY title.
    
    Only checks the first NOTES_EXCLUSION_LINE_LIMIT lines (5 lines)
    to avoid being over-aggressive in excluding pages. A page that
    has a financial statement title in the first few lines should
    NOT be excluded even if "Notes" appears lower on the page.
    """
    title_area = _get_title_area(text, line_limit=NOTES_EXCLUSION_LINE_LIMIT).lower()
    for pattern in NOTES_TITLE_PATTERNS:
        if re.search(pattern, title_area):
            return True
    return False


def _page_is_continuation(text: str) -> bool:
    """Check if a page is a continuation of a previous statement."""
    title_area = _get_title_area(text).lower()
    for pattern in CONTINUATION_PATTERNS:
        if re.search(pattern, title_area):
            return True
    return False


def _detect_statement_type_from_content(text: str) -> Optional[str]:
    """
    Detect which financial statement a page belongs to based on its
    content (section headers, line items).
    
    Uses a scoring system with many indicators. Returns the statement
    type with the highest score if it meets the minimum threshold.
    """
    text_lower = text.lower()

    bs_indicators = [
        "equity and liabilities", "total equity and liabilities",
        "non-current assets", "current assets",
        "non-current liabilities", "current liabilities",
        "total assets", "total equity",
        "property plant and equipment", "property, plant",
        "capital work-in-progress", "capital work in progress",
        "inventories", "trade receivables", "cash and cash equivalents",
        "borrowings", "trade payables", "other equity",
        "deferred tax assets", "deferred tax liabilities",
        "as at march", "as at april",
    ]
    bs_count = sum(1 for ind in bs_indicators if ind in text_lower)

    pl_indicators = [
        "revenue from operations", "total income",
        "total expenses", "profit before tax",
        "profit for the year", "tax expense",
        "earnings per equity share", "other income",
        "employee benefits expense", "finance costs",
        "depreciation and amortisation", "other expenses",
        "cost of materials consumed", "purchases of stock-in-trade",
        "profit/(loss)", "profit before exceptional",
    ]
    pl_count = sum(1 for ind in pl_indicators if ind in text_lower)

    cf_indicators = [
        "cash flows from operating activities",
        "cash flows from investing activities",
        "cash flows from financing activities",
        "cash flow from operating",
        "cash flow from investing",
        "cash flow from financing",
        "net cash from operating",
        "net cash from investing",
        "net cash from financing",
        "net increase in cash", "net decrease in cash",
        "cash and cash equivalents",
    ]
    cf_count = sum(1 for ind in cf_indicators if ind in text_lower)

    scores = {
        "balance_sheet": bs_count,
        "profit_and_loss": pl_count,
        "cash_flow": cf_count,
    }

    best = max(scores, key=scores.get)
    # Lower threshold (2 instead of 3) to be more inclusive
    if scores[best] >= 2:
        return best
    return None


def _content_score_for_statement(text: str, stmt_type: str) -> float:
    """
    Score how likely a page belongs to a given statement type based
    on content analysis. Returns a score from 0.0 to 1.0.
    
    This is used for content-based detection when title patterns fail.
    """
    text_lower = text.lower()
    
    if stmt_type == "balance_sheet":
        strong_indicators = [
            "equity and liabilities", "total equity and liabilities",
            "non-current assets", "current assets",
            "non-current liabilities", "current liabilities",
            "total assets",
        ]
        weak_indicators = [
            "property plant", "inventories", "trade receivables",
            "cash and cash equivalents", "borrowings", "trade payables",
            "other equity", "deferred tax", "capital work",
            "as at march", "as at april",
        ]
    elif stmt_type == "profit_and_loss":
        strong_indicators = [
            "revenue from operations", "profit before tax",
            "profit for the year", "total income",
        ]
        weak_indicators = [
            "other income", "employee benefits", "finance costs",
            "depreciation", "other expenses", "tax expense",
            "earnings per", "cost of materials", "total expenses",
            "profit/(loss)",
        ]
    elif stmt_type == "cash_flow":
        strong_indicators = [
            "cash flows from operating",
            "cash flows from investing",
            "cash flows from financing",
        ]
        weak_indicators = [
            "net cash from", "net cash flow",
            "cash and cash equivalents",
            "operating activities", "investing activities",
            "financing activities",
        ]
    else:
        return 0.0
    
    strong_count = sum(1 for ind in strong_indicators if ind in text_lower)
    weak_count = sum(1 for ind in weak_indicators if ind in text_lower)
    
    # Strong indicators count more
    score = (strong_count * 0.25) + (weak_count * 0.08)
    return min(1.0, score)


# ============================================================================
# TITLE-BASED PAGE SCANNER
# ============================================================================


def find_financial_pages_title(
    pdf: pdfplumber.PDF,
) -> FinancialStatementPages:
    """
    Find financial statement pages using a multi-pass approach.
    
    Pass 1: Title-area scan (first 20 lines) with strict patterns.
    Pass 2: Full-page scan with lenient patterns (if Pass 1 incomplete).
    Pass 3: Content-based detection (if Pass 2 still incomplete).
    
    Over-inclusive by design — better to include extra pages and let
    the extraction/mapping stages filter out irrelevant data than to
    miss real financial statements at the detection stage.
    
    Args:
        pdf: Open pdfplumber PDF object.

    Returns:
        FinancialStatementPages with detected pages.
    """
    result = FinancialStatementPages()
    result.detection_method = "title"

    # ========================================================================
    # Pass 1: Title-area scan (first TITLE_LINE_LIMIT lines)
    # ========================================================================
    title_pages: dict[str, list[int]] = {
        "balance_sheet": [],
        "profit_and_loss": [],
        "cash_flow": [],
        "changes_in_equity": [],
    }

    for use_consolidated in [False, True]:
        title_pages = {k: [] for k in title_pages}

        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if not text.strip():
                continue

            page_num = i + 1

            # Skip pages that have a Notes/other title as their PRIMARY title
            # (only checks first 5 lines to avoid over-exclusion)
            if _page_has_notes_title(text):
                continue

            for stmt_type in title_pages:
                if _page_has_statement_title(text, stmt_type, consolidated=use_consolidated):
                    title_pages[stmt_type].append(page_num)

        # Check if we found all three main statements
        found_all = all(title_pages.get(st) for st in ["balance_sheet", "profit_and_loss", "cash_flow"])

        if found_all:
            label = "consolidated" if use_consolidated else "standalone"
            logger.info(f"Pass 1 (title-area): Found all three {label} financial statement title pages")
            break

        if not use_consolidated:
            standalone_title_pages = dict(title_pages)
        else:
            # Merge: use standalone where found, consolidated as fallback
            for stmt_type in title_pages:
                if not standalone_title_pages.get(stmt_type) and title_pages.get(stmt_type):
                    logger.info(f"Using consolidated pages for {stmt_type}: {title_pages[stmt_type]}")
                elif standalone_title_pages.get(stmt_type):
                    title_pages[stmt_type] = standalone_title_pages[stmt_type]

    logger.info(
        f"Pass 1 (title-area): BS={title_pages['balance_sheet']}, "
        f"P&L={title_pages['profit_and_loss']}, CF={title_pages['cash_flow']}"
    )

    # ========================================================================
    # Pass 2: Full-page scan with lenient patterns (if incomplete)
    # ========================================================================
    missing = [st for st in ["balance_sheet", "profit_and_loss", "cash_flow"] if not title_pages.get(st)]
    
    if missing:
        logger.info(f"Pass 1 incomplete — missing: {missing}. Running Pass 2 (full-page scan)...")
        
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if not text.strip():
                continue

            page_num = i + 1

            # Skip pages already found
            already_found = any(page_num in title_pages[st] for st in title_pages)
            if already_found:
                continue

            # Skip pages with Notes title in first few lines
            if _page_has_notes_title(text):
                continue

            for stmt_type in missing:
                if _page_has_statement_title_fullpage(text, stmt_type):
                    title_pages[stmt_type].append(page_num)
                    logger.info(
                        f"Pass 2 (full-page): Found {stmt_type} on page {page_num}"
                    )

        # Re-check completeness
        still_missing = [st for st in ["balance_sheet", "profit_and_loss", "cash_flow"] if not title_pages.get(st)]
        if still_missing:
            logger.info(f"Pass 2 still missing: {still_missing}")
        else:
            logger.info("Pass 2 (full-page): Found all three statements")

    # ========================================================================
    # Pass 3: Content-based detection (if still incomplete)
    # ========================================================================
    still_missing = [st for st in ["balance_sheet", "profit_and_loss", "cash_flow"] if not title_pages.get(st)]
    
    if still_missing:
        logger.info(f"Pass 2 incomplete — missing: {still_missing}. Running Pass 3 (content-based)...")
        result.detection_method = "content"
        
        # Scan pages in the financial section of the PDF (30%-85% of pages)
        total_pages = len(pdf.pages)
        scan_start = max(0, int(total_pages * 0.25))
        scan_end = min(total_pages, int(total_pages * 0.90))
        
        # Score each page for each missing statement type
        page_scores: dict[str, list[tuple[int, float]]] = {st: [] for st in still_missing}
        
        for i in range(scan_start, scan_end):
            page = pdf.pages[i]
            text = page.extract_text() or ""
            if not text.strip():
                continue
            
            page_num = i + 1
            
            # Skip pages already found for other statements
            already_found = any(page_num in title_pages[st] for st in title_pages)
            if already_found:
                continue
            
            # Skip pages with Notes title
            if _page_has_notes_title(text):
                continue
            
            for stmt_type in still_missing:
                score = _content_score_for_statement(text, stmt_type)
                if score >= 0.3:  # Minimum threshold for content-based detection
                    page_scores[stmt_type].append((page_num, score))
        
        # For each missing type, take the top-scoring pages
        for stmt_type in still_missing:
            if page_scores[stmt_type]:
                # Sort by score descending
                page_scores[stmt_type].sort(key=lambda x: x[1], reverse=True)
                
                # Take the best page and any nearby pages with decent scores
                best_page, best_score = page_scores[stmt_type][0]
                title_pages[stmt_type].append(best_page)
                logger.info(
                    f"Pass 3 (content): Found {stmt_type} on page {best_page} "
                    f"(content score={best_score:.2f})"
                )
                
                # Also include pages with score >= 0.5 that are within 3 pages
                # of the best page (likely continuation pages)
                for pg, sc in page_scores[stmt_type][1:]:
                    if sc >= 0.5 and abs(pg - best_page) <= 3:
                        title_pages[stmt_type].append(pg)
                        logger.info(
                            f"Pass 3 (content): Added nearby {stmt_type} page {pg} "
                            f"(score={sc:.2f})"
                        )

    # ========================================================================
    # Phase 2: Expand to include continuation pages
    # ========================================================================
    for stmt_type, pages in title_pages.items():
        if not pages:
            continue

        expanded = set(pages)
        last_page = max(pages)
        total_pages = len(pdf.pages)

        for offset in range(1, CONTINUATION_LOOK_AHEAD + 1):
            next_page = last_page + offset
            if next_page > total_pages:
                break

            page = pdf.pages[next_page - 1]
            text = page.extract_text() or ""

            # Stop if this page has a title for a DIFFERENT financial statement
            if is_different := any(
                _page_has_statement_title(text, other_type)
                for other_type in title_pages
                if other_type != stmt_type
            ):
                break

            # Stop if this page has a Notes title as its PRIMARY title
            if _page_has_notes_title(text):
                break

            # Include if it says "continued" in title area
            if _page_is_continuation(text):
                expanded.add(next_page)
                last_page = next_page
                continue

            # Include if content type matches the statement type
            detected_type = _detect_statement_type_from_content(text)
            if detected_type == stmt_type:
                expanded.add(next_page)
                last_page = next_page
                continue

            # Include if the page has STRONG content indicators (score >= 0.5)
            # This is stricter than before (was 0.4) to avoid including
            # unrelated pages that happen to have some financial keywords
            content_score = _content_score_for_statement(text, stmt_type)
            if content_score >= 0.5:
                expanded.add(next_page)
                last_page = next_page
                logger.debug(
                    f"Included page {next_page} as continuation of {stmt_type} "
                    f"(content score={content_score:.2f})"
                )
            else:
                # No strong indicators — stop looking for continuations
                break

        setattr(result, stmt_type, sorted(expanded))

    # Set confidence
    found_count = sum(1 for stmt in ["balance_sheet", "profit_and_loss", "cash_flow"]
                      if getattr(result, stmt))
    result.confidence = found_count / 3.0

    logger.info(
        f"Title scan found: BS={result.balance_sheet}, "
        f"P&L={result.profit_and_loss}, CF={result.cash_flow}, "
        f"CoE={result.changes_in_equity}, confidence={result.confidence:.1%}"
    )

    return result


# ============================================================================
# QUICK DETERMINISTIC CHECK (cost optimization for highly standard cases)
# ============================================================================


def _quick_deterministic_check(pdf: pdfplumber.PDF) -> FinancialStatementPages:
    """
    Quick deterministic check for highly standard Indian annual reports.

    This is a COST OPTIMIZATION — if the PDF uses standard Schedule III
    titles (e.g., "Standalone Balance Sheet as at March 31, 2024"), we
    can find all 3 statements without an LLM call, saving time and money.

    Only checks the title area (first 10 lines) with strict patterns.
    Does NOT do full-page scan or content-based detection (those are
    done later as validation if LLM is used).

    Returns:
        FinancialStatementPages with detection_method="quick_deterministic"
        if all 3 found, or partial results otherwise.
    """
    result = FinancialStatementPages()
    result.detection_method = "quick_deterministic"

    title_pages: dict[str, list[int]] = {
        "balance_sheet": [],
        "profit_and_loss": [],
        "cash_flow": [],
        "changes_in_equity": [],
    }

    for use_consolidated in [False, True]:
        title_pages = {k: [] for k in title_pages}

        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if not text.strip():
                continue

            page_num = i + 1

            if _page_has_notes_title(text):
                continue

            for stmt_type in title_pages:
                if _page_has_statement_title(text, stmt_type, consolidated=use_consolidated):
                    title_pages[stmt_type].append(page_num)

        found_all = all(title_pages.get(st) for st in ["balance_sheet", "profit_and_loss", "cash_flow"])
        if found_all:
            label = "consolidated" if use_consolidated else "standalone"
            logger.info(f"Quick deterministic check: Found all three {label} statements")
            break

        if not use_consolidated:
            standalone_title_pages = dict(title_pages)
        else:
            for stmt_type in title_pages:
                if not standalone_title_pages.get(stmt_type) and title_pages.get(stmt_type):
                    logger.info(f"Using consolidated pages for {stmt_type}: {title_pages[stmt_type]}")
                elif standalone_title_pages.get(stmt_type):
                    title_pages[stmt_type] = standalone_title_pages[stmt_type]

    for stmt_type, pages in title_pages.items():
        setattr(result, stmt_type, sorted(pages))

    found_count = sum(1 for stmt in ["balance_sheet", "profit_and_loss", "cash_flow"]
                      if getattr(result, stmt))
    result.confidence = found_count / 3.0

    # Detect statement type from found pages
    if result.balance_sheet or result.profit_and_loss or result.cash_flow:
        all_found = list(set(result.balance_sheet + result.profit_and_loss + result.cash_flow))
        standalone_count = 0
        consolidated_count = 0
        for pg in all_found[:6]:
            if pg > len(pdf.pages) or pg < 1:
                continue
            page = pdf.pages[pg - 1]
            text = page.extract_text() or ""
            title_area = '\n'.join(text.split('\n')[:10]).lower()
            if 'standalone' in title_area:
                standalone_count += 1
            elif 'consolidated' in title_area:
                consolidated_count += 1
        if standalone_count > consolidated_count:
            result.statement_type = "Standalone"
        elif consolidated_count > standalone_count:
            result.statement_type = "Consolidated"
        else:
            result.statement_type = "Standalone"  # Default

    logger.info(
        f"Quick deterministic: BS={result.balance_sheet}, "
        f"P&L={result.profit_and_loss}, CF={result.cash_flow}, "
        f"type={result.statement_type}, confidence={result.confidence:.1%}"
    )

    return result


# ============================================================================
# LLM-BASED PAGE IDENTIFICATION (PRIMARY method)
# ============================================================================


def find_pages_by_llm(
    pdf: pdfplumber.PDF,
    llm,
    hint_pages: Optional[FinancialStatementPages] = None,
) -> FinancialStatementPages:
    """
    Use LLM to identify financial statement pages (PRIMARY method).

    The LLM receives page snippets and identifies which pages contain
    BS/P&L/CF statements. It also detects the statement type
    (Standalone vs Consolidated).

    This is the PRIMARY page-finding method because:
    - LLM understands context and non-standard titles
    - LLM handles abbreviations and CID-fragmented text
    - LLM can distinguish "Balance Sheet" title from references
    - LLM detects statement type in the same call (no extra cost)

    Args:
        pdf: Open pdfplumber PDF object.
        llm: LangChain ChatOpenAI instance.
        hint_pages: Optional partial results from quick deterministic check
                    (used to provide context to LLM about already-found pages).

    Returns:
        FinancialStatementPages with LLM-identified pages and statement type.
    """
    if llm is None:
        logger.warning("No LLM provided for page identification")
        return FinancialStatementPages()

    from ews_agent.llm_utils import llm_call_with_retry, extract_json_from_response

    total_pages = len(pdf.pages)

    # Sample pages: every 2nd page in the financial section (25%-90%)
    # Plus all pages from hint_pages and their neighbors
    scan_start = max(1, int(total_pages * 0.15))
    scan_end = min(total_pages, int(total_pages * 0.95))

    sample_pages = set()
    # Dense sampling in the financial section
    for pg in range(scan_start, scan_end + 1, 2):
        sample_pages.add(pg)
    # Also sample first few pages (table of contents, etc.)
    for pg in range(1, min(6, total_pages + 1)):
        sample_pages.add(pg)

    # Add hint pages and their neighbors
    if hint_pages:
        for pg in hint_pages.all_pages:
            for offset in range(-3, 6):
                sample_pages.add(pg + offset)

    sample_pages = sorted(p for p in sample_pages if 1 <= p <= total_pages)

    # Build page snippets for the prompt
    page_summaries = []
    for pg in sample_pages:
        page = pdf.pages[pg - 1]
        text = page.extract_text() or ""
        snippet = text[:400].replace("\n", " | ")
        page_summaries.append(f"Page {pg}: {snippet}")

    # Build hint context if available
    hint_context = ""
    if hint_pages and (hint_pages.balance_sheet or hint_pages.profit_and_loss or hint_pages.cash_flow):
        hint_context = f"""
DETERMINISTIC HINT (preliminary scan found these pages — use as guidance):
- Balance Sheet: {hint_pages.balance_sheet or 'not found'}
- Profit & Loss: {hint_pages.profit_and_loss or 'not found'}
- Cash Flow: {hint_pages.cash_flow or 'not found'}
- Statement type hint: {hint_pages.statement_type}

IMPORTANT: These are HINTS only. Verify each page and add any pages the
deterministic scan may have missed (e.g., continuation pages, non-standard titles).
"""

    prompt = f"""You are analyzing an Indian company annual report PDF. Identify which pages contain the financial statements.

Below are text snippets from selected pages of a {total_pages}-page PDF.
{hint_context}
PAGE SNIPPETS:
{chr(10).join(page_summaries)}

Respond in this exact JSON format:
{{
    "balance_sheet": [page_numbers],
    "profit_and_loss": [page_numbers],
    "cash_flow": [page_numbers],
    "changes_in_equity": [page_numbers],
    "statement_type": "Standalone" or "Consolidated",
    "confidence": "high" or "medium" or "low"
}}

Rules:
- Page numbers are 1-indexed
- Include ALL pages that are part of each statement (including continuation pages marked "continued")
- If a statement is not found, use an empty list []
- Look for titles like "Standalone Balance Sheet", "Consolidated Balance Sheet", "Statement of Profit and Loss", "Statement of Cash Flows"
- Also look for simple titles like "Balance Sheet", "Profit and Loss", "Cash Flow Statement"
- Prefer STANDALONE statements over consolidated (but if only consolidated is available, use that)
- A page saying "(continued)" after a statement is part of that statement
- Do NOT include Notes to Accounts pages
- Detect whether the statements are "Standalone" or "Consolidated" based on the page titles
- When in doubt, INCLUDE the page rather than exclude it (over-inclusive is better than missing pages)"""

    try:
        response = llm_call_with_retry(llm, prompt, max_retries=2)
        if not response:
            logger.warning("LLM page identification: no response received")
            return FinancialStatementPages()

        parsed = extract_json_from_response(response)
        if not parsed:
            logger.warning("LLM page identification: could not parse JSON response")
            return FinancialStatementPages()

        result = FinancialStatementPages()
        result.detection_method = "llm_primary"

        for stmt_type in ["balance_sheet", "profit_and_loss", "cash_flow", "changes_in_equity"]:
            llm_pages = parsed.get(stmt_type, [])
            if isinstance(llm_pages, list):
                llm_pages = [int(p) for p in llm_pages if isinstance(p, (int, float)) and 1 <= p <= total_pages]
            else:
                llm_pages = []
            setattr(result, stmt_type, sorted(llm_pages))

        # Extract statement type from LLM response
        llm_stmt_type = parsed.get("statement_type", "")
        if isinstance(llm_stmt_type, str):
            llm_stmt_type_lower = llm_stmt_type.lower()
            if "consolidated" in llm_stmt_type_lower:
                result.statement_type = "Consolidated"
            elif "standalone" in llm_stmt_type_lower:
                result.statement_type = "Standalone"
            else:
                result.statement_type = "Standalone"  # Default
        else:
            result.statement_type = "Standalone"  # Default

        # Set confidence
        found_count = sum(1 for stmt in ["balance_sheet", "profit_and_loss", "cash_flow"]
                          if getattr(result, stmt))
        result.confidence = found_count / 3.0

        llm_confidence = parsed.get("confidence", "low")
        logger.info(
            f"LLM page identification (PRIMARY): BS={result.balance_sheet}, "
            f"P&L={result.profit_and_loss}, CF={result.cash_flow}, "
            f"CoE={result.changes_in_equity}, "
            f"type={result.statement_type}, "
            f"llm_confidence={llm_confidence}, "
            f"result_confidence={result.confidence:.1%}"
        )

        return result

    except Exception as e:
        logger.error(f"LLM page identification failed: {e}")
        return FinancialStatementPages()


# ============================================================================
# DETERMINISTIC VALIDATION (validates LLM results, adds missed pages)
# ============================================================================


def _validate_with_deterministic(
    pdf: pdfplumber.PDF,
    llm_result: FinancialStatementPages,
) -> FinancialStatementPages:
    """
    Validate LLM-identified pages against deterministic methods.

    This is the SECONDARY step after LLM page identification. It:
    1. Validates each LLM-identified page has financial statement content
    2. Adds pages found by deterministic methods but missed by LLM
       (e.g., continuation pages, pages with standard titles)
    3. Expands page lists to include continuation pages
    4. Cross-validates statement type against page titles

    The deterministic validation CANNOT remove pages found by LLM
    (LLM may see content that regex patterns miss), but it CAN add
    pages that LLM missed.

    Args:
        pdf: Open pdfplumber PDF object.
        llm_result: Pages identified by LLM.

    Returns:
        FinancialStatementPages with validated and expanded page lists.
    """
    result = FinancialStatementPages()
    result.detection_method = "llm_primary_validated"
    result.statement_type = llm_result.statement_type

    # Step 1: Run full deterministic scan for comparison
    det_result = find_financial_pages_title(pdf)

    # Step 2: Merge — LLM pages + deterministic pages (union, not intersection)
    # LLM is primary but deterministic can add missed pages
    for stmt_type in ["balance_sheet", "profit_and_loss", "cash_flow", "changes_in_equity"]:
        llm_pages = set(getattr(llm_result, stmt_type))
        det_pages = set(getattr(det_result, stmt_type))

        # Pages found by either method
        merged = sorted(llm_pages | det_pages)

        # Log what deterministic added
        added_by_det = det_pages - llm_pages
        if added_by_det:
            logger.info(
                f"Deterministic validation added {len(added_by_det)} pages "
                f"to {stmt_type} that LLM missed: {sorted(added_by_det)}"
            )

        # Log what LLM found that deterministic didn't
        llm_only = llm_pages - det_pages
        if llm_only:
            logger.info(
                f"LLM found {len(llm_only)} pages for {stmt_type} that "
                f"deterministic missed: {sorted(llm_only)} (keeping — LLM is primary)"
            )

        setattr(result, stmt_type, merged)

    # Step 3: Expand to include continuation pages
    for stmt_type in ["balance_sheet", "profit_and_loss", "cash_flow", "changes_in_equity"]:
        pages = getattr(result, stmt_type)
        if not pages:
            continue

        expanded = set(pages)
        last_page = max(pages)
        total_pages = len(pdf.pages)

        for offset in range(1, CONTINUATION_LOOK_AHEAD + 1):
            next_page = last_page + offset
            if next_page > total_pages:
                break

            page = pdf.pages[next_page - 1]
            text = page.extract_text() or ""

            # Stop if this page has a title for a DIFFERENT financial statement
            if any(
                _page_has_statement_title(text, other_type)
                for other_type in ["balance_sheet", "profit_and_loss", "cash_flow", "changes_in_equity"]
                if other_type != stmt_type
            ):
                break

            # Stop if this page has a Notes title as its PRIMARY title
            if _page_has_notes_title(text):
                break

            # Include if it says "continued" in title area
            if _page_is_continuation(text):
                expanded.add(next_page)
                last_page = next_page
                continue

            # Include if content type matches the statement type
            detected_type = _detect_statement_type_from_content(text)
            if detected_type == stmt_type:
                expanded.add(next_page)
                last_page = next_page
                continue

            # Include if the page has STRONG content indicators
            content_score = _content_score_for_statement(text, stmt_type)
            if content_score >= 0.5:
                expanded.add(next_page)
                last_page = next_page
                logger.debug(
                    f"Included page {next_page} as continuation of {stmt_type} "
                    f"(content score={content_score:.2f})"
                )
            else:
                break

        setattr(result, stmt_type, sorted(expanded))

    # Step 4: Cross-validate statement type
    # If LLM said "Standalone" but deterministic found only consolidated pages, correct it
    det_type = det_result.statement_type if hasattr(det_result, 'statement_type') else "Not specified"
    if result.statement_type != det_type and det_type != "Not specified":
        # Check if deterministic found explicit type indicators
        all_result_pages = set()
        for stmt_type in ["balance_sheet", "profit_and_loss", "cash_flow"]:
            all_result_pages.update(getattr(result, stmt_type))

        standalone_count = 0
        consolidated_count = 0
        for pg in list(all_result_pages)[:6]:
            if pg > len(pdf.pages) or pg < 1:
                continue
            page = pdf.pages[pg - 1]
            text = page.extract_text() or ""
            title_area = '\n'.join(text.split('\n')[:10]).lower()
            if 'standalone' in title_area:
                standalone_count += 1
            elif 'consolidated' in title_area:
                consolidated_count += 1

        if consolidated_count > standalone_count and consolidated_count >= 2:
            logger.info(
                f"Statement type correction: LLM said '{result.statement_type}' but "
                f"deterministic validation found {consolidated_count} consolidated vs "
                f"{standalone_count} standalone pages — correcting to 'Consolidated'"
            )
            result.statement_type = "Consolidated"
        elif standalone_count > consolidated_count and standalone_count >= 2:
            logger.info(
                f"Statement type correction: LLM said '{result.statement_type}' but "
                f"deterministic validation found {standalone_count} standalone vs "
                f"{consolidated_count} consolidated pages — correcting to 'Standalone'"
            )
            result.statement_type = "Standalone"

    # Set confidence
    found_count = sum(1 for stmt in ["balance_sheet", "profit_and_loss", "cash_flow"]
                      if getattr(result, stmt))
    result.confidence = found_count / 3.0

    logger.info(
        f"Validated result: BS={result.balance_sheet}, "
        f"P&L={result.profit_and_loss}, CF={result.cash_flow}, "
        f"CoE={result.changes_in_equity}, type={result.statement_type}, "
        f"confidence={result.confidence:.1%}"
    )

    return result


# ============================================================================
# NOTES PAGE FINDER
# ============================================================================


# Patterns that identify the START of the Notes to Accounts section.
# These appear as page titles in Indian annual reports.
NOTES_START_PATTERNS = [
    r"notes?\s+to\s+(?:the\s+)?(?:standalone|consolidated)\s+financial\s+statements?",
    r"notes?\s+to\s+(?:the\s+)?financial\s+statements?",
    r"notes?\s+forming\s+part\s+of\s+(?:the\s+)?financial\s+statements?",
    r"notes?\s+to\s+(?:the\s+)?accounts?",
    r"significant\s+accounting\s+policies\s+and\s+notes",
    r"notes?\s+on\s+financial\s+statements?",
    # Additional patterns for broader matching
    r"notes?\s+(?:forming\s+part\s+of\s+)?(?:the\s+)?accounts?",
    r"schedule\s+of\s+notes?",
    r"notes?\s+and\s+accounting\s+policies",
    r"accounting\s+policies\s+and\s+notes?",
    r"notes?\s+to\s+(?:the\s+)?above",
    r"significant\s+accounting\s+policies",
    r"summary\s+of\s+significant\s+accounting\s+policies",
    r"notes?\s+1\s*[:.]\s+(?:company|overview|corporate)",
]

# Patterns that indicate the END of the Notes section (a different section starts).
# When we encounter a page with one of these titles, we stop including notes pages.
NOTES_END_PATTERNS = [
    r"auditors?\s*[''']?\s*report",
    r"independent\s+auditors?\s*[''']?\s*report",
    r"directors?\s+report",
    r"corporate\s+governance",
    r"management\s+discussion\s+and\s+analysis",
    r"business\s+responsibility",
    r"annual\s+general\s+meeting",
    r"notice\s+of\s+annual",
    r"shareholders?\s+information",
    r"financial\s+highlights",
    r"additional\s+shareholders?\s+information",
    # Additional end patterns
    r"report\s+on\s+corporate\s+governance",
    r"remuneration\s+of\s+directors?",
    r"related\s+party\s+transactions?\s+statement",
    r"secretarial\s+audit\s+report",
]


def find_notes_pages(
    pdf: pdfplumber.PDF,
    financial_pages: FinancialStatementPages,
) -> list[int]:
    """
    Find Notes to Accounts pages in an annual report PDF.
    
    Strategy (broad search to not miss anything):
        1. Find the first page with a "Notes to Financial Statements" title
           (search both title area AND full page text)
        2. Include all subsequent pages until hitting a non-notes section
           (Auditor's Report, Director's Report, etc.)
        3. Search a wide range: 60 pages forward, 50 pages backward
        4. Allow up to 120 pages of notes (some reports have very long notes)
    
    The notes section typically starts AFTER the primary financial statements
    (BS, P&L, CF) and before the Auditor's Report or other annexures.
    
    Args:
        pdf: Open pdfplumber PDF object.
        financial_pages: Already-identified financial statement pages (to know
            where the statements end).

    Returns:
        List of 1-indexed page numbers for the Notes to Accounts section.
    """
    total_pages = len(pdf.pages)
    
    # Determine the earliest page after which to look for notes
    # Notes typically start after the last financial statement page
    all_stmt_pages = set()
    for attr in ['balance_sheet', 'profit_and_loss', 'cash_flow', 'changes_in_equity']:
        all_stmt_pages.update(getattr(financial_pages, attr, []))
    
    # Start searching from the page after the last financial statement
    search_start = max(all_stmt_pages) + 1 if all_stmt_pages else int(total_pages * 0.25)
    search_start = max(1, search_start)
    
    # Phase 1: Find the first notes page
    # Search forward up to 60 pages from the last statement
    notes_start = None
    forward_search_limit = min(total_pages, search_start + 60)
    
    for i in range(search_start - 1, forward_search_limit):
        page = pdf.pages[i]
        text = page.extract_text() or ""
        
        # Check title area first (most reliable)
        title_area = _get_title_area(text).lower()
        
        for pattern in NOTES_START_PATTERNS:
            if re.search(pattern, title_area):
                notes_start = i + 1  # 1-indexed
                logger.info(
                    f"Found Notes to Accounts starting at page {notes_start}: "
                    f"'{title_area.strip()[:80]}'"
                )
                break
        
        if notes_start:
            break
        
        # Also check full page text (catches notes titles pushed down by headers)
        text_lower = text.lower()
        for pattern in NOTES_START_PATTERNS:
            if re.search(pattern, text_lower):
                notes_start = i + 1
                logger.info(
                    f"Found Notes to Accounts (full-page scan) at page {notes_start}: "
                    f"'{text_lower[:80]}'"
                )
                break
        
        if notes_start:
            break
    
    if not notes_start:
        # Fallback: also check pages BEFORE the financial statements
        # (some reports put notes before the statements)
        # Search backward up to 50 pages
        backward_search_start = max(0, search_start - 50)
        
        for i in range(backward_search_start, search_start - 1):
            page = pdf.pages[i]
            text = page.extract_text() or ""
            title_area = _get_title_area(text).lower()
            
            for pattern in NOTES_START_PATTERNS:
                if re.search(pattern, title_area):
                    notes_start = i + 1
                    logger.info(
                        f"Found Notes to Accounts (before statements) at page {notes_start}"
                    )
                    break
            
            if notes_start:
                break
        
        # Also try full-page scan backward
        if not notes_start:
            for i in range(backward_search_start, search_start - 1):
                page = pdf.pages[i]
                text = page.extract_text() or ""
                text_lower = text.lower()
                
                for pattern in NOTES_START_PATTERNS:
                    if re.search(pattern, text_lower):
                        notes_start = i + 1
                        logger.info(
                            f"Found Notes to Accounts (full-page backward) at page {notes_start}"
                        )
                        break
                
                if notes_start:
                    break
    
    if not notes_start:
        # Last resort: scan the entire PDF for notes start patterns
        logger.info("Broad search: scanning entire PDF for Notes to Accounts...")
        for i in range(total_pages):
            page = pdf.pages[i]
            text = page.extract_text() or ""
            text_lower = text.lower()
            
            for pattern in NOTES_START_PATTERNS:
                if re.search(pattern, text_lower):
                    # Make sure this isn't a page already identified as a statement
                    page_num = i + 1
                    if page_num not in all_stmt_pages:
                        notes_start = page_num
                        logger.info(
                            f"Found Notes to Accounts (full PDF scan) at page {notes_start}"
                        )
                        break
            
            if notes_start:
                break
    
    if not notes_start:
        logger.info("Could not find Notes to Accounts section")
        return []
    
    # Phase 2: Include all pages from notes_start until we hit an end pattern
    notes_pages = []
    max_notes_pages = 120  # Increased from 80 — some reports have very long notes
    
    for i in range(notes_start - 1, min(total_pages, notes_start + max_notes_pages)):
        page = pdf.pages[i]
        text = page.extract_text() or ""
        title_area = _get_title_area(text, line_limit=NOTES_EXCLUSION_LINE_LIMIT).lower()
        
        # Check if this page starts a different section (end of notes)
        # Only check first few lines to avoid stopping prematurely
        is_end = False
        for pattern in NOTES_END_PATTERNS:
            if re.search(pattern, title_area):
                is_end = True
                logger.info(
                    f"Notes section ends at page {i + 1}: '{title_area.strip()[:80]}'"
                )
                break
        
        if is_end:
            break
        
        # Check if this page starts a primary financial statement (also ends notes)
        # Only check title area, not full page
        is_statement = False
        for stmt_type in ["balance_sheet", "profit_and_loss", "cash_flow"]:
            if _page_has_statement_title(text, stmt_type):
                is_statement = True
                break
        
        if is_statement:
            break
        
        notes_pages.append(i + 1)  # 1-indexed
    
    logger.info(
        f"Found {len(notes_pages)} Notes to Accounts pages: "
        f"{notes_pages[:5]}...{notes_pages[-3:] if len(notes_pages) > 5 else ''}"
    )
    
    return notes_pages


# ============================================================================
# MAIN ENTRY POINT (LLM-first with deterministic validation)
# ============================================================================


def find_financial_statements(
    pdf_path: str,
    llm=None,
    use_llm: bool = True,
) -> FinancialStatementPages:
    """
    Find financial statement pages in an annual report PDF.

    Fully automatic — no manual page input required.

    LLM-first strategy:
        1. QUICK DETERMINISTIC CHECK: If all 3 statements found with standard
           Schedule III titles, skip LLM (cost optimization for highly standard
           cases). This saves an LLM call for ~70% of Indian annual reports.
        2. LLM PAGE IDENTIFICATION (PRIMARY): Send page snippets to LLM which
           identifies BS/P&L/CF pages AND statement type (Standalone/Consolidated).
           LLM understands context, abbreviations, and non-standard titles.
        3. DETERMINISTIC VALIDATION (SECONDARY): Validate LLM results against
           title patterns and content indicators. Add any pages found by
           deterministic methods but missed by LLM. Expand continuation pages.
        4. NOTES PAGE DETECTION: Broad search for Notes to Accounts pages
           (deterministic — regex-based).

    If LLM is unavailable (llm=None or use_llm=False), falls back to
    full deterministic scan: title scan → full-page scan → content-based.

    Args:
        pdf_path: Path to the PDF file.
        llm: LangChain ChatOpenAI instance for LLM page identification.
        use_llm: Whether to use LLM as primary page finder.

    Returns:
        FinancialStatementPages with detected page numbers and statement type.
    """
    pdf = pdfplumber.open(pdf_path)
    try:
        if use_llm and llm is not None:
            # ============================================================
            # LLM-FIRST PATH
            # ============================================================

            # Step 1: Quick deterministic check (cost optimization)
            quick_result = _quick_deterministic_check(pdf)

            if quick_result.is_complete and quick_result.confidence >= 1.0:
                # All 3 statements found with standard titles — skip LLM
                logger.info(
                    "Quick deterministic check found all 3 statements with high confidence "
                    "— skipping LLM page identification (cost optimization)"
                )
                quick_result.detection_method = "quick_deterministic"
                result = quick_result
            else:
                # Step 2: LLM page identification (PRIMARY)
                logger.info("Using LLM as PRIMARY page finder...")
                hint = (
                    quick_result
                    if quick_result.balance_sheet or quick_result.profit_and_loss or quick_result.cash_flow
                    else None
                )
                llm_result = find_pages_by_llm(pdf, llm, hint_pages=hint)

                if not llm_result.balance_sheet and not llm_result.profit_and_loss and not llm_result.cash_flow:
                    # LLM failed completely — fall back to full deterministic
                    logger.warning(
                        "LLM page identification returned no results — "
                        "falling back to full deterministic scan"
                    )
                    result = find_financial_pages_title(pdf)
                    result.detection_method = "deterministic_fallback"
                else:
                    # Step 3: Deterministic validation (SECONDARY)
                    logger.info("Validating LLM results with deterministic methods...")
                    result = _validate_with_deterministic(pdf, llm_result)
        else:
            # ============================================================
            # DETERMINISTIC-ONLY PATH (LLM unavailable)
            # ============================================================
            logger.info("LLM unavailable — using full deterministic scan")
            result = find_financial_pages_title(pdf)
            result.detection_method = "deterministic_fallback"

        # Step 4: Find Notes to Accounts pages (always deterministic)
        result.notes_pages = find_notes_pages(pdf, result)

        return result
    finally:
        pdf.close()
