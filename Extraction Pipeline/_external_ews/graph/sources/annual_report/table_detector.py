"""Table Detection Layer — identifies pages containing structured tables.

Uses heuristics (numeric density, column detection, table boundaries,
layout analysis) to identify pages containing financial tables and
determines whether VLM extraction is needed.

Target table types:
  - Balance Sheet
  - Profit & Loss Statement
  - Cash Flow Statement
  - Statement of Changes in Equity
  - Shareholding Pattern
  - Financial Ratios
  - Debt Schedules
  - Segment Information

Phase 5 additions:
  - ``TableCategory`` enum for refined table classification
  - Context-aware ``_classify_table_category()`` that cross-references
    with the section registry to reduce false positives
  - ``parent_section_id`` linking each table to its owning section

VLM is triggered only when:
  - Complex table detected (multi-level headers, merged cells)
  - Table reconstruction confidence below threshold
  - Traditional extraction fails
"""

from __future__ import annotations

import enum
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ===================================================================
# Table Category Enum (Phase 5)
# ===================================================================

class TableCategory(str, enum.Enum):
    """Refined table category for classification.

    Maps the raw ``table_type`` from keyword detection into a
    semantic category used for VLM priority routing and false-positive
    reduction.
    """

    FINANCIAL_STATEMENT = "financial_statement"    # BS, P&L, CF, SOCE
    KPI_TABLE = "kpi_table"                        # Financial highlights, ratios
    SHAREHOLDING_TABLE = "shareholding_table"      # Shareholding pattern
    NOTE_TABLE = "note_table"                      # Tables within notes
    RELATED_PARTY_TABLE = "related_party_table"    # RPT disclosures
    RATIO_TABLE = "ratio_table"                    # Key financial ratios
    SEGMENT_TABLE = "segment_table"                # Segment information
    SCHEDULE_TABLE = "schedule_table"              # Schedules to financial statements
    OTHER = "other"                                # Miscellaneous tables


# Mapping: raw table_type → TableCategory
_TABLE_TYPE_TO_CATEGORY: dict[str, TableCategory] = {
    "balance_sheet": TableCategory.FINANCIAL_STATEMENT,
    "profit_and_loss": TableCategory.FINANCIAL_STATEMENT,
    "cash_flow": TableCategory.FINANCIAL_STATEMENT,
    "changes_in_equity": TableCategory.FINANCIAL_STATEMENT,
    "shareholding_pattern": TableCategory.SHAREHOLDING_TABLE,
    "financial_ratios": TableCategory.RATIO_TABLE,
    "debt_schedule": TableCategory.SCHEDULE_TABLE,
    "segment_information": TableCategory.SEGMENT_TABLE,
}

# Taxonomy categories that indicate financial-statement pages
_FINANCIAL_TAXONOMY_CATEGORIES = {
    "Financial Statements",
    "Notes to Accounts",
    "Shareholding Information",
    "Related Party Transactions",
}

# KPI / highlights keywords — if a table matches financial_statement
# keywords but is in a non-financial section, it's likely a KPI table
_KPI_SECTION_KEYWORDS: list[re.Pattern] = [
    re.compile(r"\bfinancial\s+highlight", re.I),
    re.compile(r"\bkey\s+(?:performance|financial)\s+indicator", re.I),
    re.compile(r"\bkpi\b", re.I),
    re.compile(r"\bperformance\s+summary", re.I),
    re.compile(r"\bfinancial\s+summary", re.I),
    re.compile(r"\bat\s+a\s+glance\b", re.I),
]


# ===================================================================
# Table type detection patterns
# ===================================================================

