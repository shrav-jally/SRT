"""
Smart Extraction Agent

Orchestrates the full pipeline for extracting financial data from annual
report PDFs and populating the Excel template:

    1. TABLE FINDER: LLM-first page identification with deterministic validation
       a. QUICK DETERMINISTIC CHECK: Cost optimization for standard Schedule III titles
       b. LLM PAGE IDENTIFICATION (PRIMARY): Identifies BS/P&L/CF pages + statement type
       c. DETERMINISTIC VALIDATION (SECONDARY): Validates LLM results, adds missed pages
       d. NOTES PAGE DETECTION: Deterministic regex-based search
    2. TEXT TABLE EXTRACTOR: Deterministic line-by-line parsing of
       financial statement text (like Excel's "Get Data from PDF")
    3. DATA MAPPER: LLM-first mapping strategy:
       a. KEYWORD ALIASES: Deterministic pre-pass for known label variations
       b. LLM MAPPING: Primary method — understands semantics, sections,
          abbreviations (e.g., "PPE" = "Property, Plant and Equipment")
       c. FUZZY MATCHING: Fallback for items LLM couldn't map
    4. EXCEL WRITER: Write mapped values + formulas to the template

Design principles:
    - Fully automatic: no manual page input required
    - LLM-first: LLM is the primary method for both page finding AND mapping;
      deterministic methods serve as validation and fallback
    - Deterministic extraction: table extraction is pattern-based, not probabilistic
    - Section-aware: tracks which section (NC Assets, Current Liabilities, etc.)
      each row belongs to for accurate mapping
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import pdfplumber

from .table_finder import find_financial_statements, FinancialStatementPages
from .text_table_extractor import (
    extract_financial_statement,
    extract_table_from_pages,
    extract_notes_from_pages,
    ExtractedTable,
    ExtractedRow,
)
from .data_mapper import (
    MappingResult,
    map_balance_sheet,
    map_profit_and_loss,
    map_cash_flow,
    map_notes_to_other_financial_info,
    compute_derived_items,
    BALANCE_SHEET_TEMPLATE,
    PL_TEMPLATE,
    CASH_FLOW_TEMPLATE,
    FORMULA_TEMPLATE_ITEMS,
    _is_total_row,
    _normalize_text,
    _parse_alias_value,
)
from .ca_validator import run_ca_validation, ValidationReport, InferredMapping
from .excel_writer import write_all_sheets

logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class ExtractionResult:
    """Result of the full extraction pipeline."""
    output_path: str = ""
    year: int = 0
    year_detection_method: str = ""  # How the year was detected (e.g., "filename_compact6")

    # Page detection results
    pages_found: FinancialStatementPages = field(default_factory=FinancialStatementPages)

    # Extraction stats per sheet
    bs_rows_extracted: int = 0
    pl_rows_extracted: int = 0
    cf_rows_extracted: int = 0

    # Mapping stats per sheet
    bs_mapped: int = 0
    pl_mapped: int = 0
    cf_mapped: int = 0

    # Writing stats
    bs_written: int = 0
    pl_written: int = 0
    cf_written: int = 0

    # Completeness percentages
    bs_completeness: float = 0.0
    pl_completeness: float = 0.0
    cf_completeness: float = 0.0

    # Notes extraction stats
    notes_rows_extracted: int = 0
    notes_ofi_mapped: int = 0  # "Other Financial Information" items from notes

    # CA Validation stats
    ca_flags_count: int = 0  # Total validation flags (errors + warnings + info)
    ca_errors: int = 0  # Error-level flags (e.g., BS doesn't balance)
    ca_warnings: int = 0  # Warning-level flags (e.g., sub-total mismatch)
    ca_inferred: int = 0  # Number of CA-inferred mappings applied
    ca_note_refs: int = 0  # Number of items with note cross-references
    ca_balanced: bool = True  # Whether BS equation holds

    # Metadata
    unit: str = "Not specified"  # e.g., "₹ in Lakhs", "₹ in Crores"
    statement_type: str = "Not specified"  # "Standalone" or "Consolidated"
    bs_pages: list = field(default_factory=list)
    pl_pages: list = field(default_factory=list)
    cf_pages: list = field(default_factory=list)
    notes_pages: list = field(default_factory=list)

    # Any errors
    errors: list[str] = field(default_factory=list)

    @property
    def overall_completeness(self) -> float:
        """Average completeness across all three sheets."""
        scores = []
        if self.bs_completeness > 0:
            scores.append(self.bs_completeness)
        if self.pl_completeness > 0:
            scores.append(self.pl_completeness)
        if self.cf_completeness > 0:
            scores.append(self.cf_completeness)
        return sum(scores) / len(scores) if scores else 0.0


# ============================================================================
# SECTION TRACKER
# ============================================================================


# Maps section headers in the PDF to template section names
# This is critical for disambiguating items like "(i) Borrowings" which
# appears in both Non-current and Current liabilities
BS_SECTION_MAP = {
    # Assets
    "non-current assets": "Non-current assets",
    "non current assets": "Non-current assets",
    "noncurrent assets": "Non-current assets",
    "current assets": "Current assets",
    # Equity
    "equity": "",
    "equity and liabilities": "",
    "equity & liabilities": "",
    "equity and liability": "",
    # Liabilities
    "non-current liabilities": "Non-current liabilities",
    "non current liabilities": "Non-current liabilities",
    "noncurrent liabilities": "Non-current liabilities",
    "current liabilities": "Current liabilities",
    # Sub-sections within assets/liabilities (common in Indian reports)
    "financial assets": "",  # Sub-section, don't change current section
    "financial liabilities": "",  # Sub-section, don't change current section
    # Assets top-level
    "assets": "",  # Top-level header, don't change section
}

PL_SECTION_MAP = {
    "income": "Income",
    "expenses": "IV. Expenses",
    "taxes": "Taxes",
    "profit": "Profit/Loss",
    "profit/loss": "Profit/Loss",
}

CF_SECTION_MAP = {
    "cash flow": "Cash Flow",
    "operating": "Cash Flow",
    "investing": "Cash Flow",
    "financing": "Cash Flow",
    "other financial information": "Other Financial Information",
}


def _track_section(row: ExtractedRow, section_map: dict) -> str:
    """
    Determine which template section a row belongs to based on
    section headers and indent levels.
    """
    label_lower = row.label.lower().strip()

    # Check if this row IS a section header
    if row.is_section_header:
        for pdf_section, template_section in section_map.items():
            if pdf_section in label_lower:
                return template_section

    # For sub-items, the section is inherited from the current context
    # (handled by the caller which tracks current section)
    return ""


# ============================================================================
# CONVERTER: ExtractedTable → tabular format for data_mapper
# ============================================================================


def _normalize_section_key(s: str) -> str:
    """Normalize a section name for comparison: lowercase, strip hyphens/spaces."""
    return re.sub(r'[\s\-]', '', s.lower().strip())


def _convert_extracted_table_to_tabular(
    extracted: ExtractedTable,
    section_map: dict,
    target_year: Optional[int] = None,
) -> tuple[list[str], list[list[str]]]:
    """
    Convert an ExtractedTable (from text_table_extractor) into the
    tabular format expected by data_mapper's map_table_to_template().

    The data_mapper expects:
        - table_headers: list of column header strings
        - table_rows: list of rows, each row is a list of cell strings
          where row[0] is the label and subsequent cells are values

    We also add a "Section" column so the data_mapper can do
    section-aware matching (e.g., distinguish NC vs Current "Borrowings").

    Section detection strategy (3-tier):
        1. EXACT: If row.is_section_header is True, match against section_map
           using normalized comparison (case-insensitive, hyphen/space stripped).
        2. LABEL-BASED: If a data row's label contains a known section name
           as a prefix (e.g., "Non-current assets Financial assets" where
           "Non-current assets" is the section), detect and assign section.
        3. STRUCTURAL FALLBACK: For Balance Sheet, if no section headers were
           detected at all, assign sections based on row order using the
           standard Schedule III structure:
           Equity Share Capital + Other Equity → Equity section
           Then NC Liabilities → Current Liabilities

    Year column labeling strategy (fixes the "wrong year" bug):
        - If year_headers from extraction contain actual 4-digit years,
          use them directly. Then verify: if target_year is provided and
          the first year header does NOT contain target_year, swap columns
          and log a warning (PDF had previous year first).
        - If year_headers are empty/generic but target_year is provided,
          construct synthetic headers with actual year numbers so that
          data_mapper's _detect_year_column() can work correctly:
            target_year → "As at March 31, {target_year}"
            target_year-1 → "As at March 31, {target_year-1}"
        - If neither year_headers nor target_year available, fall back to
          generic "Current Year" / "Previous Year" labels (legacy behavior).

    Args:
        extracted: ExtractedTable from text_table_extractor.
        section_map: Mapping from PDF section names to template section names.
        target_year: The detected financial year ending year (e.g., 2018 for
                     FY 2017-18). Used to correctly label value columns.

    Returns:
        (table_headers, table_rows) tuple.
    """
    # Pre-compute normalized section map for fast lookup
    norm_section_map = {
        _normalize_section_key(k): v for k, v in section_map.items()
    }

    # Determine number of value columns from the extracted data
    max_values = 0
    for row in extracted.rows:
        if len(row.values) > max_values:
            max_values = len(row.values)

    # Build headers: Label | Section | Note | Val1 | Val2 | ...
    # We include "Section" column for section-aware matching
    headers = ["Label", "Section", "Note"]
    for i in range(max_values):
        if i == 0 and max_values == 1:
            headers.append("Current Year")
        elif i == 0:
            headers.append("Current Year")
        elif i == 1:
            headers.append("Previous Year")
        else:
            headers.append(f"Year_{i+1}")

    # === YEAR COLUMN LABELING (fixes the "wrong year" bug) ===
    # Check if year_headers contain actual 4-digit year numbers
    year_headers_have_years = False
    if extracted.year_headers and len(extracted.year_headers) <= max_values:
        for yh in extracted.year_headers:
            if re.search(r'20\d{2}', yh):
                year_headers_have_years = True
                break

    if year_headers_have_years and extracted.year_headers:
        # Use the extracted year headers directly
        for i, yh in enumerate(extracted.year_headers):
            if i + 3 < len(headers):
                headers[i + 3] = yh

        # VERIFICATION: If target_year is provided, check that the first
        # value column actually corresponds to the target (current) year.
        # Some Indian PDFs put the previous year column first.
        if target_year and max_values >= 2:
            first_year_match = re.search(r'(20\d{2})', headers[3])
            second_year_match = re.search(r'(20\d{2})', headers[4]) if len(headers) > 4 else None

            if first_year_match and second_year_match:
                first_year = int(first_year_match.group(1))
                second_year = int(second_year_match.group(1))

                if first_year != target_year and second_year == target_year:
                    # The PDF has previous year first — swap column labels
                    logger.warning(
                        f"YEAR COLUMN SWAP: PDF has previous year ({first_year}) in column 1 "
                        f"and current year ({second_year}) in column 2. Swapping headers to "
                        f"match expected order (current year first)."
                    )
                    headers[3], headers[4] = headers[4], headers[3]

    elif target_year and max_values >= 2:
        # No year headers with actual years from extraction, but we know
        # the target year. Construct synthetic headers with actual year
        # numbers so data_mapper's _detect_year_column() can work correctly.
        # This is the KEY FIX for the "takes 2017 instead of 2018" bug.
        headers[3] = f"As at March 31, {target_year}"
        headers[4] = f"As at March 31, {target_year - 1}"
        logger.info(
            f"YEAR HEADERS: Constructed synthetic year headers from target_year={target_year}: "
            f"Col1='{headers[3]}', Col2='{headers[4]}'"
        )
    elif target_year and max_values == 1:
        # Single value column — just label with target year
        headers[3] = f"As at March 31, {target_year}"
        logger.info(
            f"YEAR HEADERS: Single value column labeled with target_year={target_year}"
        )
    else:
        # Fallback: use extracted year_headers if available (even without years)
        if extracted.year_headers and len(extracted.year_headers) <= max_values:
            for i, yh in enumerate(extracted.year_headers):
                if i + 3 < len(headers):
                    headers[i + 3] = yh
        # Otherwise, generic "Current Year"/"Previous Year" labels remain
        # (legacy behavior — data_mapper will try keyword matching)

    # Build rows with section tracking
    rows = []
    current_section = ""
    any_section_detected = False  # Track if ANY section header was found

    for row in extracted.rows:
        # Update current section if this is a section header
        if row.is_section_header:
            label_norm = _normalize_section_key(row.label)
            for pdf_section_norm, template_section in norm_section_map.items():
                if pdf_section_norm in label_norm or label_norm in pdf_section_norm:
                    # Only update if the template_section is non-empty
                    # (empty means "top-level header, don't change section")
                    if template_section:
                        current_section = template_section
                        any_section_detected = True
                    break

        # Skip rows with no label and no values
        if not row.label and not row.values:
            continue

        # Build the row cells
        cells = [row.label, current_section, row.note_ref or ""]

        # Add values, padding with empty strings if needed
        for i in range(max_values):
            if i < len(row.values):
                cells.append(row.values[i])
            else:
                cells.append("")

        rows.append(cells)

    # === STRUCTURAL FALLBACK for Balance Sheet ===
    # If NO section headers were detected at all (all rows have empty section),
    # assign sections based on row order and known BS structure.
    # This handles PDFs where section headers are missing or not recognized.
    if not any_section_detected and extracted.statement_type == "balance_sheet":
        logger.info(
            "BS: No section headers detected — applying structural fallback "
            "section assignment based on Schedule III order"
        )
        _assign_bs_sections_structurally(rows)

    return headers, rows


def _assign_bs_sections_structurally(rows: list[list[str]]) -> None:
    """
    Assign BS sections to rows when no section headers were detected.

    Uses the standard Schedule III Balance Sheet structure:
        1. Non-current assets (first group of asset rows)
        2. Current assets (second group of asset rows)
        3. Equity (Equity Share Capital + Other Equity)
        4. Non-current liabilities (first group of liability rows after equity)
        5. Current liabilities (second group of liability rows)

    Detection heuristics:
        - "Equity Share Capital" or "Other Equity" marks the Equity section
        - "Total" rows mark section boundaries
        - After equity, the next group is NC liabilities, then Current liabilities
        - Before equity, the first group is NC assets, then Current assets
    """
    # Key row labels that mark section boundaries
    EQUITY_MARKERS = {"equity share capital", "other equity"}
    NC_LIAB_MARKERS = {
        "non-current liabilities", "non current liabilities",
        "financial liabilities", "borrowings", "lease liabilities",
        "deferred tax liabilities", "provisions",
    }
    CURRENT_LIAB_MARKERS = {
        "current liabilities", "current borrowings", "trade payables",
        "other financial liabilities", "other current liabilities",
        "short-term provisions", "current tax liabilities",
    }
    CURRENT_ASSET_MARKERS = {
        "inventories", "trade receivables", "cash and cash equivalents",
        "bank balances", "current investments", "loans",
        "other current assets", "current tax assets",
    }

    # Phase 1: Find the equity boundary
    equity_idx = None
    for i, row in enumerate(rows):
        label = row[0].lower().strip() if row else ""
        # Strip (a)/(b) prefixes for comparison
        label_clean = re.sub(r'^\(?[a-z]+[\).]\s*', '', label).strip()
        if label_clean in EQUITY_MARKERS or any(m == label_clean for m in EQUITY_MARKERS):
            equity_idx = i
            break

    if equity_idx is None:
        # Try finding "Total Assets" or "Total Equity and Liabilities" as boundary
        for i, row in enumerate(rows):
            label = row[0].lower().strip() if row else ""
            if 'total assets' in label and 'total equity' not in label:
                equity_idx = i
                break

    # Phase 2: Assign sections based on position relative to equity
    # Before equity: Assets (NC first, then Current)
    # At/after equity: Equity, then Liabilities (NC first, then Current)
    current_section = "Non-current assets"  # Default start for BS

    for i, row in enumerate(rows):
        label = row[0].lower().strip() if row else ""
        label_clean = re.sub(r'^\(?[a-z]+[\).]\s*', '', label).strip()
        # Also strip roman numeral prefixes
        label_clean = re.sub(r'^[ivx]+\.\s*', '', label_clean).strip()

        # Skip total rows for section assignment (they inherit current section)
        if label_clean.startswith('total'):
            row[1] = current_section
            continue

        # Check for equity markers
        if equity_idx is not None and i >= equity_idx:
            if i == equity_idx or label_clean in EQUITY_MARKERS:
                current_section = ""  # Equity section (empty in template)
                row[1] = current_section
                continue

            # After equity: check if we've moved to liabilities
            if current_section == "" or current_section == "Non-current liabilities" or current_section == "Current liabilities":
                # Check for NC liability markers
                if any(m in label_clean for m in NC_LIAB_MARKERS):
                    if current_section != "Current liabilities":
                        current_section = "Non-current liabilities"
                # Check for Current liability markers
                elif any(m in label_clean for m in CURRENT_LIAB_MARKERS):
                    current_section = "Current liabilities"
                # "Total Non-current Liabilities" boundary
                elif 'total non' in label_clean and 'liab' in label_clean:
                    current_section = "Non-current liabilities"
                    row[1] = current_section
                    # Next section will be Current liabilities
                    current_section = "Current liabilities"
                    continue
                # "Total Current Liabilities" boundary
                elif 'total current liab' in label_clean:
                    current_section = "Current liabilities"

        else:
            # Before equity: Assets section
            # Check for current asset markers
            if any(m in label_clean for m in CURRENT_ASSET_MARKERS):
                current_section = "Current assets"
            # "Total Non Current Assets" boundary
            elif 'total non' in label_clean and 'asset' in label_clean:
                current_section = "Non-current assets"
                row[1] = current_section
                # Next section will be Current assets
                current_section = "Current assets"
                continue
            # "Total Current Assets" boundary
            elif 'total current asset' in label_clean:
                current_section = "Current assets"

        row[1] = current_section

    # Log the resulting section distribution
    section_counts = {}
    for row in rows:
        sec = row[1] if len(row) > 1 else ""
        sec_display = sec if sec else "(empty)"
        section_counts[sec_display] = section_counts.get(sec_display, 0) + 1
    logger.info(f"BS: Structural fallback section distribution: {section_counts}")


# ============================================================================
# YEAR DETECTION
# ============================================================================


def _detect_year_from_pdf(
    pdf_path: str,
    pages: FinancialStatementPages,
    llm=None,
) -> tuple[int, str]:
    """
    Auto-detect the financial year from the PDF.

    Strategy (ordered by specificity):
    1. Check filename for year patterns (multiple Indian AR formats)
    2. Check page text for "Year ended March 31, YYYY" patterns
    3. LLM verification fallback (if llm is provided and confidence is low)

    Indian financial year convention: FY "2017-18" means year ending
    March 31, 2018. We always return the ENDING year.

    Returns:
        (year, detection_method) — method is one of:
        "filename_full_range", "filename_2digit_suffix", "filename_compact6",
        "filename_fy_prefix", "filename_single_year", "page_text",
        "llm_verified", "default_current"
    """
    filename = os.path.basename(pdf_path)

    # --- Filename patterns (ordered by specificity) ---

    # Pattern 1: "2022-2023" or "2022_2023" (4-digit both sides) → take second year
    year_match = re.search(r'(20\d{2})\s*[-_]\s*(20\d{2})', filename)
    if year_match:
        year1, year2 = int(year_match.group(1)), int(year_match.group(2))
        if year2 == year1 + 1:
            logger.info(
                f"Year detected from filename (full range): {year2} "
                f"(from '{year_match.group(0)}' in '{filename}')"
            )
            return year2, "filename_full_range"

    # Pattern 2: "2017-18" or "2017_18" (4-digit + 2-digit) → construct ending year
    year_match = re.search(r'(20\d{2})\s*[-_]\s*(\d{2})', filename)
    if year_match:
        year1 = int(year_match.group(1))
        suffix = int(year_match.group(2))
        ending_year = 2000 + suffix
        if ending_year == year1 + 1:
            logger.info(
                f"Year detected from filename (2-digit suffix): {ending_year} "
                f"(from '{year_match.group(0)}' in '{filename}')"
            )
            return ending_year, "filename_2digit_suffix"

    # Pattern 3: "202021" or "202425" (6-digit compact YYYY+YY) → extract ending year
    # This handles filenames like "RajeshExportsAR202021" or "AR201920REL"
    year_match = re.search(r'(20\d{2})(\d{2})', filename)
    if year_match:
        year1 = int(year_match.group(1))
        suffix = int(year_match.group(2))
        ending_year = 2000 + suffix
        if ending_year == year1 + 1:
            logger.info(
                f"Year detected from filename (compact 6-digit): {ending_year} "
                f"(from '{year_match.group(0)}' in '{filename}')"
            )
            return ending_year, "filename_compact6"

    # Pattern 4: "FY2024" or "fy2024"
    year_match = re.search(r'FY\s*(20\d{2})', filename, re.IGNORECASE)
    if year_match:
        year = int(year_match.group(1))
        logger.info(
            f"Year detected from filename (FY prefix): {year} "
            f"(from '{year_match.group(0)}' in '{filename}')"
        )
        return year, "filename_fy_prefix"

    # Pattern 5: Single 4-digit year (lowest confidence from filename)
    year_match = re.search(r'(20\d{2})', filename)
    if year_match:
        year = int(year_match.group(1))
        logger.info(
            f"Year detected from filename (single year, low confidence): {year} "
            f"(from '{filename}')"
        )
        # Don't return immediately — try page text first for higher confidence
        page_year = _detect_year_from_page_text(pdf_path, pages)
        if page_year is not None:
            return page_year, "page_text"
        # Fall back to filename single year
        return year, "filename_single_year"

    # --- Page text patterns ---
    page_year = _detect_year_from_page_text(pdf_path, pages)
    if page_year is not None:
        return page_year, "page_text"

    # Default: current year
    from datetime import datetime
    logger.warning(
        f"Could not detect year from filename or page text for '{filename}', "
        f"defaulting to current year"
    )
    return datetime.now().year, "default_current"


def _detect_year_from_page_text(
    pdf_path: str,
    pages: FinancialStatementPages,
) -> Optional[int]:
    """
    Extract the financial year from page text by looking for
    "March 31, YYYY" or "Year ended March 31, YYYY" patterns.

    Returns the latest year found, or None if no year patterns found.
    """
    all_pages = pages.all_pages
    if not all_pages:
        # Scan middle pages of the PDF
        try:
            pdf = pdfplumber.open(pdf_path)
            total = len(pdf.pages)
            scan_pages = range(max(1, total // 3), min(total, int(total * 0.7)))
            all_pages = list(scan_pages)
            pdf.close()
        except Exception:
            return None

    if all_pages:
        try:
            pdf = pdfplumber.open(pdf_path)
            all_years = []
            for pg_num in all_pages[:10]:
                page = pdf.pages[pg_num - 1]
                text = page.extract_text() or ""
                # Look for "March 31, 2024" or "Year ended March 31, 2024"
                year_matches = re.findall(
                    r'(?:March|April)\s+\d{1,2},?\s*(20\d{2})', text
                )
                all_years.extend(int(y) for y in year_matches)
            pdf.close()
            if all_years:
                return max(all_years)  # Use the latest year
        except Exception:
            pass

    return None


def _verify_year_with_llm(
    pdf_path: str,
    pages: FinancialStatementPages,
    detected_year: int,
    detection_method: str,
    llm,
) -> int:
    """
    Use LLM to verify the detected financial year when confidence is low.

    Called only when the year was detected from a low-confidence source
    (e.g., single year from filename with no range confirmation).

    The LLM reads the first financial statement page and confirms the year.

    Returns:
        The verified year (may differ from detected_year if LLM corrects it).
    """
    if llm is None:
        return detected_year

    # Only verify low-confidence detections
    low_confidence_methods = {
        "filename_single_year",
        "filename_fy_prefix",
        "default_current",
    }
    if detection_method not in low_confidence_methods:
        return detected_year

    from .llm_utils import llm_call_with_retry, extract_json_from_response

    # Get text from the first financial statement page
    page_text = ""
    all_pages = pages.all_pages
    if all_pages:
        try:
            pdf = pdfplumber.open(pdf_path)
            page = pdf.pages[all_pages[0] - 1]
            page_text = page.extract_text() or ""
            pdf.close()
        except Exception:
            pass

    if not page_text or len(page_text) < 100:
        logger.info("LLM year verification: insufficient page text, keeping detected year")
        return detected_year

    # Truncate to first 1500 chars to keep prompt compact
    page_text = page_text[:1500]

    prompt = f"""You are a financial document analyst. Read the following text from an Indian company annual report and determine the financial year.

