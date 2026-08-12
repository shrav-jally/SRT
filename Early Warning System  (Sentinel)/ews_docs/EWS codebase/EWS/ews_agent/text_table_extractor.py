"""
Text-Based Table Extractor Module

Extracts financial statement tables from PDF text using line-by-line parsing.

Key insight: pdfplumber's extract_text() produces well-structured text for
financial statements. Each line has:
    - A text label on the left (e.g., "Property, plant and equipment")
    - Optionally a note reference number
    - Numeric values on the right (e.g., "2,315.59  2,346.13  2,720.52")

This module parses each line using regex to deterministically separate
labels from values — no LLM needed, no word-position clustering needed.

This is similar to how Excel's "Get Data from PDF" works: it reads the
text content and uses pattern recognition to identify table structure.
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
class ExtractedRow:
    """A single row extracted from a financial statement table."""
    label: str = ""           # Line item label (e.g., "Property, plant and equipment")
    note_ref: str = ""        # Note reference (e.g., "4")
    values: list[str] = field(default_factory=list)  # Numeric values as strings
    indent_level: int = 0     # 0 = top-level, 1 = sub-item, 2 = sub-sub-item
    is_total: bool = False    # Whether this is a total/summary row
    is_section_header: bool = False  # Whether this is a section header (e.g., "ASSETS")
    raw_text: str = ""        # Original text for debugging


@dataclass
class ExtractedTable:
    """A complete financial statement table extracted from PDF pages."""
    statement_type: str = ""  # "balance_sheet", "profit_and_loss", "cash_flow"
    rows: list[ExtractedRow] = field(default_factory=list)
    year_headers: list[str] = field(default_factory=list)
    page_numbers: list[int] = field(default_factory=list)
    unit: str = ""            # e.g., "₹ millions"


# ============================================================================
# LINE PARSING
# ============================================================================

# Pattern to match numeric values in Indian financial statements:
# - Regular: 2,315.59, 948.46, 0.06
# - Negative: (9,955.85), (53.36)
# - Indian format: 1,10,680.38
# - Zero/dash: -, —
# - With rupee sign: ₹ 2,315.59
NUMERIC_PATTERN = r'(?:[\(]?\d[\d,]*\.?\d*[\)]?|[\-—–])'

# Pattern to match a line with label + optional note + values
# The label is text on the left, values are numeric on the right
LINE_WITH_VALUES = re.compile(
    r'^'
    r'(?P<label>\S.*?)'           # Label: starts with non-space, lazy match
    r'\s+'                         # Separator (spaces/tabs)
    r'(?P<values>'                 # Values group:
    r'(?:' + NUMERIC_PATTERN + r'\s*)+'  # One or more numeric values
    r')'
    r'$'
)

# Pattern for a line with just a label (section header, sub-item header)
LINE_LABEL_ONLY = re.compile(
    r'^'
    r'(?P<label>[A-Za-z\(\)][A-Za-z\s\(\)\-\,\.\&/]+)'  # Text label
    r'$'
)

# Pattern for note reference: a small integer that appears between label and values
NOTE_REF_PATTERN = re.compile(r'\b(\d{1,3})\b')


def _parse_line(line: str) -> Optional[ExtractedRow]:
    """
    Parse a single line of text into an ExtractedRow.

    Strategy:
    1. Extract all numeric values from the RIGHT side of the line
    2. Everything to the left of the first numeric value is the label
    3. Check if there's a note reference between label and values
    4. Check if the label contains an inline section header and split

    Args:
        line: A single line of text from the financial statement.

    Returns:
        ExtractedRow, or None if the line is not a data row.
    """
    line = line.strip()
    if not line:
        return None

    # Skip page numbers, headers, footers
    if re.match(r'^\d+$', line):
        return None
    if re.match(r'^Annual Report', line):
        return None
    if re.match(r'^STNEMETATS', line):  # Rotated sidebar text
        return None
    if re.match(r'^LAICNANIF', line):
        return None
    if re.match(r'^ENOLADNATS', line):
        return None
    if re.match(r'^GNITEEM', line):
        return None
    if re.match(r'^LARENEG', line):
        return None

    # Find all numeric tokens from the right side
    # We scan from right to left, collecting numeric values
    tokens = line.split()
    
    values = []
    value_start_idx = len(tokens)
    
    # Scan from right to left to find numeric values
    for i in range(len(tokens) - 1, -1, -1):
        token = tokens[i].rstrip('.,;:')
        if _is_numeric_token(token):
            values.insert(0, tokens[i])  # Preserve original formatting
            value_start_idx = i
        else:
            break
    
    # If no values found, this might be a section header or label-only line
    if not values:
        # Check if it's a meaningful label
        if len(line) > 2 and re.search(r'[A-Za-z]', line):
            row = ExtractedRow()
            row.label = line.strip()
            row.indent_level = _detect_indent_level(line)
            row.is_section_header = _is_section_header(line)
            row.is_total = _is_total_row(line)
            row.raw_text = line
            return row
        return None

    # Check if the leftmost "value" is actually a note reference
    # Note references are small integers (1-3 digits) that appear between
    # the label and the actual financial values
    note_ref = ""
    if len(values) >= 2:
        first_val = values[0].rstrip('.,;:')
        # A note ref is a small integer, NOT a financial value
        # Financial values have commas or decimals; note refs are plain integers
        if _is_note_reference(first_val) and not _is_financial_value(first_val):
            note_ref = first_val
            values = values[1:]
            value_start_idx += 1  # Adjust label boundary

    # Everything before the values is the label
    label_tokens = tokens[:value_start_idx]
    label_text = ' '.join(label_tokens)

    if not label_text.strip():
        # Line starts with values — might be a continuation or just numbers
        row = ExtractedRow()
        row.values = values
        row.note_ref = note_ref
        row.raw_text = line
        return row

    # Also check if the last token of the label is a note reference
    # (in case the right-to-left scan missed it)
    if not note_ref and label_tokens:
        last_label_token = label_tokens[-1].rstrip('.,;:')
        if _is_note_reference(last_label_token):
            note_ref = last_label_token
            label_tokens = label_tokens[:-1]
            label_text = ' '.join(label_tokens)

    # Check if the label contains an inline section header
    # e.g., "Right of use assets 38 Financial assets" → split into
    #   data row: "Right of use assets" (note=38) + section header: "Financial assets"
    data_label, inline_section = _split_inline_section_header(label_text)
    if inline_section:
        label_text = data_label
        # Re-extract note ref from the cleaned label
        if not note_ref:
            parts = label_text.rsplit(None, 1)
            if len(parts) == 2:
                last = parts[-1].rstrip('.,;:')
                if _is_note_reference(last):
                    note_ref = last
                    label_text = parts[0]

    row = ExtractedRow()
    row.label = label_text.strip()
    row.note_ref = note_ref
    row.values = values
    row.indent_level = _detect_indent_level(label_text)
    row.is_total = _is_total_row(label_text)
    # Only mark as section header if this row has NO values.
    # Data rows like "Income tax assets (net)" or "Equity share capital"
    # should never be section headers even if their label starts with a
    # section keyword.
    row.is_section_header = _is_section_header(label_text) if not values else False
    row.raw_text = line

    # If there was an inline section header, we need to emit it as a
    # separate section header row BEFORE this data row.
    # We handle this by returning a special two-row result via a list,
    # but since _parse_line returns a single row, we'll handle it
    # in the caller (extract_table_from_pages).
    # For now, store the inline section as a marker.
    if inline_section:
        row._inline_section = inline_section  # type: ignore[attr-defined]

    return row


def _is_numeric_token(token: str) -> bool:
    """
    Check if a token is a numeric value from a financial statement.

    Handles:
    - Regular numbers: 2,315.59, 948.46
    - Indian format: 1,10,680.38
    - Negative in parentheses: (9,955.85), (53.36)
    - Dash for zero: -, —, –
    - With rupee: ₹2,315.59
    """
    cleaned = token.strip().rstrip('.,;:')
    
    if cleaned in ('-', '—', '–', 'Nil', 'nil', 'NA', 'N.A.'):
        return True
    
    # Remove rupee symbol
    cleaned = cleaned.replace('₹', '')
    
    # Remove parentheses (negative numbers)
    inner = cleaned
    if inner.startswith('(') and inner.endswith(')'):
        inner = inner[1:-1]
    
    # Remove commas and try to parse
    inner = inner.replace(',', '')
    
    try:
        float(inner)
        return True
    except ValueError:
        return False


def _is_financial_value(token: str) -> bool:
    """Check if a token is a financial value (has commas or decimals)."""
    cleaned = token.strip().rstrip('.,;:')
    # Financial values have commas (1,315.59) or decimals (0.06)
    # Note references are plain integers without formatting
    if ',' in cleaned:
        return True
    if '.' in cleaned:
        return True
    if cleaned.startswith('(') and cleaned.endswith(')'):
        return True
    return False


def _is_note_reference(token: str) -> bool:
    """Check if a token is a note reference number (small integer)."""
    cleaned = token.strip().rstrip('.,;:')
    # Note references are typically 1-3 digit integers
    if re.match(r'^\d{1,3}$', cleaned):
        # But not if it looks like a year (2023, 2022, etc.)
        num = int(cleaned)
        if 1900 <= num <= 2100:
            return False
        return True
    return False


def _detect_indent_level(text: str) -> int:
    """
    Detect indent level from the label text.

    In financial statements, sub-items are indicated by:
    - Leading whitespace (from PDF text extraction)
    - Prefix patterns like "(i)", "(ii)", "(A)", "(B)"
    - Lower indentation in the hierarchy
    """
    # Check for leading whitespace
    leading_spaces = len(text) - len(text.lstrip())
    if leading_spaces >= 6:
        return 2
    elif leading_spaces >= 3:
        return 1

    # Check for parenthesized prefixes like (i), (ii), (A), (B)
    if re.match(r'^\([ivx]+\)', text) or re.match(r'^\([A-Z]\)', text):
        return 1

    return 0


def _is_section_header(label: str) -> bool:
    """
    Check if a label is a section header (e.g., 'ASSETS', 'EQUITY AND LIABILITIES').
    
    IMPORTANT: A section header must be a standalone label with NO values.
    Data rows like "Income tax assets (net)" or "Equity share capital" should
    NOT be classified as section headers even though they start with section keywords.
    This function only checks the label text — the caller must also verify that
    the row has no values before treating it as a section header.
    """
    label_stripped = label.strip()
    
    # All-caps section headers (e.g., "ASSETS", "EQUITY AND LIABILITIES")
    if label_stripped.isupper() and len(label_stripped) > 3:
        return True
    
    # Known section headers (mixed case) — EXACT match only
    # These are labels that appear as standalone section headers in financial statements.
    # We use EXACT match to avoid false positives on data rows like
    # "Income tax assets (net)" or "Equity share capital".
    exact_section_headers = {
        'Assets',
        'Equity and Liabilities',
        'Non-current assets',
        'Current assets',
        'Non-current liabilities',
        'Current liabilities',
        'Equity',
        'Liabilities',
        'Income',
        'Expenses',
        'A. Cash flows from operating activities',
        'B. Cash flow from investing activities',
        'C. Cash flow from financing activities',
        'Financial assets',
        'Financial liabilities',
        'Other financial information',
    }
    
    if label_stripped in exact_section_headers:
        return True
    
    # Case-insensitive and normalized matching for section headers.
    # Handles spacing/case variations like "Non Current Assets", "NON-CURRENT ASSETS",
    # "Non-Current Assets", "Non current assets", etc.
    label_norm = re.sub(r'[\s\-]', '', label_stripped.lower())
    for header in exact_section_headers:
        header_norm = re.sub(r'[\s\-]', '', header.lower())
        if label_norm == header_norm:
            return True
    
    # Compound section headers like "Non-current liabilities Financial liabilities"
    # These appear when two section headers are on the same line in the PDF
    compound_prefixes = [
        'Non-current assets',
        'Non-current liabilities',
        'Current assets',
        'Current liabilities',
    ]
    compound_suffixes = [
        'Financial assets',
        'Financial liabilities',
    ]
    for prefix in compound_prefixes:
        if label_stripped.startswith(prefix):
            remainder = label_stripped[len(prefix):].strip()
            if remainder in compound_suffixes:
                return True
    
    return False


# Known sub-section header phrases that appear inline with data labels
# e.g., "Right of use assets 38 Financial assets" — "Financial assets" is a sub-section
INLINE_SECTION_HEADERS = [
    'Financial assets',
    'Financial liabilities',
    'Non-current liabilities',
    'Current liabilities',
    'Non-current assets',
    'Current assets',
]


def _split_inline_section_header(label: str) -> tuple[str, str]:
    """
    Split a label that contains an inline section header.
    
    In PDFs, sometimes a data row and the next section header end up on
    the same line. For example:
        "Right of use assets 38 Financial assets"
        → ("Right of use assets 38", "Financial assets")
        "Inventories 10 Financial assets"
        → ("Inventories 10", "Financial assets")
    
    Returns:
        (data_label, section_header) — section_header is "" if no split needed.
    """
    for sh in INLINE_SECTION_HEADERS:
        # Look for the section header as a suffix after the data label
        # The section header must be preceded by a space
        idx = label.find(' ' + sh)
        if idx > 0:
            data_part = label[:idx].strip()
            sec_part = label[idx+1:].strip()
            # Verify the data part is meaningful (has at least 3 chars)
            if len(data_part) >= 3:
                return data_part, sec_part
    return label, ""


def _is_total_row(label: str) -> bool:
    """Check if a row label indicates a total/summary row."""
    label_lower = label.lower().strip()
    total_patterns = [
        r'^total\s+',
        r'\s+total\s*$',
        r'^total$',
    ]
    for pattern in total_patterns:
        if re.search(pattern, label_lower):
            return True
    return False


# ============================================================================
# PAGE TEXT EXTRACTION
# ============================================================================


def _extract_page_lines(
    page: pdfplumber.page.Page,
) -> list[str]:
    """
    Extract meaningful text lines from a PDF page.

    Filters out headers, footers, page numbers, and sidebar text.

    Args:
        page: pdfplumber page object.

    Returns:
        List of cleaned text lines.
    """
    text = page.extract_text() or ""
    if not text:
        return []

    lines = text.split('\n')
    cleaned = []

    for line in lines:
        line_stripped = line.strip()

        # Skip empty lines
        if not line_stripped:
            continue

        # Skip page number lines (e.g., "166 Annual Report 2022 - 2023")
        if re.match(r'^\d+\s+Annual Report', line_stripped):
            continue
        if re.match(r'^Annual Report\s+\d+', line_stripped):
            continue

        # Skip sidebar text (rotated text read as separate lines)
        if line_stripped in ('STNEMETATS', 'LAICNANIF', 'ENOLADNATS',
                            'GNITEEM', 'LARENEG', 'DETADILOSNOC'):
            continue

        # Skip pure page number
        if re.match(r'^\d{1,3}$', line_stripped):
            continue

        # Skip auditor/director signatures
        if any(kw in line_stripped.lower() for kw in [
            'as per our report', 'for walker chandiok', 'for and on behalf',
            'chartered accountants', 'icai firm', 'partner',
            'membership no', 'din:', 'bengaluru', 'may 2023',
            'chief financial officer', 'company secretary',
            'compliance officer', 'acs', 'the accompanying notes',
            'summary of significant accounting policies',
        ]):
            continue

        cleaned.append(line_stripped)

    return cleaned


# ============================================================================
# TABLE RECONSTRUCTION
# ============================================================================


# Patterns that indicate the START of a financial statement table
# (used to skip pre-statement text like auditor's report)
# IMPORTANT: These must be specific enough to NOT match auditor's report text
# that merely mentions the statement name in a sentence.
# Strategy: Require the line to look like a TITLE (short, starts with
# "Standalone"/"Consolidated", or is a known exact title).
#
# Two tiers of patterns:
#   - STRICT: Line must START with the pattern (^ anchor). High confidence.
#   - LENIENT: Pattern can appear anywhere in the line. Used as fallback
#     when strict patterns fail. This handles cases where the company name
#     or other text precedes the statement title.
STATEMENT_START_PATTERNS = {
    "balance_sheet": {
        "strict": [
            r'^standalone\s+balance\s+sheet',
            r'^consolidated\s+balance\s+sheet',
            r'^balance\s+sheet\s+as\s+at\s+\d',
            r'^balance\s+sheet\s*$',
            r'^balance\s+sheet\s+as\s+at',
            r'^balance\s+sheet\b',
        ],
        "lenient": [
            r'balance\s+sheet\s+as\s+at\s+\d',
            r'balance\s+sheet\s*$',
            r'\bbalance\s+sheet\b',
        ],
    },
    "profit_and_loss": {
        "strict": [
            r'^standalone\s+statement\s+of\s+profit',
            r'^consolidated\s+statement\s+of\s+profit',
            r'^statement\s+of\s+profit\s+and\s+loss',
            r'^statement\s+of\s+comprehensive\s+income',
            r'^statement\s+of\s+profit\s+loss',
            r'^profit\s+and\s+loss\s+statement',
            r'^profit\s+and\s+loss\s*$',
            r'^income\s+statement\b',
        ],
        "lenient": [
            r'statement\s+of\s+profit\s+and\s+loss',
            r'statement\s+of\s+comprehensive\s+income',
            r'profit\s+and\s+loss\s+statement',
            r'\bprofit\s+and\s+loss\b',
            r'\bincome\s+statement\b',
        ],
    },
    "cash_flow": {
        "strict": [
            r'^standalone\s+statement\s+of\s+cash',
            r'^consolidated\s+statement\s+of\s+cash',
            r'^statement\s+of\s+cash\s+flows?',
            r'^cash\s+flow\s+statement\b',
            r'^cash\s+flows?\s*$',
        ],
        "lenient": [
            r'statement\s+of\s+cash\s+flows?',
            r'cash\s+flow\s+statement',
            r'\bcash\s+flows?\b',
        ],
    },
}


def _find_statement_start(
    lines: list[str],
    statement_type: str,
) -> int:
    """
    Find the line index where the actual financial statement table begins.

    This skips pre-statement text like auditor's reports, certificates, etc.
    that may appear on the same page before the table.

    Uses a two-tier matching strategy:
      1. STRICT: Line must START with the pattern (^ anchor). High confidence,
         avoids false positives on auditor's report text.
      2. LENIENT: Pattern can appear anywhere in the line. Used as fallback
         when strict patterns fail. Handles cases where company name or other
         text precedes the statement title (e.g., "GODREJ PROPERTIES LIMITED
         Balance Sheet as at March 31, 2025").

    Returns:
        0-based line index where the statement starts, or -1 if not found.
    """
    pattern_dict = STATEMENT_START_PATTERNS.get(statement_type, {})
    strict_patterns = pattern_dict.get("strict", []) if isinstance(pattern_dict, dict) else pattern_dict
    lenient_patterns = pattern_dict.get("lenient", []) if isinstance(pattern_dict, dict) else []

    # Pass 1: Strict matching (line must start with the pattern)
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        for pattern in strict_patterns:
            if re.search(pattern, line_lower):
                return i

    # Pass 2: Lenient matching (pattern can appear anywhere in the line)
    # Only use if strict matching failed — this handles company-name-prefixed titles
    if lenient_patterns:
        for i, line in enumerate(lines):
            line_lower = line.lower().strip()
            # Skip very long lines (likely paragraph text, not titles)
            if len(line_lower) > 120:
                continue
            for pattern in lenient_patterns:
                if re.search(pattern, line_lower):
                    logger.debug(
                        f"Lenient match for {statement_type} on line {i}: "
                        f"'{line_lower[:80]}'"
                    )
                    return i

    return -1


def extract_table_from_pages(
    pdf: pdfplumber.PDF,
    page_numbers: list[int],
    statement_type: str,
) -> ExtractedTable:
    """
    Extract a financial statement table from specified PDF pages.

    Uses line-by-line text parsing — deterministic, no LLM needed.

    Args:
        pdf: Open pdfplumber PDF object.
        page_numbers: List of 1-indexed page numbers.
        statement_type: Type of financial statement.

    Returns:
        ExtractedTable with all rows from the specified pages.
    """
    result = ExtractedTable(statement_type=statement_type, page_numbers=page_numbers)

    all_rows = []
    seen_labels = set()  # For deduplication across pages
    statement_started = False  # Track if we've found the statement start

    for pg_idx, pg in enumerate(page_numbers):
        page = pdf.pages[pg - 1]  # 0-indexed
        lines = _extract_page_lines(page)

        # Skip pre-statement text (auditor's report, certificates, etc.)
        # Check EVERY page until we find the statement start.
        start_idx = 0
        if not statement_started:
            found_idx = _find_statement_start(lines, statement_type)
            if found_idx >= 0:
                # Found the statement title on this page
                start_idx = found_idx
                statement_started = True
                if found_idx > 0:
                    logger.info(
                        f"Skipping {found_idx} pre-statement lines on page {pg} "
                        f"for {statement_type}"
                    )
            else:
                # Statement title not found on this page — skip entirely
                # (it's likely an auditor's report or certificate page)
                logger.info(
                    f"Page {pg} has no {statement_type} title — skipping entirely"
                )
                continue

        for line_idx in range(start_idx, len(lines)):
            line = lines[line_idx]
            row = _parse_line(line)
            if row is None:
                continue

            # Handle inline section headers: emit section header row first
            inline_section = getattr(row, '_inline_section', None)
            if inline_section:
                sec_row = ExtractedRow(
                    label=inline_section,
                    indent_level=0,
                    is_section_header=True,
                    raw_text=f"(inline section: {inline_section})",
                )
                all_rows.append(sec_row)
                # Remove the marker from the data row
                delattr(row, '_inline_section')

            # Deduplication: skip if we've seen this exact label
            # (handles cases where both standalone and consolidated are detected)
            label_key = row.label.lower().strip()
            if label_key in seen_labels and row.values:
                # Check if values are different (might be consolidated vs standalone)
                existing = next((r for r in all_rows if r.label.lower().strip() == label_key), None)
                if existing and existing.values == row.values:
                    continue  # Exact duplicate

            if label_key:
                seen_labels.add(label_key)

            all_rows.append(row)

    # Post-process
    result.rows = _post_process_rows(all_rows, statement_type)
    result.year_headers = _extract_year_headers(all_rows)

    # Fallback: if row-based year header extraction failed, scan page text directly
    if not result.year_headers:
        result.year_headers = _extract_year_headers_from_page_text(pdf, page_numbers)
        if result.year_headers:
            logger.info(
                f"Year headers from page-text fallback: {result.year_headers}"
            )

    # Detect unit from all pages (not just first)
    result.unit = _detect_unit(pdf, page_numbers)

    logger.info(f"Extracted {len(result.rows)} rows from {len(page_numbers)} pages "
               f"for {statement_type}")

    return result


def _merge_fragmented_rows(rows: list[ExtractedRow]) -> list[ExtractedRow]:
    """
    Merge rows that were fragmented across multiple lines in the PDF.

    Common fragmentation patterns in Indian annual reports:
        1. Label-only line followed by values-only line:
           "(A) Total outstanding dues of micro enterprises and small"
           "23  -  -  -"
           → Merge into one row with label + values

        2. Label-only line followed by continuation text:
           "(A) Total outstanding dues of micro enterprises and small"
           "enterprises; and"
           → Merge labels together

        3. Data row followed by continuation text:
           "Trade payables  2,315.59  2,346.13"
           "(unsecured)"
           → Append continuation to label

    Strategy:
        - Look ahead at the next row(s) to detect fragmentation
        - Merge when: current row has no values and next has values (pattern 1)
        - Merge when: current row has no values and next has no values but
          has a short label that looks like continuation (pattern 2)
        - Merge when: current row has values and next has no values and
          next label looks like continuation (pattern 3)
    """
    if not rows:
        return rows

    merged = []
    i = 0

    while i < len(rows):
        current = rows[i]

        # --- Pattern 1: Label-only row followed by values-only row ---
        # Current has label but no values; next has values but no (or minimal) label
        if (not current.values and current.label
                and i + 1 < len(rows)):
            next_row = rows[i + 1]
            merged_row = None

            # Next row has values but no meaningful label
            if next_row.values and (not next_row.label or len(next_row.label) <= 3):
                # Merge: current label + next values/note
                merged_row = ExtractedRow(
                    label=current.label,
                    note_ref=next_row.note_ref or current.note_ref,
                    values=next_row.values,
                    indent_level=current.indent_level,
                    is_total=current.is_total,
                    is_section_header=current.is_section_header,
                    raw_text=f"{current.raw_text} | {next_row.raw_text}",
                )
                i += 2

            # Next row has values AND a note ref as label (e.g., "23")
            elif next_row.values and next_row.label and _is_note_reference(next_row.label.rstrip('.,;:')):
                merged_row = ExtractedRow(
                    label=current.label,
                    note_ref=next_row.label.rstrip('.,;:'),
                    values=next_row.values,
                    indent_level=current.indent_level,
                    is_total=current.is_total,
                    is_section_header=current.is_section_header,
                    raw_text=f"{current.raw_text} | {next_row.raw_text}",
                )
                i += 2

            if merged_row is not None:
                # After Pattern 1 merge, also consume any continuation text
                # e.g., "(A) Total outstanding dues of micro enterprises and small"
                #        + "23  -  -  -"  (values row)
                #        + "enterprises; and"  (continuation)
                while i < len(rows) and _is_continuation_text(rows[i]):
                    merged_row.label = f"{merged_row.label} {rows[i].label}".strip()
                    merged_row.raw_text = f"{merged_row.raw_text} | {rows[i].raw_text}"
                    i += 1
                merged.append(merged_row)
                continue

        # --- Pattern 2 & 3: Continuation text lines ---
        # A continuation line is a label-only row that doesn't look like a
        # section header or a new item. It typically:
        #   - Starts with lowercase or semicolon
        #   - Is short (< 60 chars)
        #   - Doesn't start with a roman numeral or lettered prefix like (i), (A)
        if (i + 1 < len(rows)):
            next_row = rows[i + 1]

            if _is_continuation_text(next_row):
                # Append continuation to current row's label
                current.label = f"{current.label} {next_row.label}".strip()
                current.raw_text = f"{current.raw_text} | {next_row.raw_text}"
                merged.append(current)
                i += 2

                # Keep consuming continuation lines
                while i < len(rows) and _is_continuation_text(rows[i]):
                    current.label = f"{current.label} {rows[i].label}".strip()
                    i += 1
                continue

        # No merging needed — keep as-is
        merged.append(current)
        i += 1

    return merged


def _is_continuation_text(row: ExtractedRow) -> bool:
    """
    Check if a row is a continuation text line (not a new item).

    Continuation lines:
      - Have a label but no values
      - Don't look like section headers
      - Typically start with lowercase, semicolon, or are short fragments
      - Don't start with a new item prefix like (i), (A), roman numerals
      - Don't look like known sub-section headers (Financial assets, etc.)
    """
    if not row.label or row.values:
        return False

    label = row.label.strip()

    # Not a continuation if it's a section header
    if row.is_section_header:
        return False

    # Not a continuation if it matches a known sub-section header
    # (even if _is_section_header didn't catch it — e.g., "Financial assets"
    # appearing as a standalone line)
    known_subsections = {
        'financial assets', 'financial liabilities',
        'non-current assets', 'non-current liabilities',
        'current assets', 'current liabilities',
        'operating activities', 'investing activities', 'financing activities',
        'equity', 'liabilities', 'assets', 'income', 'expenses',
    }
    if label.lower() in known_subsections:
        return False

    # Not a continuation if it starts with a new item prefix
    # e.g., "(i)", "(ii)", "(A)", "(B)", "I.", "II.", "1.", "2."
    if re.match(r'^\([ivx]+\)', label, re.IGNORECASE):
        return False
    if re.match(r'^\([A-Z]\)', label):
        return False
    if re.match(r'^[IVX]+\.', label):
        return False
    if re.match(r'^\d+\.', label):
        return False

    # Continuation if starts with lowercase or connecting punctuation
    if label[0].islower() or label.startswith(';') or label.startswith('and '):
        return True

    # Short fragments (< 40 chars) with no values that don't start a new item
    # AND don't start with a capital letter followed by more capitals
    # (to avoid treating "Financial assets" as continuation)
    if len(label) < 40 and not re.match(r'^[A-Z][a-z]+\s+[a-z]', label):
        # Only treat as continuation if it looks like a sentence fragment,
        # not a title-cased phrase
        words = label.split()
        if len(words) <= 3 and all(w[0].isupper() for w in words if w):
            return False  # Title-cased short phrase = likely a new item
        return True

    return False


def _post_process_rows(
    rows: list[ExtractedRow],
    statement_type: str,
) -> list[ExtractedRow]:
    """
    Post-process extracted rows: merge fragmented rows, clean labels, remove junk.
    """
    # First pass: merge fragmented multi-line rows
    rows = _merge_fragmented_rows(rows)

    processed = []

    for row in rows:
        # Skip rows with very short labels that aren't meaningful
        if len(row.label) < 2 and not row.values:
            continue

        # Skip the company name line
        if row.label.upper() in ('SOBHA LIMITED',) and not row.values:
            continue

        # Skip the unit declaration line
        if 'amounts in' in row.label.lower() and 'unless otherwise' in row.label.lower():
            continue

        # Skip "(continued)" lines
        if row.label.lower().strip() in ('(continued)', 'continued'):
            continue

        # Clean up label
        row.label = row.label.strip()

        # Remove trailing note numbers that got merged into label
        # e.g., "Property, plant and equipment 4" -> label="Property, plant and equipment", note="4"
        if not row.note_ref and row.values:
            label_parts = row.label.rsplit(None, 1)
            if len(label_parts) == 2:
                last_part = label_parts[-1].rstrip('.,;:')
                if _is_note_reference(last_part):
                    row.label = label_parts[0]
                    row.note_ref = last_part

        if row.label:
            processed.append(row)

    return processed


def _extract_year_headers(rows: list[ExtractedRow]) -> list[str]:
    """
    Extract year header strings from header rows or page text.
    
    Handles multiple Indian annual report date formats:
        - "As at March 31, 2018"
        - "As at 31st March, 2018"
        - "Year ended March 31, 2018"
        - "March 31, 2018"
        - "31 March 2018"
        - "As at 1st April, 2018"
        - "Year ended 31st March 2018"
    
    Also scans rows WITH values (not just label-only rows), since some PDFs
    put the year header on the same line as the first data row.
    
    Returns year header strings in the order they appear (first = leftmost
    column in the PDF, typically current year in Indian reports).
    """
    # Pattern 1: Full date expressions with year (4-digit)
    # Matches: "As at March 31, 2018", "Year ended 31st March, 2018", etc.
    date_patterns = [
        # "As at March 31, 2018" / "As at 31st March, 2018"
        r'(?:As\s+at\s+)?(?:1st\s+)?(?:March|April)\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}',
        # "As at 31 March 2018" / "31st March 2018"
        r'(?:As\s+at\s+)?\d{1,2}(?:st|nd|rd|th)?\s+(?:March|April),?\s*\d{4}',
        # "Year ended March 31, 2018"
        r'Year\s+ended\s+(?:March|April)\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}',
        # "Year ended 31st March 2018"
        r'Year\s+ended\s+\d{1,2}(?:st|nd|rd|th)?\s+(?:March|April),?\s*\d{4}',
    ]
    
    # Collect all year header strings found, preserving order
    found_headers = []
    seen_years = set()
    
    for row in rows:
        label = row.label
        if not label:
            continue
        
        for pattern in date_patterns:
            matches = re.findall(pattern, label, re.IGNORECASE)
            for m in matches:
                # Extract the year to check for duplicates
                year_match = re.search(r'(20\d{2})', m)
                if year_match:
                    year = year_match.group(1)
                    if year not in seen_years:
                        found_headers.append(m.strip())
                        seen_years.add(year)
        
        # Also check for standalone year patterns in label-only rows
        # e.g., "2018 2017" as a header row
        if not row.values:
            year_matches = re.findall(r'\b(20\d{2})\b', label)
            for y in year_matches:
                if y not in seen_years:
                    found_headers.append(y)
                    seen_years.add(y)
    
    return found_headers


def _extract_year_headers_from_page_text(
    pdf: pdfplumber.PDF,
    page_numbers: list[int],
) -> list[str]:
    """
    Extract year header strings by scanning page text directly.
    
    This is a fallback for when _extract_year_headers() fails on parsed rows.
    Some PDFs have year headers that get mangled during line parsing (e.g.,
    the header row gets split across lines or merged with data).
    
    Scans the first 15 lines of each page for date patterns containing years.
    
    Returns year header strings ordered by year (descending = current first).
    """
    date_patterns = [
        r'(?:As\s+at\s+)?(?:1st\s+)?(?:March|April)\s+\d{1,2}(?:st|nd|rd|th)?,?\s*(20\d{2})',
        r'(?:As\s+at\s+)?\d{1,2}(?:st|nd|rd|th)?\s+(?:March|April),?\s*(20\d{2})',
        r'Year\s+ended\s+(?:March|April)\s+\d{1,2}(?:st|nd|rd|th)?,?\s*(20\d{2})',
        r'Year\s+ended\s+\d{1,2}(?:st|nd|rd|th)?\s+(?:March|April),?\s*(20\d{2})',
    ]
    
    found_years = []
    
    for pg in page_numbers[:3]:  # Scan first 3 pages
        if pg > len(pdf.pages) or pg < 1:
            continue
        try:
            page = pdf.pages[pg - 1]
            text = page.extract_text() or ""
            lines = text.split('\n')[:15]  # First 15 lines
            
            for line in lines:
                for pattern in date_patterns:
                    matches = re.findall(pattern, line, re.IGNORECASE)
                    for year_str in matches:
                        year = int(year_str)
                        if year not in found_years:
                            found_years.append(year)
        except Exception:
            continue
    
    if not found_years:
        return []
    
    # Sort descending (current year first) and construct header strings
    found_years.sort(reverse=True)
    return [str(y) for y in found_years]


# ============================================================================
# UNIT DETECTION
# ============================================================================


def _detect_unit(pdf: pdfplumber.PDF, page_numbers: list[int]) -> str:
    """
    Detect the unit of measurement used in the financial statements.

    Scans the first few pages of the statement for common unit declarations
    like "₹ in Lakhs", "₹ in Crores", "₹ in Millions", "₹ in Thousands", etc.

    Indian annual reports typically declare the unit in one of these ways:
        - "₹ in Lakhs" / "₹ in lakhs" / "Rs. in Lakhs"
        - "₹ in Crores" / "₹ in crores" / "Rs. in Crores"
        - "₹ in Millions" / "₹ in millions"
        - "₹ in Thousands" / "₹ in thousands"
        - "Amounts in lakhs of Rupees unless otherwise stated"
        - "Figures in lakhs" / "Figures in crores"
        - "(All amounts in lakhs of ₹ unless otherwise stated)"

    Args:
        pdf: Open pdfplumber PDF object.
        page_numbers: List of 1-indexed page numbers to scan.

    Returns:
        Unit string, e.g., "₹ in Lakhs", "₹ in Crores", "₹ in Millions",
        "₹ in Thousands", or "Not specified" if not detected.
    """
    # Unit patterns ordered by specificity (most specific first)
    # Each pattern maps to a standardized unit string
    unit_patterns = [
        # With ₹ symbol
        (r'₹\s*in\s+lakhs?', "₹ in Lakhs"),
        (r'₹\s*in\s+crores?', "₹ in Crores"),
        (r'₹\s*in\s+millions?', "₹ in Millions"),
        (r'₹\s*in\s+thousands?', "₹ in Thousands"),
        # With Rs./Rs
        (r'rs\.?\s*in\s+lakhs?', "₹ in Lakhs"),
        (r'rs\.?\s*in\s+crores?', "₹ in Crores"),
        (r'rs\.?\s*in\s+millions?', "₹ in Millions"),
        (r'rs\.?\s*in\s+thousands?', "₹ in Thousands"),
        # "Amounts in" / "Figures in" / "All amounts in"
        (r'(?:all\s+)?amounts?\s+in\s+lakhs?', "₹ in Lakhs"),
        (r'(?:all\s+)?amounts?\s+in\s+crores?', "₹ in Crores"),
        (r'(?:all\s+)?amounts?\s+in\s+millions?', "₹ in Millions"),
        (r'(?:all\s+)?amounts?\s+in\s+thousands?', "₹ in Thousands"),
        (r'figures?\s+in\s+lakhs?', "₹ in Lakhs"),
        (r'figures?\s+in\s+crores?', "₹ in Crores"),
        (r'figures?\s+in\s+millions?', "₹ in Millions"),
        (r'figures?\s+in\s+thousands?', "₹ in Thousands"),
        # "lakhs of Rupees" / "crores of Rupees"
        (r'lakhs?\s+of\s+rupees?', "₹ in Lakhs"),
        (r'crores?\s+of\s+rupees?', "₹ in Crores"),
        (r'millions?\s+of\s+rupees?', "₹ in Millions"),
        # Standalone unit in parentheses
        (r'\(\s*all\s+amounts\s+in\s+lakhs?', "₹ in Lakhs"),
        (r'\(\s*all\s+amounts\s+in\s+crores?', "₹ in Crores"),
        (r'\(\s*all\s+amounts\s+in\s+millions?', "₹ in Millions"),
        (r'\(\s*all\s+amounts\s+in\s+thousands?', "₹ in Thousands"),
        # "₹ Lakhs" / "₹ Crores" (short form)
        (r'₹\s*lakhs?', "₹ in Lakhs"),
        (r'₹\s*crores?', "₹ in Crores"),
        (r'₹\s*millions?', "₹ in Millions"),
    ]

    # Scan the first 3 pages of the statement
    for pg in page_numbers[:3]:
        try:
            page = pdf.pages[pg - 1]
            text = page.extract_text() or ""
            text_lower = text.lower()

            for pattern, unit_str in unit_patterns:
                if re.search(pattern, text_lower):
                    logger.info(f"Detected unit '{unit_str}' from page {pg}")
                    return unit_str
        except Exception:
            continue

    return "Not specified"


# ============================================================================
# NOTES EXTRACTION
# ============================================================================


def extract_notes_from_pages(
    pdf: pdfplumber.PDF,
    page_numbers: list[int],
) -> ExtractedTable:
    """
    Extract data from Notes to Accounts pages.

    Unlike financial statements, notes pages don't have a single "statement
    start" title. Instead, each page may contain multiple notes, each with
    their own note number and title. We parse ALL lines on every page.

    The notes section contains data needed for the CF template's "Other
    Financial Information" items (Contingent Liabilities, Current maturities,
    Power and fuel, Bad debts, Auditors Remuneration, RP items, etc.)

    Args:
        pdf: Open pdfplumber PDF object.
        page_numbers: List of 1-indexed page numbers for the notes section.

    Returns:
        ExtractedTable with all rows from the notes pages.
    """
    result = ExtractedTable(
        statement_type="notes",
        page_numbers=page_numbers,
    )

    all_rows = []

    for pg in page_numbers:
        if pg > len(pdf.pages) or pg < 1:
            continue

        page = pdf.pages[pg - 1]
        lines = _extract_page_lines(page)

        for line in lines:
            row = _parse_line(line)
            if row is None:
                continue

            # Handle inline section headers
            inline_section = getattr(row, '_inline_section', None)
            if inline_section:
                sec_row = ExtractedRow(
                    label=inline_section,
                    indent_level=0,
                    is_section_header=True,
                    raw_text=f"(inline section: {inline_section})",
                )
                all_rows.append(sec_row)
                delattr(row, '_inline_section')

            if row.label or row.values:
                all_rows.append(row)

    # Post-process (merge fragmented rows, clean labels)
    result.rows = _post_process_rows(all_rows, "notes")
    result.year_headers = _extract_year_headers(all_rows)

    # Fallback: if row-based year header extraction failed, scan page text directly
    if not result.year_headers:
        result.year_headers = _extract_year_headers_from_page_text(pdf, page_numbers)
        if result.year_headers:
            logger.info(
                f"Notes: Year headers from page-text fallback: {result.year_headers}"
            )

    # Detect unit from notes pages
    result.unit = _detect_unit(pdf, page_numbers)

    logger.info(
        f"Extracted {len(result.rows)} rows from {len(page_numbers)} "
        f"notes pages"
    )

    return result


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================


def extract_financial_statement(
    pdf_path: str,
    page_numbers: list[int],
    statement_type: str,
) -> ExtractedTable:
    """
    Extract a financial statement table from a PDF.

    Args:
        pdf_path: Path to the PDF file.
        page_numbers: List of 1-indexed page numbers.
        statement_type: "balance_sheet", "profit_and_loss", or "cash_flow".

    Returns:
        ExtractedTable with all rows.
    """
    pdf = pdfplumber.open(pdf_path)
    try:
        return extract_table_from_pages(pdf, page_numbers, statement_type)
    finally:
        pdf.close()