# Maps table type → (keyword_patterns, required_keywords_count)
_TABLE_TYPE_PATTERNS: dict[str, tuple[list[re.Pattern], int]] = {
    "balance_sheet": (
        [
            re.compile(r"\bbalance\s+sheet\b", re.I),
            re.compile(r"\bstatement\s+of\s+financial\s+position\b", re.I),
            re.compile(r"\bequity\s+and\s+liabilit", re.I),
            re.compile(r"\bnon[-\s]?current\s+assets\b", re.I),
            re.compile(r"\bcurrent\s+assets\b", re.I),
            re.compile(r"\btotal\s+assets\b", re.I),
            re.compile(r"\btotal\s+equity\b", re.I),
        ],
        2,  # Need at least 2 keyword matches
    ),
    "profit_and_loss": (
        [
            re.compile(r"\bstatement\s+of\s+profit\s+(?:and|&)\s+loss\b", re.I),
            re.compile(r"\bprofit\s+(?:and|&)\s+loss\s+(?:account|statement)\b", re.I),
            re.compile(r"\bincome\s+statement\b", re.I),
            re.compile(r"\brevenue\s+from\s+operations\b", re.I),
            re.compile(r"\bearnings?\s+per\s+(?:equity\s+)?share\b", re.I),
            re.compile(r"\bother\s+comprehensive\s+income\b", re.I),
            re.compile(r"\btotal\s+comprehensive\s+income\b", re.I),
        ],
        2,
    ),
    "cash_flow": (
        [
            re.compile(r"\bcash\s+flow\s+statement\b", re.I),
            re.compile(r"\bstatement\s+of\s+cash\s+flows?\b", re.I),
            re.compile(r"\boperating\s+activities\b", re.I),
            re.compile(r"\binvesting\s+activities\b", re.I),
            re.compile(r"\bfinancing\s+activities\b", re.I),
            re.compile(r"\bnet\s+(?:increase|decrease)\s+in\s+cash\b", re.I),
            re.compile(r"\bcash\s+and\s+cash\s+equivalents\b", re.I),
        ],
        2,
    ),
    "changes_in_equity": (
        [
            re.compile(r"\bstatement\s+of\s+changes?\s+in\s+equity\b", re.I),
            re.compile(r"\bchanges?\s+in\s+equity\b", re.I),
            re.compile(r"\bequity\s+share\s+capital\b", re.I),
            re.compile(r"\bother\s+equity\b", re.I),
            re.compile(r"\bretained\s+earnings\b", re.I),
        ],
        2,
    ),
    "shareholding_pattern": (
        [
            re.compile(r"\bshareholding\s+pattern\b", re.I),
            re.compile(r"\bpromoter\s+(?:and\s+promoter\s+group)?\b", re.I),
            re.compile(r"\bpublic\s+shareholding\b", re.I),
            re.compile(r"\bcustodian[s]?\b", re.I),
            re.compile(r"\b%\s+of\s+total\b", re.I),
            re.compile(r"\bno\.?\s+of\s+shares?\b", re.I),
        ],
        2,
    ),
    "financial_ratios": (
        [
            re.compile(r"\bfinancial\s+ratios?\b", re.I),
            re.compile(r"\bkey\s+(?:financial\s+)?ratios?\b", re.I),
            re.compile(r"\bratio\s+analysis\b", re.I),
            re.compile(r"\bdebt[\s-]equity\s+ratio\b", re.I),
            re.compile(r"\bcurrent\s+ratio\b", re.I),
            re.compile(r"\breturn\s+on\s+(?:equity|capital|net\s+worth)\b", re.I),
        ],
        2,
    ),
    "debt_schedule": (
        [
            re.compile(r"\bdebt\s+(?:schedule|maturity|profile)\b", re.I),
            re.compile(r"\blong[\s-]term\s+borrowing", re.I),
            re.compile(r"\bshort[\s-]term\s+borrowing", re.I),
            re.compile(r"\bmaturity\s+profile\b", re.I),
            re.compile(r"\brepayment\s+schedule\b", re.I),
        ],
        2,
    ),
    "segment_information": (
        [
            re.compile(r"\bsegment\s+(?:information|reporting|wise)\b", re.I),
            re.compile(r"\bbusiness\s+segment", re.I),
            re.compile(r"\bgeographical\s+segment", re.I),
            re.compile(r"\bsegment\s+revenue\b", re.I),
            re.compile(r"\bsegment\s+(?:assets|liabilities|result)\b", re.I),
        ],
        2,
    ),
}

# Indicators of complex tables that need VLM
_COMPLEXITY_INDICATORS = [
    re.compile(r"\bparticulars\b.*\bparticulars\b", re.I | re.DOTALL),  # Merged headers
    re.compile(r"\bas\s+at\b.*\bas\s+at\b", re.I),  # Multiple date columns
    re.compile(r"\bnote\s+no\b.*\bnote\s+no\b", re.I),  # Repeated headers
]


# ===================================================================
# Detection Functions
# ===================================================================