The financial year in India runs from April 1 to March 31. For example, "FY 2017-18" means the year ending March 31, 2018.

Text from the report:
---
{page_text}
---

The system detected year {detected_year} (method: {detection_method}).

Respond in JSON format:
{{"year": <ending_year_as_integer>, "confidence": "high"|"medium"|"low", "reasoning": "<brief explanation>"}}

For example, if the text says "As at March 31, 2024", the year is 2024.
If the text says "For the year ended March 31, 2023", the year is 2023."""

    try:
        response = llm_call_with_retry(llm, prompt, max_retries=1)
        if not response:
            return detected_year

        result = extract_json_from_response(response)
        if result and isinstance(result, dict):
            llm_year = result.get("year")
            confidence = result.get("confidence", "low")
            reasoning = result.get("reasoning", "")

            if llm_year and isinstance(llm_year, int) and 2000 <= llm_year <= 2099:
                if llm_year != detected_year:
                    logger.info(
                        f"LLM year verification: corrected {detected_year} → {llm_year} "
                        f"(confidence={confidence}, reasoning: {reasoning})"
                    )
                    return llm_year
                else:
                    logger.info(
                        f"LLM year verification: confirmed {detected_year} "
                        f"(confidence={confidence})"
                    )
                    return detected_year
    except Exception as e:
        logger.warning(f"LLM year verification failed: {e}")

    return detected_year


# ============================================================================
# VERIFICATION (optional, uses LLM sparingly)
# ============================================================================


def _build_valid_template_items() -> set[str]:
    """
    Build a set of all valid template item names across BS, P&L, and CF templates.
    Used to validate LLM corrections so we don't rename items to garbage.
    """
    valid_items = set()
    for template in [BALANCE_SHEET_TEMPLATE, PL_TEMPLATE, CASH_FLOW_TEMPLATE]:
        for section_key, section_val in template.items():
            if isinstance(section_val, dict) and section_val is not None:
                for item_name in section_val.keys():
                    valid_items.add(item_name)
            else:
                valid_items.add(section_key)
    return valid_items


# Pre-compute valid template items once at module level
_VALID_TEMPLATE_ITEMS = _build_valid_template_items()


def _verify_mappings_with_llm(
    extracted: ExtractedTable,
    mappings: list[MappingResult],
    llm,
    statement_type: str,
) -> list[MappingResult]:
    """
    Optional: Use LLM to verify or correct low-confidence mappings.

    Only checks mappings with confidence < 0.7 to minimize LLM usage.
    Validates that LLM correction targets are actual template item names
    before applying — prevents garbage renames that cause values to be lost.

    Returns the (possibly corrected) mappings list.
    """
    if llm is None:
        return mappings

    low_confidence = [m for m in mappings if m.confidence < 0.7]
    if not low_confidence:
        return mappings

    from .llm_utils import llm_call_with_retry, extract_json_from_response

    # Build a summary of extracted rows
    rows_summary = []
    for row in extracted.rows[:30]:
        vals = " | ".join(row.values) if row.values else "(no values)"
        rows_summary.append(f"  {row.label}: {vals}")

    # Build a summary of low-confidence mappings
    mapping_summary = []
    for m in low_confidence:
        mapping_summary.append(
            f"  '{m.pdf_row_label}' -> '{m.template_item}' "
            f"(value={m.value}, confidence={m.confidence:.2f})"
        )

    # Build list of valid template items for this statement type to guide the LLM
    if "balance" in statement_type.lower():
        template_items_list = sorted(
            item for section in BALANCE_SHEET_TEMPLATE.values()
            if isinstance(section, dict) for item in section.keys()
        )
    elif "profit" in statement_type.lower() or "loss" in statement_type.lower():
        template_items_list = sorted(
            item for section in PL_TEMPLATE.values()
            if isinstance(section, dict) for item in section.keys()
        )
    elif "cash" in statement_type.lower():
        template_items_list = sorted(
            item for section in CASH_FLOW_TEMPLATE.values()
            if isinstance(section, dict) for item in section.keys()
        )
    else:
        template_items_list = sorted(_VALID_TEMPLATE_ITEMS)

    prompt = f"""You are a financial data verification assistant. Review these low-confidence mappings from an Indian company annual report.

