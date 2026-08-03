"""VLM Target Generator — auto-identifies high-priority VLM extraction targets.

Analyses the consolidated section registry and table inventory to produce
a prioritised list of sections that require Vision Language Model extraction,
along with tailored prompt templates for each table category.

Priority Rules
--------------
+----------+---------------------------------------------------+---------------------------+
| Priority | Condition                                         | Examples                  |
+==========+===================================================+===========================+
| HIGH     | content_type == table AND table_category ==        | Balance Sheet, P&L,       |
|          | financial_statement                               | Cash Flow, Changes in     |
|          |                                                   | Equity                    |
+----------+---------------------------------------------------+---------------------------+
| HIGH     | content_type == table AND table_category ==        | Shareholding Pattern      |
|          | shareholding_table                                |                           |
+----------+---------------------------------------------------+---------------------------+
| MEDIUM   | content_type == table AND table_category ==        | Related Party             |
|          | related_party_table                               | Transactions              |
+----------+---------------------------------------------------+---------------------------+
| MEDIUM   | content_type == mixed AND high numeric density     | Notes with embedded       |
|          |                                                   | tables                    |
+----------+---------------------------------------------------+---------------------------+
| MEDIUM   | content_type == table AND table_category in        | Financial Ratios,         |
|          | (ratio_table, segment_table, schedule_table)       | Segment Info, Debt        |
+----------+---------------------------------------------------+---------------------------+
| LOW      | content_type == text                              | Directors Report, MD&A    |
+----------+---------------------------------------------------+---------------------------+
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ===================================================================
# Table Category Classification
# ===================================================================

class TableCategory:
    """Constants for table category classification.

    Maps the raw ``table_type`` values from
    :mod:`table_detector` into semantic categories used
    for VLM priority routing.
    """

    FINANCIAL_STATEMENT = "financial_statement"
    KPI_TABLE = "kpi_table"
    SHAREHOLDING_TABLE = "shareholding_table"
    NOTE_TABLE = "note_table"
    RELATED_PARTY_TABLE = "related_party_table"
    RATIO_TABLE = "ratio_table"
    SEGMENT_TABLE = "segment_table"
    SCHEDULE_TABLE = "schedule_table"
    OTHER = "other"


# Mapping: table_detector table_type → TableCategory
_TABLE_TYPE_TO_CATEGORY: dict[str, str] = {
    "balance_sheet": TableCategory.FINANCIAL_STATEMENT,
    "profit_and_loss": TableCategory.FINANCIAL_STATEMENT,
    "cash_flow": TableCategory.FINANCIAL_STATEMENT,
    "changes_in_equity": TableCategory.FINANCIAL_STATEMENT,
    "shareholding_pattern": TableCategory.SHAREHOLDING_TABLE,
    "financial_ratios": TableCategory.RATIO_TABLE,
    "debt_schedule": TableCategory.SCHEDULE_TABLE,
    "segment_information": TableCategory.SEGMENT_TABLE,
}

# Mapping: taxonomy category → default TableCategory for sections in that category
_CATEGORY_TO_TABLE_CATEGORY: dict[str, str] = {
    "Financial Statements": TableCategory.FINANCIAL_STATEMENT,
    "Notes to Accounts": TableCategory.NOTE_TABLE,
    "Shareholding Pattern": TableCategory.SHAREHOLDING_TABLE,
    "Related Party Transactions": TableCategory.RELATED_PARTY_TABLE,
}

# Taxonomy subcategory keywords that indicate related-party content
_RELATED_PARTY_KEYWORDS: list[re.Pattern] = [
    re.compile(r"\brelated\s+part", re.I),
    re.compile(r"\brpt\b", re.I),
    re.compile(r"\btransactions\s+with\s+(?:related|associated)", re.I),
]

# Taxonomy subcategory keywords that indicate KPI / highlights content
_KPI_KEYWORDS: list[re.Pattern] = [
    re.compile(r"\bfinancial\s+highlight", re.I),
    re.compile(r"\bkpi\b", re.I),
    re.compile(r"\bkey\s+(?:performance|financial)\s+indicator", re.I),
    re.compile(r"\bperformance\s+summary", re.I),
    re.compile(r"\bfinancial\s+summary", re.I),
]


# ===================================================================
# VLM Prompt Templates
# ===================================================================

_PROMPT_FINANCIAL_STATEMENT = (
    "You are a financial data extraction expert. Extract the {statement_type} "
    "from the provided page image(s). Return a JSON object with keys: "
    '"title", "currency", "periods" (list of period strings), '
    'and "rows" (list of dicts, each with "section", "line_item", '
    '"note_no", and "values" containing "current_period" and "previous_period"). '
    "All amounts should be in absolute numbers (e.g., 1,234.56 for ₹1,234.56 crore). "
    "Preserve the exact line-item hierarchy and indentation from the document."
)

_PROMPT_SHAREHOLDING = (
    "You are a financial data extraction expert. Extract the Shareholding Pattern "
    "table from the provided page image(s). Return a JSON object with keys: "
    '"title", "category" (shareholder category), "rows" where each row has '
    '"shareholder_category", "no_of_shares", "pct_of_total", and any sub-categories. '
    "Ensure the totals reconcile."
)

_PROMPT_RELATED_PARTY = (
    "You are a financial data extraction expert. Extract the Related Party "
    "Transactions table from the provided page image(s). Return a JSON object "
    'with keys: "title", "rows" where each row has "related_party_name", '
    '"relationship", "transaction_type", "current_period_amount", '
    '"previous_period_amount", and "balance_outstanding". '
    "Group by relationship category if the table is structured that way."
)

_PROMPT_RATIO_TABLE = (
    "You are a financial data extraction expert. Extract the Financial Ratios "
    "table from the provided page image(s). Return a JSON object with keys: "
    '"title", "periods" (list of period strings), "rows" where each row has '
    '"ratio_name", "current_period_value", "previous_period_value". '
    "Preserve the exact ratio names from the document."
)

_PROMPT_SEGMENT_TABLE = (
    "You are a financial data extraction expert. Extract the Segment "
    "Information table from the provided page image(s). Return a JSON object "
    'with keys: "title", "rows" where each row has "segment_name", '
    '"segment_revenue", "segment_result", "segment_assets", "segment_liabilities". '
    "Separate business segments from geographical segments if both are present."
)

_PROMPT_SCHEDULE_TABLE = (
    "You are a financial data extraction expert. Extract the Schedule table "
    "from the provided page image(s). Return a JSON object with keys: "
    '"title", "schedule_no", "rows" where each row has "line_item", '
    '"note_no", "current_period", "previous_period". '
    "Preserve the exact line-item hierarchy from the document."
)

_PROMPT_NOTE_TABLE = (
    "You are a financial data extraction expert. Extract the Notes to Accounts "
    "table from the provided page image(s). Return a JSON object with keys: "
    '"note_no", "title", "rows" where each row is a list of cell values. '
    "Preserve the exact table structure including sub-totals and totals."
)

_PROMPT_KPI_TABLE = (
    "You are a financial data extraction expert. Extract the Financial "
    "Highlights / KPI table from the provided page image(s). Return a JSON "
    'object with keys: "title", "periods" (list of period strings), "rows" '
    'where each row has "metric_name", "values" (list of amounts per period). '
    "Include units and scale information (e.g., 'in ₹ crore')."
)

_PROMPT_GENERIC_TABLE = (
    "You are a financial data extraction expert. Extract the table from the "
    "provided page image(s). Return a JSON object with keys: "
    '"title", "column_headers" (list of column names), "rows" (list of lists '
    "representing each row's cell values). Preserve the exact table structure."
)

# Mapping: TableCategory → prompt template
_CATEGORY_PROMPTS: dict[str, str] = {
    TableCategory.FINANCIAL_STATEMENT: _PROMPT_FINANCIAL_STATEMENT,
    TableCategory.SHAREHOLDING_TABLE: _PROMPT_SHAREHOLDING,
    TableCategory.RELATED_PARTY_TABLE: _PROMPT_RELATED_PARTY,
    TableCategory.RATIO_TABLE: _PROMPT_RATIO_TABLE,
    TableCategory.SEGMENT_TABLE: _PROMPT_SEGMENT_TABLE,
    TableCategory.SCHEDULE_TABLE: _PROMPT_SCHEDULE_TABLE,
    TableCategory.NOTE_TABLE: _PROMPT_NOTE_TABLE,
    TableCategory.KPI_TABLE: _PROMPT_KPI_TABLE,
    TableCategory.OTHER: _PROMPT_GENERIC_TABLE,
}

# Mapping: TableCategory → statement_type for financial statement prompt
_FINANCIAL_STATEMENT_TYPES: dict[str, str] = {
    "balance_sheet": "Balance Sheet",
    "profit_and_loss": "Statement of Profit and Loss",
    "cash_flow": "Cash Flow Statement",
    "changes_in_equity": "Statement of Changes in Equity",
}


# ===================================================================
# VLMTarget dataclass
# ===================================================================

@dataclass
class VLMTarget:
    """A single VLM extraction target derived from the section registry.

    Attributes
    ----------
    section_id : str
        Unique identifier from the section registry.
    section_name : str
        Human-readable section name.
    priority : str
        ``"high"``, ``"medium"``, or ``"low"``.
    table_category : str
        One of the :class:`TableCategory` constants.
    page_range : tuple[int, int]
        ``(start_page, end_page)`` inclusive.
    extraction_prompt : str
        Tailored VLM prompt for this target's table category.
    estimated_pages : int
        Number of pages this target spans.
    content_type : str
        ``"table"``, ``"text"``, or ``"mixed"`` from the section.
    category : str
        Taxonomy category (parent).
    confidence : float
        Section confidence score.
    table_type : str
        Raw table_type from table_detector (if available).
    """

    section_id: str
    section_name: str
    priority: str  # "high" | "medium" | "low"
    table_category: str
    page_range: tuple[int, int]
    extraction_prompt: str
    estimated_pages: int
    content_type: str
    category: str
    confidence: float = 0.0
    table_type: str = ""


# ===================================================================
# Core Generator
# ===================================================================

def generate_vlm_targets(
    master_sections: list[dict[str, Any]],
    table_inventory: list[dict[str, Any]],
    progress_callback=None,
) -> list[dict[str, Any]]:
    """Auto-generate VLM extraction targets from section registry + table inventory.

    Parameters
    ----------
    master_sections : list[dict]
        Consolidated sections from :func:`section_consolidator.consolidate_sections`.
    table_inventory : list[dict]
        Detected tables from :func:`table_detector.detect_tables`.
    progress_callback : callable, optional
        Progress message callback.

    Returns
    -------
    list[dict]
        Prioritised list of VLM target dicts, sorted by priority
        (high → medium → low), then by page number.
    """
    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    _log("[VLMTargets] Generating VLM extraction targets...")

    # ── Build page → table_type lookup from inventory ──
    page_to_tables: dict[int, list[dict[str, Any]]] = {}
    for t in table_inventory:
        pg = t.get("page_no", 0)
        page_to_tables.setdefault(pg, []).append(t)

    targets: list[VLMTarget] = []

    for section in master_sections:
        section_id = section.get("section_id", "")
        section_name = section.get("normalized_section_name", section.get("raw_section_name", ""))
        content_type = section.get("content_type", "text")
        category = section.get("category", "")
        subcategory = section.get("subcategory", "")
        start_page = section.get("start_page", 0)
        end_page = section.get("end_page", 0)
        confidence = section.get("confidence", 0.0)
        extraction_strategy = section.get("extraction_strategy", "pdf_text")

        # ── Determine table_category ──
        table_category, table_type = _classify_section_table_category(
            section=section,
            page_to_tables=page_to_tables,
        )

        # ── Determine priority ──
        priority = _determine_priority(
            content_type=content_type,
            table_category=table_category,
            category=category,
            subcategory=subcategory,
            confidence=confidence,
        )

        # ── Build extraction prompt ──
        prompt = _build_extraction_prompt(
            table_category=table_category,
            table_type=table_type,
            section_name=section_name,
        )

        target = VLMTarget(
            section_id=section_id,
            section_name=section_name,
            priority=priority,
            table_category=table_category,
            page_range=(start_page, end_page),
            extraction_prompt=prompt,
            estimated_pages=end_page - start_page + 1,
            content_type=content_type,
            category=category,
            confidence=confidence,
            table_type=table_type,
        )
        targets.append(target)

    # ── Sort: high → medium → low, then by start_page ──
    priority_order = {"high": 0, "medium": 1, "low": 2}
    targets.sort(key=lambda t: (priority_order.get(t.priority, 3), t.page_range[0]))

    # ── Convert to dicts ──
    result = [_target_to_dict(t) for t in targets]

    # ── Log summary ──
    high_count = sum(1 for t in targets if t.priority == "high")
    medium_count = sum(1 for t in targets if t.priority == "medium")
    low_count = sum(1 for t in targets if t.priority == "low")
    _log(f"[VLMTargets] {len(result)} targets: "
         f"{high_count} HIGH, {medium_count} MEDIUM, {low_count} LOW")

    # Log category breakdown
    cat_counts: dict[str, int] = {}
    for t in targets:
        cat_counts[t.table_category] = cat_counts.get(t.table_category, 0) + 1
    for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
        _log(f"[VLMTargets]   {cat}: {cnt}")

    return result


# ===================================================================
# Table Category Classification
# ===================================================================

def _classify_section_table_category(
    section: dict[str, Any],
    page_to_tables: dict[int, list[dict[str, Any]]],
) -> tuple[str, str]:
    """Classify a section's table category using multiple signals.

    Uses (in priority order):
    1. table_detector's ``table_type`` for pages within the section
    2. Taxonomy category → TableCategory mapping
    3. Subcategory keyword matching (related party, KPI)
    4. Default based on content_type

    Parameters
    ----------
    section : dict
        A master section dict.
    page_to_tables : dict
        Page number → list of detected table dicts.

    Returns
    -------
    tuple[str, str]
        ``(table_category, raw_table_type)`` where *raw_table_type* is
        the original ``table_type`` from the detector (empty string if
        none found).
    """
    start_page = section.get("start_page", 0)
    end_page = section.get("end_page", 0)
    category = section.get("category", "")
    subcategory = section.get("subcategory", "")
    content_type = section.get("content_type", "text")

    # ── Signal 1: Cross-reference with table inventory ──
    # Collect all table_types detected on pages within this section
    detected_types: dict[str, int] = {}  # table_type → count
    for pg in range(start_page, end_page + 1):
        for t in page_to_tables.get(pg, []):
            tt = t.get("table_type", "")
            if tt:
                detected_types[tt] = detected_types.get(tt, 0) + 1

    # If we have a clear dominant table_type, use it
    if detected_types:
        dominant_type = max(detected_types, key=detected_types.get)
        dominant_count = detected_types[dominant_type]
        # Only use if majority of pages with tables agree
        total_table_pages = sum(detected_types.values())
        if dominant_count >= total_table_pages * 0.5:
            mapped_category = _TABLE_TYPE_TO_CATEGORY.get(
                dominant_type, TableCategory.OTHER
            )
            return (mapped_category, dominant_type)

    # ── Signal 2: Taxonomy category mapping ──
    if category in _CATEGORY_TO_TABLE_CATEGORY:
        return (_CATEGORY_TO_TABLE_CATEGORY[category], "")

    # ── Signal 3: Subcategory keyword matching ──
    for pattern in _RELATED_PARTY_KEYWORDS:
        if pattern.search(subcategory) or pattern.search(section.get("section_name", "")):
            return (TableCategory.RELATED_PARTY_TABLE, "")

    for pattern in _KPI_KEYWORDS:
        if pattern.search(subcategory) or pattern.search(section.get("section_name", "")):
            return (TableCategory.KPI_TABLE, "")

    # ── Signal 4: Default based on content_type ──
    if content_type == "table":
        return (TableCategory.OTHER, "")
    elif content_type == "mixed":
        return (TableCategory.NOTE_TABLE, "")
    else:
        return (TableCategory.OTHER, "")


# ===================================================================
# Priority Determination
# ===================================================================

def _determine_priority(
    content_type: str,
    table_category: str,
    category: str,
    subcategory: str,
    confidence: float,
) -> str:
    """Determine VLM extraction priority for a section.

    Parameters
    ----------
    content_type : str
        ``"table"``, ``"text"``, or ``"mixed"``.
    table_category : str
        One of the :class:`TableCategory` constants.
    category : str
        Taxonomy category.
    subcategory : str
        Taxonomy subcategory.
    confidence : float
        Section confidence score.

    Returns
    -------
    str
        ``"high"``, ``"medium"``, or ``"low"``.
    """
    # ── HIGH priority ──
    if content_type == "table" and table_category == TableCategory.FINANCIAL_STATEMENT:
        return "high"
    if content_type == "table" and table_category == TableCategory.SHAREHOLDING_TABLE:
        return "high"

    # ── MEDIUM priority ──
    if content_type == "table" and table_category == TableCategory.RELATED_PARTY_TABLE:
        return "medium"
    if content_type == "table" and table_category in (
        TableCategory.RATIO_TABLE,
        TableCategory.SEGMENT_TABLE,
        TableCategory.SCHEDULE_TABLE,
    ):
        return "medium"
    if content_type == "mixed":
        # Mixed content with high numeric density → medium
        # (numeric density is already reflected in content_type assignment
        #  by the section consolidator)
        return "medium"
    if content_type == "table" and table_category == TableCategory.KPI_TABLE:
        return "medium"

    # ── LOW priority ──
    # Text sections, note tables with low confidence, and other tables
    return "low"


# ===================================================================
# Prompt Builder
# ===================================================================

def _build_extraction_prompt(
    table_category: str,
    table_type: str,
    section_name: str,
) -> str:
    """Build a tailored VLM extraction prompt for the target.

    Parameters
    ----------
    table_category : str
        One of the :class:`TableCategory` constants.
    table_type : str
        Raw table_type from table_detector (may be empty).
    section_name : str
        Section name for context.

    Returns
    -------
    str
        Tailored VLM prompt string.
    """
    template = _CATEGORY_PROMPTS.get(table_category, _PROMPT_GENERIC_TABLE)

    # For financial statements, fill in the statement type
    if table_category == TableCategory.FINANCIAL_STATEMENT:
        stmt_type = _FINANCIAL_STATEMENT_TYPES.get(
            table_type, section_name
        )
        return template.format(statement_type=stmt_type)

    return template


# ===================================================================
# Target Summary
# ===================================================================

def vlm_target_summary(
    vlm_targets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Generate a summary of VLM targets for reporting.

    Parameters
    ----------
    vlm_targets : list[dict]
        VLM target dicts from :func:`generate_vlm_targets`.

    Returns
    -------
    dict
        Summary with counts, priority breakdown, and category breakdown.
    """
    if not vlm_targets:
        return {
            "total_targets": 0,
            "by_priority": {"high": 0, "medium": 0, "low": 0},
            "by_category": {},
            "high_priority_sections": [],
            "estimated_vlm_pages": 0,
        }

    by_priority: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
    by_category: dict[str, int] = {}
    high_priority_sections: list[str] = []
    estimated_vlm_pages = 0

    for t in vlm_targets:
        priority = t.get("priority", "low")
        by_priority[priority] = by_priority.get(priority, 0) + 1

        tc = t.get("table_category", "other")
        by_category[tc] = by_category.get(tc, 0) + 1

        if priority in ("high", "medium"):
            estimated_vlm_pages += t.get("estimated_pages", 1)

        if priority == "high":
            high_priority_sections.append(
                f"{t.get('section_name', '')} (pp. {t['page_range'][0]}-{t['page_range'][1]})"
            )

    return {
        "total_targets": len(vlm_targets),
        "by_priority": by_priority,
        "by_category": by_category,
        "high_priority_sections": high_priority_sections,
        "estimated_vlm_pages": estimated_vlm_pages,
    }


# ===================================================================
# Helpers
# ===================================================================

def _target_to_dict(target: VLMTarget) -> dict[str, Any]:
    """Convert a :class:`VLMTarget` to a serialisable dict."""
    return {
        "section_id": target.section_id,
        "section_name": target.section_name,
        "priority": target.priority,
        "table_category": target.table_category,
        "page_range": list(target.page_range),  # tuple → list for JSON
        "extraction_prompt": target.extraction_prompt,
        "estimated_pages": target.estimated_pages,
        "content_type": target.content_type,
        "category": target.category,
        "confidence": target.confidence,
        "table_type": target.table_type,
    }