def detect_tables(
    pages: list[dict[str, Any]],
    master_sections: list[dict[str, Any]] | None = None,
    progress_callback=None,
) -> list[dict[str, Any]]:
    """Detect structured tables across all pages.

    Parameters
    ----------
    pages : list[dict]
        Page data dicts from master data layer.
    master_sections : list[dict], optional
        Consolidated sections from the section consolidator.
        When provided, enables context-aware table category
        classification and false-positive reduction.
    progress_callback : callable, optional
        Progress callback.

    Returns
    -------
    list[dict]
        List of detected table dicts with: page_number, table_type,
        detection_confidence, needs_vlm, numeric_density, column_count,
        table_category, parent_section_id.
    """
    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    detected: list[dict[str, Any]] = []

    _log(f"[TableDetect] Scanning {len(pages)} pages for structured tables...")

    # Build page → section_id lookup for parent_section_id assignment
    page_to_section_id: dict[int, str] = {}
    if master_sections:
        for section in master_sections:
            sid = section.get("section_id", "")
            for pg in range(section.get("start_page", 0), section.get("end_page", 0) + 1):
                page_to_section_id[pg] = sid

    for page in pages:
        page_num = page["page_number"]
        raw_text = page.get("raw_text", "")

        if not raw_text.strip():
            continue

        # Compute page metrics
        numeric_density = _compute_numeric_density(raw_text)
        column_count = _estimate_column_count(raw_text)
        has_table_structure = page.get("has_tables", False)

        # Check each table type
        for table_type, (patterns, min_matches) in _TABLE_TYPE_PATTERNS.items():
            matches = sum(1 for p in patterns if p.search(raw_text))
            if matches >= min_matches:
                # Calculate detection confidence
                confidence = _calculate_confidence(
                    keyword_matches=matches,
                    total_patterns=len(patterns),
                    numeric_density=numeric_density,
                    has_pdfplumber_tables=has_table_structure,
                )

                # Determine if VLM is needed
                needs_vlm = _needs_vlm_extraction(
                    raw_text, numeric_density, column_count, confidence
                )

                import uuid
                table_id = f"TB_{uuid.uuid4().hex[:6].upper()}"

                # Context-aware table category classification
                table_category = _classify_table_category(
                    table_type=table_type,
                    page_number=page_num,
                    master_sections=master_sections,
                    raw_text=raw_text,
                )

                # Parent section ID
                parent_section_id = page_to_section_id.get(page_num, "")

                detected.append({
                    "table_id": table_id,
                    "table_name": table_type.replace("_", " ").title(),
                    "page_no": page_num,
                    "complexity_score": round(confidence, 3),
                    "needs_vlm": needs_vlm,
                    "table_type": table_type,
                    "numeric_density": round(numeric_density, 3),
                    "column_count": column_count,
                    "table_category": table_category.value,
                    "parent_section_id": parent_section_id,
                })

    _log(f"[TableDetect] Detected {len(detected)} tables across "
         f"{len(set(d['page_no'] for d in detected))} pages")

    # Log summary by type
    type_counts: dict[str, int] = {}
    for d in detected:
        type_counts[d["table_type"]] = type_counts.get(d["table_type"], 0) + 1
    for tt, count in type_counts.items():
        vlm_count = sum(1 for d in detected if d["table_type"] == tt and d["needs_vlm"])
        _log(f"[TableDetect]   {tt}: {count} page(s), {vlm_count} need VLM")

    # Log summary by category
    cat_counts: dict[str, int] = {}
    for d in detected:
        tc = d.get("table_category", "other")
        cat_counts[tc] = cat_counts.get(tc, 0) + 1
    for tc, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        _log(f"[TableDetect]   category={tc}: {count}")

    return detected


# ===================================================================
# Context-Aware Table Category Classification (Phase 5)
# ===================================================================

def _classify_table_category(
    table_type: str,
    page_number: int,
    master_sections: list[dict[str, Any]] | None,
    raw_text: str,
) -> TableCategory:
    """Classify a detected table into a refined category using context.

    Uses three signals (in priority order):

    1. **Section context**: If the page belongs to a section whose
       taxonomy category is not ``Financial Statements``, a table
       matching financial-statement keywords is likely a KPI/summary
       table, not a primary financial statement.
    2. **KPI keyword check**: If the page text contains KPI/highlights
       keywords, reclassify financial_statement → kpi_table.
    3. **Default mapping**: Use the ``_TABLE_TYPE_TO_CATEGORY`` lookup.

    Parameters
    ----------
    table_type : str
        Raw table type from keyword detection (e.g., ``"balance_sheet"``).
    page_number : int
        Page number where the table was detected.
    master_sections : list[dict] | None
        Consolidated sections (may be ``None`` if not available).
    raw_text : str
        Raw text on the page for keyword analysis.

    Returns
    -------
    TableCategory
        Refined table category.
    """
    # Start with the default mapping
    base_category = _TABLE_TYPE_TO_CATEGORY.get(table_type, TableCategory.OTHER)

    # If no section context available, return the base category
    if not master_sections:
        return base_category

    # Find which section this page belongs to
    owning_section: dict[str, Any] | None = None
    for section in master_sections:
        start = section.get("start_page", 0)
        end = section.get("end_page", 0)
        if start <= page_number <= end:
            owning_section = section
            break

    if not owning_section:
        return base_category

    section_category = owning_section.get("category", "")
    section_name = owning_section.get("raw_section_name", "") or owning_section.get("section_name", "")
    section_subcategory = owning_section.get("section_subtype", owning_section.get("subcategory", ""))
    zone = owning_section.get("zone", "narrative")

    # ── False-positive reduction ──
    # If a table matches financial_statement keywords but the page
    # belongs to a non-financial zone, it's likely a KPI table or TOC
    if base_category == TableCategory.FINANCIAL_STATEMENT:
        if zone != "financial":
            if section_name.lower() in ("toc", "table of contents", "index") or "table of contents" in section_category.lower():
                return TableCategory.OTHER
                
            # Check for KPI keywords in the section name or page text
            is_kpi = any(
                p.search(section_name) or p.search(section_subcategory) or p.search(raw_text[:500])
                for p in _KPI_SECTION_KEYWORDS
            )
            if is_kpi:
                return TableCategory.KPI_TABLE
            
            # Even without KPI keywords, a financial-statement match
            # outside the financial zone is probably a summary table
            return TableCategory.KPI_TABLE

    # ── Related-party reclassification ──
    # If the section is about related parties, classify accordingly
    if section_category == "Notes to Accounts" and section_subcategory == "Related Party Transactions":
        return TableCategory.RELATED_PARTY_TABLE
    elif "Related Party" in section_subcategory and zone != "financial":
        return TableCategory.OTHER # Just a mention, not the table

    # ── Notes reclassification ──
    # Tables within Notes to Accounts are note tables
    if section_category == "Notes to Accounts":
        return TableCategory.NOTE_TABLE

    return base_category