Statement type: {statement_type}

Valid template item names (corrections MUST be one of these):
{chr(10).join(f'  - {item}' for item in template_items_list)}

Extracted rows:
{chr(10).join(rows_summary)}

Low-confidence mappings to verify:
{chr(10).join(mapping_summary)}

For each mapping that is WRONG, respond with:
WRONG|current_template_item|correct_template_item

The correct_template_item MUST be from the valid template item names listed above.
Only respond for mappings you want to change. One per line.
If all mappings are correct, respond with: ALL CORRECT"""

    try:
        response = llm_call_with_retry(llm, prompt, max_retries=1)
        if not response:
            return mappings

        # Log raw response for debugging
        logger.debug(f"LLM verification raw response ({len(response)} chars): {response[:300]}")

        corrections = {}
        rejected = {}
        for line in response.strip().split('\n'):
            line = line.strip()
            if '|' not in line:
                continue
            parts = line.split('|')
            if len(parts) < 3:
                continue

            verdict = parts[0].strip().upper()
            template_item = parts[1].strip()

            if verdict == "WRONG" and len(parts) >= 3:
                correct_item = parts[2].strip()
                # Validate: the correction target MUST be a valid template item
                if correct_item in _VALID_TEMPLATE_ITEMS:
                    corrections[template_item] = correct_item
                else:
                    rejected[template_item] = correct_item
                    logger.warning(
                        f"LLM correction REJECTED: '{template_item}' -> '{correct_item}' "
                        f"('{correct_item}' is not a valid template item name)"
                    )

        if rejected:
            logger.warning(
                f"LLM verification: {len(rejected)} correction(s) rejected because "
                f"target is not a valid template item: {rejected}"
            )

        # Apply only validated corrections
        applied = 0
        if corrections:
            for m in mappings:
                if m.template_item in corrections:
                    old = m.template_item
                    m.template_item = corrections[old]
                    m.method = f"{m.method}_llm_corrected"
                    applied += 1
                    logger.info(
                        f"LLM correction: '{old}' -> '{corrections[old]}' "
                        f"(was: '{m.pdf_row_label}')"
                    )

        if applied or rejected:
            logger.info(
                f"LLM verification: {applied} correction(s) applied, "
                f"{len(rejected)} rejected"
            )

    except Exception as e:
        logger.warning(f"LLM verification failed: {e}")

    return mappings


# ============================================================================
# MAIN AGENT CLASS
# ============================================================================


class SmartExtractionAgent:
    """
    Orchestrates the full extraction pipeline:
        PDF → find pages (LLM-first) → extract tables → map to template (LLM-first) → write Excel

    Fully automatic — no manual page input required.
    LLM is the PRIMARY method for page finding and mapping; deterministic
    methods serve as validation and fallback.
    """

    def __init__(
        self,
        llm=None,
        use_llm: bool = True,
        verify_with_llm: bool = True,
        progress_callback=None,
    ):
        """
        Args:
            llm: LangChain ChatOpenAI instance (required for LLM-first page finding and mapping).
            use_llm: Whether to use LLM as primary page finder and mapper.
            verify_with_llm: Whether to use LLM for post-mapping verification
                             (default True — LLM is now the primary mapper).
            progress_callback: Optional callback function(step, status, progress, message)
                called at each pipeline step to report real-time progress.
        """
        self.llm = llm
        self.use_llm = use_llm
        self.verify_with_llm = verify_with_llm
        self.progress_callback = progress_callback

    def _report_progress(self, step: str, status: str, progress: float, message: str = ""):
        """Report progress to the callback if available."""
        if self.progress_callback:
            try:
                self.progress_callback(step, status, progress, message)
            except Exception:
                pass  # Don't let callback errors break extraction

    def run(
        self,
        pdf_path: str,
        template_path: str,
        output_path: str,
        year: Optional[int] = None,
    ) -> ExtractionResult:
        """
        Run the full extraction pipeline.

        Args:
            pdf_path: Path to the annual report PDF.
            template_path: Path to the Excel template file.
            output_path: Path to write the filled Excel file.
            year: Financial year (auto-detected if not provided).

        Returns:
            ExtractionResult with stats and completion info.
        """
        result = ExtractionResult()

        # ================================================================
        # STEP 1: Find financial statement pages
        # ================================================================
        logger.info("=" * 60)
        logger.info("STEP 1: Finding financial statement pages")
        logger.info("=" * 60)
        self._report_progress("Finding financial statement pages", "active", 0, "Scanning PDF pages for financial statement titles...")

        try:
            pages = find_financial_statements(
                pdf_path,
                llm=self.llm if self.use_llm else None,
                use_llm=self.use_llm,
            )
            result.pages_found = pages
        except Exception as e:
            error_msg = f"Failed to find financial statement pages: {e}"
            logger.error(error_msg)
            result.errors.append(error_msg)
            self._report_progress("Finding financial statement pages", "failed", 0, error_msg)
            return result

        if not pages.is_complete:
            missing = []
            if not pages.balance_sheet:
                missing.append("Balance Sheet")
            if not pages.profit_and_loss:
                missing.append("P&L")
            if not pages.cash_flow:
                missing.append("Cash Flow")
            logger.warning(f"Could not find pages for: {', '.join(missing)}")

        page_msg = f"BS={pages.balance_sheet}, P&L={pages.profit_and_loss}, CF={pages.cash_flow}"
        logger.info(
            f"Pages found: BS={pages.balance_sheet}, "
            f"P&L={pages.profit_and_loss}, CF={pages.cash_flow}, "
            f"CoE={pages.changes_in_equity}"
        )
        self._report_progress("Finding financial statement pages", "completed", 100, page_msg)

        # ================================================================
        # STEP 2: Auto-detect year
        # ================================================================
        self._report_progress("Detecting financial year", "active", 0, "Auto-detecting from filename or PDF content...")
        year_detection_method = "user_provided"
        if year is None:
            year, year_detection_method = _detect_year_from_pdf(
                pdf_path, pages, llm=self.llm if self.use_llm else None,
            )
            # LLM verification for low-confidence detections
            if self.use_llm and self.llm:
                verified_year = _verify_year_with_llm(
                    pdf_path, pages, year, year_detection_method, self.llm,
                )
                if verified_year != year:
                    logger.info(
                        f"Year updated by LLM verification: {year} → {verified_year}"
                    )
                    year = verified_year
                    year_detection_method = "llm_verified"
        result.year = year
        result.year_detection_method = year_detection_method
        logger.info(f"Financial year: {year} (method: {year_detection_method})")
        self._report_progress(
            "Detecting financial year", "completed", 100,
            f"Year: {year} (method: {year_detection_method})",
        )

        # ================================================================
        # STEP 2b: Use statement type from page finding + filter standalone
        # ================================================================
        # Statement type is now detected by the LLM/deterministic page finder
        # (FinancialStatementPages.statement_type). We use it directly instead
        # of re-detecting, since the page finder already did the work.
        statement_type = pages.statement_type
        if statement_type == "Not specified":
            # Fallback: detect from page titles if page finder didn't set it
            statement_type = _detect_statement_type(
                pages.balance_sheet, pages.profit_and_loss,
                pages.cash_flow, pdf_path,
            )
        result.statement_type = statement_type
        logger.info(f"Statement type: {statement_type} (from page finder: {pages.statement_type})")

        # Filter to standalone pages — STANDALONE-ONLY POLICY
        # Per user requirement: extract ONLY from standalone financial statements.
        # If only consolidated pages are found, skip extraction entirely.
        self._report_progress("Filtering standalone pages", "active", 0, "Filtering to standalone financial statements (standalone-only policy)...")
        bs_pages = _prefer_standalone(pages.balance_sheet, pdf_path)
        pl_pages = _prefer_standalone(pages.profit_and_loss, pdf_path)
        cf_pages = _prefer_standalone(pages.cash_flow, pdf_path)

        if bs_pages != pages.balance_sheet:
            logger.info(f"BS: Filtered to standalone pages {bs_pages} (was {pages.balance_sheet})")
        if pl_pages != pages.profit_and_loss:
            logger.info(f"P&L: Filtered to standalone pages {pl_pages} (was {pages.profit_and_loss})")
        if cf_pages != pages.cash_flow:
            logger.info(f"CF: Filtered to standalone pages {cf_pages} (was {pages.cash_flow})")
        self._report_progress("Filtering standalone pages", "completed", 100, f"BS={bs_pages}, P&L={pl_pages}, CF={cf_pages}")

        # ================================================================
        # STEP 2c: Standalone-only gate — abort if no standalone pages found
        # ================================================================
        if not bs_pages and not pl_pages and not cf_pages:
            error_msg = (
                "STANDALONE-ONLY POLICY: No standalone financial statement pages found. "
                "All detected pages are Consolidated. This app requires Standalone financial "
                "statements per Schedule III of the Companies Act, 2013. "
                "Extraction aborted."
            )
            logger.error(error_msg)
            result.errors.append(error_msg)
            result.statement_type = "Consolidated (rejected)"
            self._report_progress("Filtering standalone pages", "failed", 0, error_msg)
            return result

        # If some statements have no standalone pages, log warnings but continue
        # with the ones that do have standalone pages
        skipped = []
        if not bs_pages and pages.balance_sheet:
            skipped.append("Balance Sheet (consolidated-only)")
        if not pl_pages and pages.profit_and_loss:
            skipped.append("P&L (consolidated-only)")
        if not cf_pages and pages.cash_flow:
            skipped.append("Cash Flow (consolidated-only)")
        if skipped:
            logger.warning(
                f"Standalone-only policy: skipping consolidated-only statements: "
                f"{', '.join(skipped)}"
            )

        # ================================================================
        # STEP 3: Extract tables from each statement
        # ================================================================
        logger.info("=" * 60)
        logger.info("STEP 3: Extracting financial statement tables")
        logger.info("=" * 60)

        bs_table = ExtractedTable(statement_type="balance_sheet")
        pl_table = ExtractedTable(statement_type="profit_and_loss")
        cf_table = ExtractedTable(statement_type="cash_flow")
        notes_table = ExtractedTable(statement_type="notes")

        # Store filtered pages in result
        result.bs_pages = bs_pages
        result.pl_pages = pl_pages
        result.cf_pages = cf_pages

        pdf = pdfplumber.open(pdf_path)
        try:
            if bs_pages:
                self._report_progress("Extracting Balance Sheet", "active", 0, f"Extracting from pages {bs_pages}...")
                bs_table = extract_table_from_pages(
                    pdf, bs_pages, "balance_sheet"
                )
                result.bs_rows_extracted = len(bs_table.rows)
                logger.info(f"BS: {len(bs_table.rows)} rows extracted from pages {bs_pages}")
                self._report_progress("Extracting Balance Sheet", "completed", 100, f"{len(bs_table.rows)} rows extracted")

            if pl_pages:
                self._report_progress("Extracting P&L Statement", "active", 0, f"Extracting from pages {pl_pages}...")
                pl_table = extract_table_from_pages(
                    pdf, pl_pages, "profit_and_loss"
                )
                result.pl_rows_extracted = len(pl_table.rows)
                logger.info(f"P&L: {len(pl_table.rows)} rows extracted from pages {pl_pages}")
                self._report_progress("Extracting P&L Statement", "completed", 100, f"{len(pl_table.rows)} rows extracted")

            if cf_pages:
                self._report_progress("Extracting Cash Flow Statement", "active", 0, f"Extracting from pages {cf_pages}...")
                cf_table = extract_table_from_pages(
                    pdf, cf_pages, "cash_flow"
                )
                result.cf_rows_extracted = len(cf_table.rows)
                logger.info(f"CF: {len(cf_table.rows)} rows extracted from pages {cf_pages}")
                self._report_progress("Extracting Cash Flow Statement", "completed", 100, f"{len(cf_table.rows)} rows extracted")

            # ============================================================
            # STEP 3b: Extract Notes to Accounts tables
            # ============================================================
            notes_pages = pages.notes_pages

            if notes_pages:
                self._report_progress("Extracting Notes to Accounts", "active", 0, f"Extracting from {len(notes_pages)} notes pages...")
                try:
                    notes_table = extract_notes_from_pages(pdf, notes_pages)
                    result.notes_rows_extracted = len(notes_table.rows)
                    result.notes_pages = notes_pages
                    logger.info(
                        f"Notes: {len(notes_table.rows)} rows extracted from "
                        f"{len(notes_pages)} pages"
                    )
                    self._report_progress(
                        "Extracting Notes to Accounts", "completed", 100,
                        f"{len(notes_table.rows)} rows from {len(notes_pages)} pages"
                    )
                except Exception as e:
                    logger.warning(f"Notes extraction failed: {e}")
                    self._report_progress(
                        "Extracting Notes to Accounts", "failed", 0, str(e)
                    )
            else:
                logger.info("No Notes to Accounts pages found — skipping notes extraction")
                self._report_progress(
                    "Extracting Notes to Accounts", "completed", 100,
                    "No notes pages found"
                )
        finally:
            pdf.close()

        # Detect unit from extracted tables (use the first non-empty one)
        detected_unit = "Not specified"
        for table in [bs_table, pl_table, cf_table]:
            if table.unit and table.unit != "Not specified":
                detected_unit = table.unit
                break
        result.unit = detected_unit
        logger.info(f"Detected value unit: {detected_unit}")

        # ================================================================
        # STEP 4: Convert to tabular format and map to template
        # ================================================================
        logger.info("=" * 60)
        logger.info("STEP 4: Mapping extracted data to template items")
        logger.info("=" * 60)

        bs_mappings = []
        pl_mappings = []
        cf_mappings = []

        # --- Balance Sheet ---
        if bs_table.rows:
            self._report_progress("Mapping Balance Sheet data", "active", 0, "Converting to tabular format...")
            bs_headers, bs_rows = _convert_extracted_table_to_tabular(
                bs_table, BS_SECTION_MAP, target_year=year
            )
            logger.info(f"BS: Converted to {len(bs_rows)} tabular rows with sections")

            # Log section distribution
            section_counts = {}
            for row in bs_rows:
                sec = row[1] if len(row) > 1 else ""
                section_counts[sec] = section_counts.get(sec, 0) + 1
            logger.info(f"BS: Section distribution: {section_counts}")

            self._report_progress("Mapping Balance Sheet data", "active", 50, "LLM mapping + fuzzy fallback to template items...")
            bs_mappings = map_balance_sheet(
                bs_headers, bs_rows, target_year=year,
                llm=self.llm if self.use_llm else None,
            )
            result.bs_mapped = len(bs_mappings)
            logger.info(f"BS: {len(bs_mappings)} items mapped to template")

            # NOTE: Default zeros REMOVED per policy — only write 0 if the PDF
            # explicitly says 0/Nil/blank/—. Absent items are left blank (None).

            # Compute derived items (residuals)
            bs_derived = compute_derived_items(bs_mappings, BALANCE_SHEET_TEMPLATE)
            bs_mappings.extend(bs_derived)
            logger.info(f"BS: Added {len(bs_derived)} derived items")
            self._report_progress("Mapping Balance Sheet data", "completed", 100, f"{len(bs_mappings)} items mapped")

            # Optional LLM verification
            if self.verify_with_llm and self.llm:
                bs_mappings = _verify_mappings_with_llm(
                    bs_table, bs_mappings, self.llm, "balance_sheet"
                )

        # --- Profit & Loss ---
        if pl_table.rows:
            self._report_progress("Mapping P&L data", "active", 0, "Converting to tabular format...")
            pl_headers, pl_rows = _convert_extracted_table_to_tabular(
                pl_table, PL_SECTION_MAP, target_year=year
            )
            logger.info(f"P&L: Converted to {len(pl_rows)} tabular rows with sections")

            self._report_progress("Mapping P&L data", "active", 50, "LLM mapping + fuzzy fallback to template items...")
            pl_mappings = map_profit_and_loss(
                pl_headers, pl_rows, target_year=year,
                llm=self.llm if self.use_llm else None,
            )
            result.pl_mapped = len(pl_mappings)
            logger.info(f"P&L: {len(pl_mappings)} items mapped to template")

            # NOTE: Default zeros REMOVED per policy — only write 0 if the PDF
            # explicitly says 0/Nil/blank/—. Absent items are left blank (None).

            self._report_progress("Mapping P&L data", "completed", 100, f"{len(pl_mappings)} items mapped")

            # Optional LLM verification
            if self.verify_with_llm and self.llm:
                pl_mappings = _verify_mappings_with_llm(
                    pl_table, pl_mappings, self.llm, "profit_and_loss"
                )

        # --- Cash Flow ---
        if cf_table.rows:
            self._report_progress("Mapping Cash Flow data", "active", 0, "Converting to tabular format...")
            cf_headers, cf_rows = _convert_extracted_table_to_tabular(
                cf_table, CF_SECTION_MAP, target_year=year
            )
            logger.info(f"CF: Converted to {len(cf_rows)} tabular rows with sections")

            self._report_progress("Mapping Cash Flow data", "active", 50, "LLM mapping + fuzzy fallback to template items...")
            cf_mappings = map_cash_flow(
                cf_headers, cf_rows, target_year=year,
                llm=self.llm if self.use_llm else None,
            )
            result.cf_mapped = len(cf_mappings)
            logger.info(f"CF: {len(cf_mappings)} items mapped to template")

            # NOTE: Default zeros REMOVED per policy — only write 0 if the PDF
            # explicitly says 0/Nil/blank/—. Absent items are left blank (None).

            self._report_progress("Mapping Cash Flow data", "completed", 100, f"{len(cf_mappings)} items mapped")

            # Optional LLM verification
            if self.verify_with_llm and self.llm:
                cf_mappings = _verify_mappings_with_llm(
                    cf_table, cf_mappings, self.llm, "cash_flow"
                )

        # --- Notes to Accounts → "Other Financial Information" ---
        if notes_table.rows:
            self._report_progress("Mapping Notes to Other Financial Info", "active", 0, "Converting notes to tabular format...")
            notes_headers, notes_rows = _convert_extracted_table_to_tabular(
                notes_table, CF_SECTION_MAP, target_year=year
            )
            logger.info(f"Notes: Converted to {len(notes_rows)} tabular rows")

            self._report_progress("Mapping Notes to Other Financial Info", "active", 50, "LLM mapping + fuzzy fallback for OFI items...")
            notes_ofi_mappings = map_notes_to_other_financial_info(
                notes_headers, notes_rows, cf_mappings, year,
                target_year=year,
                llm=self.llm if self.use_llm else None,
            )

            if notes_ofi_mappings:
                # Merge notes mappings into cf_mappings, avoiding duplicates
                existing_cf_items = {r.template_item for r in cf_mappings}
                added_count = 0
                for nm in notes_ofi_mappings:
                    if nm.template_item not in existing_cf_items:
                        cf_mappings.append(nm)
                        existing_cf_items.add(nm.template_item)
                        added_count += 1

                result.notes_ofi_mapped = added_count
                logger.info(
                    f"Notes OFI: {added_count} new items added to CF mappings "
                    f"(out of {len(notes_ofi_mappings)} notes matches)"
                )

                # NOTE: Default zeros REMOVED — no re-applying default zeros
                # after notes merge. Absent items are left blank (None).

            self._report_progress(
                "Mapping Notes to Other Financial Info", "completed", 100,
                f"{result.notes_ofi_mapped} OFI items from notes"
            )

        # ================================================================
        # STEP 4.5b: CA Validation & Inference
        # ================================================================
        # Run Chartered Accountant-level validation and inferential mapping.
        # This goes beyond direct 1:1 label matching to:
        #   1. Cross-statement validation (BS equation, P&L equation, PAT consistency)
        #   2. Inferential mapping (EBITDA, EBIT, BS Profit from P&L PAT, Total Debt)
        #   3. Note cross-reference tracking (link BS/P&L items to their notes)
        #   4. Ind AS / Schedule III compliance checks
        logger.info("=" * 60)
        logger.info("STEP 4.5b: CA Validation & Inference")
        logger.info("=" * 60)
        self._report_progress(
            "CA Validation & Inference", "active", 0,
            "Running Chartered Accountant-level cross-statement validation..."
        )

        ca_report = run_ca_validation(bs_mappings, pl_mappings, cf_mappings)

        # Apply inferred mappings — only for items NOT already mapped
        existing_items = {m.template_item for m in bs_mappings + pl_mappings + cf_mappings}
        ca_applied = 0
        for im in ca_report.inferred_mappings:
            if im.template_item not in existing_items:
                # Convert InferredMapping to MappingResult
                inferred_mr = MappingResult(
                    template_item=im.template_item,
                    pdf_row_label=f"[CA Inferred] {im.reasoning[:80]}",
                    value=im.value,
                    confidence=im.confidence,
                    method=im.method,
                    section=im.section,
                )
                # Add to the appropriate mapping list
                # Determine which statement this belongs to
                if im.template_item in {k for sec in BALANCE_SHEET_TEMPLATE.values()
                                        if isinstance(sec, dict) for k in sec.keys()} or \
                   im.template_item in {"Total debt", "Profit for the year", "Change in FCTR",
                                        "NCI share of loss", "Total Equity and Liabilities",
                                        "Total Equity", "Total Liabilities", "Total Assets"}:
                    bs_mappings.append(inferred_mr)
                elif im.template_item in {k for sec in PL_TEMPLATE.values()
                                          if isinstance(sec, dict) for k in sec.keys()} or \
                     im.template_item in {"EBITDA", "EBIT"}:
                    pl_mappings.append(inferred_mr)
                else:
                    cf_mappings.append(inferred_mr)

                existing_items.add(im.template_item)
                ca_applied += 1
                logger.info(
                    f"CA INFERRED APPLIED: '{im.template_item}' = {im.value} "
                    f"(method={im.method}, confidence={im.confidence:.2f})"
                )
            else:
                logger.info(
                    f"CA INFERRED SKIPPED: '{im.template_item}' already mapped"
                )

        # Store CA stats in result
        result.ca_flags_count = len(ca_report.flags)
        result.ca_errors = len(ca_report.errors)
        result.ca_warnings = len(ca_report.warnings)
        result.ca_inferred = ca_applied
        result.ca_note_refs = len(ca_report.note_references)
        result.ca_balanced = ca_report.is_balanced

        logger.info(
            f"CA Validation complete: {ca_applied} inferred mappings applied, "
            f"{len(ca_report.errors)} errors, {len(ca_report.warnings)} warnings, "
            f"{len(ca_report.infos)} info flags, "
            f"BS balanced={'YES' if ca_report.is_balanced else 'NO'}"
        )
        self._report_progress(
            "CA Validation & Inference", "completed", 100,
            f"{ca_applied} inferred, {len(ca_report.errors)} errors, "
            f"{len(ca_report.warnings)} warnings"
        )

        # ================================================================
        # STEP 5: Write to Excel
        # ================================================================
        logger.info("=" * 60)
        logger.info("STEP 5: Writing to Excel template")
        logger.info("=" * 60)
        self._report_progress("Writing to Excel template", "active", 0, "Writing mapped values to Excel...")

        try:
            write_stats = write_all_sheets(
                template_path=template_path,
                output_path=output_path,
                bs_results=bs_mappings,
                pl_results=pl_mappings,
                cf_results=cf_mappings,
                year=year,
                bs_table=bs_table if bs_table.rows else None,
                pl_table=pl_table if pl_table.rows else None,
                cf_table=cf_table if cf_table.rows else None,
            )

            result.output_path = output_path

            # Extract write stats
            bs_stats = write_stats.get("balance_sheet", {})
            pl_stats = write_stats.get("profit_and_loss", {})
            cf_stats = write_stats.get("cash_flow", {})

            result.bs_written = bs_stats.get("written", 0)
            result.pl_written = pl_stats.get("written", 0)
            result.cf_written = cf_stats.get("written", 0)

            logger.info(f"BS: {bs_stats}")
            logger.info(f"P&L: {pl_stats}")
            logger.info(f"CF: {cf_stats}")
            self._report_progress("Writing to Excel template", "completed", 100,
                f"BS={result.bs_written}, P&L={result.pl_written}, CF={result.cf_written} values written")

        except Exception as e:
            error_msg = f"Failed to write Excel: {e}"
            logger.error(error_msg, exc_info=True)
            result.errors.append(error_msg)
            self._report_progress("Writing to Excel template", "failed", 0, error_msg)

        # ================================================================
        # STEP 6: Compute completeness
        # ================================================================
        self._report_progress("Computing completeness", "active", 0, "Calculating extraction completeness...")
        # BS template has 63 rows total, but many are formula/total rows
        # Count actual leaf items (non-formula, non-section-header)
        bs_leaf_count = _count_leaf_items(BALANCE_SHEET_TEMPLATE)
        pl_leaf_count = _count_leaf_items(PL_TEMPLATE)
        cf_leaf_count = _count_leaf_items(CASH_FLOW_TEMPLATE)

        # Count how many leaf items got values (non-None in the output)
        bs_filled = result.bs_written
        pl_filled = result.pl_written
        cf_filled = result.cf_written

        result.bs_completeness = min(1.0, bs_filled / bs_leaf_count) if bs_leaf_count else 0.0
        result.pl_completeness = min(1.0, pl_filled / pl_leaf_count) if pl_leaf_count else 0.0
        result.cf_completeness = min(1.0, cf_filled / cf_leaf_count) if cf_leaf_count else 0.0

        logger.info("=" * 60)
        logger.info("EXTRACTION COMPLETE")
        logger.info("=" * 60)
        logger.info(
            f"BS: {bs_filled}/{bs_leaf_count} items ({result.bs_completeness:.1%})"
        )
        logger.info(
            f"P&L: {pl_filled}/{pl_leaf_count} items ({result.pl_completeness:.1%})"
        )
        logger.info(
            f"CF: {cf_filled}/{cf_leaf_count} items ({result.cf_completeness:.1%})"
        )
        logger.info(
            f"Overall: {result.overall_completeness:.1%}"
        )
        if result.errors:
            logger.warning(f"Errors: {result.errors}")

        self._report_progress("Computing completeness", "completed", 100,
            f"BS={result.bs_completeness:.0%}, P&L={result.pl_completeness:.0%}, CF={result.cf_completeness:.0%}, Overall={result.overall_completeness:.0%}")

        # ================================================================
        # STEP 7: Write Meta Data sheet (after completeness is known)
        # ================================================================
        try:
            from datetime import datetime
            from .excel_writer import write_metadata_sheet

            metadata = {
                "pdf_filename": os.path.basename(pdf_path),
                "year": year,
                "year_detection_method": result.year_detection_method,
                "unit": result.unit,
                "statement_type": result.statement_type,
                "bs_pages": result.bs_pages,
                "pl_pages": result.pl_pages,
                "cf_pages": result.cf_pages,
                "notes_pages": result.notes_pages,
                "bs_rows_extracted": result.bs_rows_extracted,
                "pl_rows_extracted": result.pl_rows_extracted,
                "cf_rows_extracted": result.cf_rows_extracted,
                "notes_rows_extracted": result.notes_rows_extracted,
                "bs_mapped": result.bs_mapped,
                "pl_mapped": result.pl_mapped,
                "cf_mapped": result.cf_mapped,
                "notes_ofi_mapped": result.notes_ofi_mapped,
                "bs_written": result.bs_written,
                "pl_written": result.pl_written,
                "cf_written": result.cf_written,
                "bs_completeness": result.bs_completeness,
                "pl_completeness": result.pl_completeness,
                "cf_completeness": result.cf_completeness,
                "overall_completeness": result.overall_completeness,
                "extraction_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                # CA Validation metadata
                "ca_flags_count": result.ca_flags_count,
                "ca_errors": result.ca_errors,
                "ca_warnings": result.ca_warnings,
                "ca_inferred": result.ca_inferred,
                "ca_note_refs": result.ca_note_refs,
                "ca_balanced": result.ca_balanced,
                "ca_flags_detail": [
                    {
                        "severity": f.severity,
                        "category": f.category,
                        "statement": f.statement,
                        "message": f.message,
                        "item_name": f.item_name,
                    }
                    for f in ca_report.flags
                ],
                "ca_inferred_detail": [
                    {
                        "template_item": im.template_item,
                        "value": im.value,
                        "method": im.method,
                        "confidence": im.confidence,
                        "reasoning": im.reasoning,
                    }
                    for im in ca_report.inferred_mappings
                ],
            }

            write_metadata_sheet(output_path, metadata)
            logger.info("Meta Data sheet written successfully")
        except Exception as e:
            logger.warning(f"Failed to write Meta Data sheet: {e}")
            # Non-fatal — the main data sheets are already written

        return result


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _prefer_standalone(page_numbers: list[int], pdf_path: str) -> list[int]:
    """
    STANDALONE-ONLY POLICY: Extract only from standalone financial statements.

    Strategy: Check each page's title area for "Standalone" vs "Consolidated".
    - If standalone pages are found → return only those
    - If ONLY consolidated pages are found → return EMPTY list (skip extraction)
    - If no clear indicator → keep the page (assume standalone by default)

    Rationale: Per Schedule III of the Companies Act, 2013, standalone financial
    statements represent the company's own financials. Consolidated statements
    include subsidiaries and are not comparable on a like-for-like basis.
    This app requires standalone data only.
    """
    if len(page_numbers) <= 1:
        # Single page — check if it's explicitly consolidated
        if page_numbers:
            try:
                pdf = pdfplumber.open(pdf_path)
                page = pdf.pages[page_numbers[0] - 1]
                text = page.extract_text() or ""
                title_area = '\n'.join(text.split('\n')[:10]).lower()
                pdf.close()
                if 'consolidated' in title_area and 'standalone' not in title_area:
                    logger.info(
                        f"Standalone-only policy: skipping consolidated page {page_numbers[0]}"
                    )
                    return []
            except Exception:
                pass
        return page_numbers

    standalone_pages = []
    consolidated_pages = []

    try:
        pdf = pdfplumber.open(pdf_path)
        for pg in page_numbers:
            page = pdf.pages[pg - 1]
            text = page.extract_text() or ""
            # Check first 10 lines for standalone/consolidated indicator
            title_area = '\n'.join(text.split('\n')[:10]).lower()
            if 'standalone' in title_area:
                standalone_pages.append(pg)
            elif 'consolidated' in title_area:
                consolidated_pages.append(pg)
            else:
                # No clear indicator — assume standalone (default per Schedule III)
                standalone_pages.append(pg)
        pdf.close()
    except Exception:
        return page_numbers

    if standalone_pages:
        if consolidated_pages:
            logger.info(
                f"Standalone-only policy: using {len(standalone_pages)} standalone pages, "
                f"skipping {len(consolidated_pages)} consolidated pages"
            )
        return standalone_pages

    # ONLY consolidated pages found — skip extraction entirely
    logger.warning(
        f"Standalone-only policy: NO standalone pages found among {page_numbers}. "
        f"All {len(consolidated_pages)} pages are consolidated — skipping extraction."
    )
    return []


def _detect_statement_type(
    bs_pages: list[int],
    pl_pages: list[int],
    cf_pages: list[int],
    pdf_path: str,
) -> str:
    """
    Detect whether the extracted statements are Standalone or Consolidated.

    Checks the title area of the first page of each statement for keywords.
    If any page explicitly says "Standalone", returns "Standalone".
    If any page explicitly says "Consolidated", returns "Consolidated".
    Default is "Standalone" (most common for Indian annual reports).
    """
    all_pages = list(set(bs_pages + pl_pages + cf_pages))
    if not all_pages:
        return "Not specified"

    standalone_count = 0
    consolidated_count = 0

    try:
        pdf = pdfplumber.open(pdf_path)
        for pg in all_pages[:6]:  # Check first few pages
            if pg > len(pdf.pages) or pg < 1:
                continue
            page = pdf.pages[pg - 1]
            text = page.extract_text() or ""
            title_area = '\n'.join(text.split('\n')[:10]).lower()
            if 'standalone' in title_area:
                standalone_count += 1
            elif 'consolidated' in title_area:
                consolidated_count += 1
        pdf.close()
    except Exception:
        return "Not specified"

    if standalone_count > 0 and consolidated_count == 0:
        return "Standalone"
    elif consolidated_count > 0 and standalone_count == 0:
        return "Consolidated"
    elif standalone_count > consolidated_count:
        return "Standalone"
    elif consolidated_count > standalone_count:
        return "Consolidated"
    else:
        return "Standalone"  # Default


def _count_leaf_items(template: dict) -> int:
    """
    Count the number of leaf (non-formula, non-section-header) items
    in a template dict. These are the items that should receive values.
    """
    count = 0
    for key, value in template.items():
        if isinstance(value, dict) and value is not None:
            for sub_key in value.keys():
                if sub_key not in FORMULA_TEMPLATE_ITEMS:
                    count += 1
        else:
            if key not in FORMULA_TEMPLATE_ITEMS:
                count += 1
    return count


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================


def extract_annual_report(
    pdf_path: str,
    template_path: str,
    output_path: str,
    year: Optional[int] = None,
    llm=None,
    use_llm: bool = True,
) -> ExtractionResult:
    """
    One-call convenience function to extract financial data from an
    annual report PDF and populate the Excel template.

    Fully automatic — no manual page input required.

    Args:
        pdf_path: Path to the annual report PDF.
        template_path: Path to the Excel template file.
        output_path: Path to write the filled Excel file.
        year: Financial year (auto-detected if not provided).
        llm: LangChain ChatOpenAI instance (optional).
        use_llm: Whether to use LLM for fallback page identification.

    Returns:
        ExtractionResult with stats and completion info.
    """
    agent = SmartExtractionAgent(llm=llm, use_llm=use_llm)
    return agent.run(pdf_path, template_path, output_path, year)