def _compute_numeric_density(text: str) -> float:
    """Compute the ratio of numeric characters to total characters.

    Higher density indicates more tabular/numeric content.
    Financial statements typically have density > 0.15.
    """
    if not text:
        return 0.0

    total_chars = len(text)
    # Count digits, commas in numbers, decimal points, brackets (negatives)
    numeric_chars = sum(
        1 for c in text if c.isdigit() or c in ',.()%-'
    )

    return numeric_chars / max(total_chars, 1)


def _estimate_column_count(text: str) -> int:
    """Estimate the number of columns in tabular content.

    Looks at whitespace patterns and tab-like spacing in lines.
    """
    if not text:
        return 0

    lines = text.splitlines()
    column_counts: list[int] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or len(stripped) < 10:
            continue

        # Count segments separated by 2+ spaces (typical pdfplumber output)
        segments = re.split(r'\s{2,}', stripped)
        segments = [s.strip() for s in segments if s.strip()]

        if len(segments) >= 2:
            column_counts.append(len(segments))

    if not column_counts:
        return 0

    # Return the most common column count (mode)
    from collections import Counter
    counter = Counter(column_counts)
    return counter.most_common(1)[0][0] if counter else 0


def _calculate_confidence(
    keyword_matches: int,
    total_patterns: int,
    numeric_density: float,
    has_pdfplumber_tables: bool,
) -> float:
    """Calculate table detection confidence based on multiple signals."""
    # Base confidence from keyword match ratio
    keyword_ratio = keyword_matches / max(total_patterns, 1)
    confidence = keyword_ratio * 0.5

    # Boost for numeric density
    if numeric_density > 0.20:
        confidence += 0.25
    elif numeric_density > 0.10:
        confidence += 0.15
    elif numeric_density > 0.05:
        confidence += 0.05

    # Boost for pdfplumber table detection
    if has_pdfplumber_tables:
        confidence += 0.15

    return min(confidence, 1.0)


def _needs_vlm_extraction(
    text: str,
    numeric_density: float,
    column_count: int,
    detection_confidence: float,
) -> bool:
    """Determine if a detected table needs VLM for extraction.

    VLM is triggered when:
    - Complex table detected (multi-level headers, merged cells)
    - Table reconstruction confidence below threshold
    - Multi-column layout detected
    """
    # High complexity indicators
    complexity_score = 0

    for indicator in _COMPLEXITY_INDICATORS:
        if indicator.search(text):
            complexity_score += 1

    # Multi-column tables are harder to reconstruct
    if column_count >= 5:
        complexity_score += 1

    # High numeric density with low column detection = possibly merged
    if numeric_density > 0.15 and column_count <= 2:
        complexity_score += 1

    # Financial statements almost always benefit from VLM
    financial_keywords = [
        "balance sheet", "profit and loss", "cash flow",
        "statement of changes in equity",
    ]
    is_financial = any(kw in text.lower() for kw in financial_keywords)
    if is_financial:
        complexity_score += 1

    # Low detection confidence → VLM as safety net
    if detection_confidence < 0.6:
        complexity_score += 1

    return complexity_score >= 2
