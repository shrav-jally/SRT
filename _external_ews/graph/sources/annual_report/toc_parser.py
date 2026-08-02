"""Table of Contents parser for Indian annual report PDFs.

Scans the first pages of a PDF for a Table of Contents / Index page,
parses the entries to find page references for financial statements,
and returns page hints that can be fed into the extraction pipeline.

This serves as "Pass 0" — before heading-based detection — to narrow
down the search area for each financial statement.

Supported TOC formats
---------------------
1. Dotted leaders with page numbers::

       Consolidated Balance Sheet………………........ 180
       Standalone Statement of Profit and Loss….... 251

2. Plain numbers after section names::

       Standalone Financials 155
       Consolidated Financials 243

3. Split numbers in multi-column layout (Brightcom style)::

       STANDALONE FINANCIALS 11 5
       CONSOLIDATED FINANCIALS 16 7

4. Two-column TOC with separate standalone/consolidated sections::

       Standalone Financial Statements     Consolidated Financial Statements
       Balance Sheet ........... 250       Balance Sheet ........... 180
       Profit and Loss ......... 251       Profit and Loss ......... 181

5. CID-encoded page numbers (custom font encoding)::

       STANDALONE FINANCIAL STATEMENTS (cid:56)(cid:56)

LLM fallback
------------
When regex-based parsing fails to extract enough entries (e.g. due to
unusual formatting, CID encoding, or two-column layouts that confuse
line-by-line parsing), the raw TOC text is sent to the LLM for
structured extraction.  The LLM identifies financial statement entries
and their page numbers, which are then fed into the same offset
detection and hint-building pipeline.

Page number offset
------------------
The TOC references "printed page numbers" which may differ from the
0-based PDF page index.  The parser detects the offset by checking
a few candidate pages around each TOC reference and verifying the
content matches the TOC description.  If the offset cannot be
determined automatically, a generous search window is used instead.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ===================================================================
# Data structures
# ===================================================================

@dataclass
class TocEntry:
    """A single entry parsed from the Table of Contents."""
    description: str
    page_number: int  # printed page number from TOC
    raw_line: str = ""


@dataclass
class TocPageHints:
    """Page hints derived from the Table of Contents.

    Maps internal statement types to lists of 1-based PDF page numbers
    where the statement is likely to be found.
    """
    hints: dict[str, list[int]] = field(default_factory=dict)
    toc_pages: list[int] = field(default_factory=list)
    page_offset: int | None = None
    page_offsets: dict[str, int] = field(default_factory=dict)  # per-entity offsets
    raw_entries: list[TocEntry] = field(default_factory=list)


# ===================================================================
# Keywords for matching TOC entries to statement types
# ===================================================================

# Each pattern maps to one or more internal statement types.
# The patterns are checked in order; first match wins.
_TOC_STATEMENT_PATTERNS: list[tuple[re.Pattern, list[str]]] = [
    # Specific statement patterns (check before generic section patterns)
    (
        re.compile(
            r"\bstandalone\s+balance\s+sheet\b",
            re.IGNORECASE,
        ),
        ["standalone_balance_sheet"],
    ),
    (
        re.compile(
            r"\bconsolidated\s+balance\s+sheet\b",
            re.IGNORECASE,
        ),
        ["consolidated_balance_sheet"],
    ),
    (
        re.compile(
            r"\bstandalone\s+(?:statement\s+of\s+)?profit\s+(?:and|&)\s+(?:loss|or\s+loss)\b",
            re.IGNORECASE,
        ),
        ["standalone_profit_and_loss"],
    ),
    (
        re.compile(
            r"\bconsolidated\s+(?:statement\s+of\s+)?profit\s+(?:and|&)\s+(?:loss|or\s+loss)\b",
            re.IGNORECASE,
        ),
        ["consolidated_profit_and_loss"],
    ),
    (
        re.compile(
            r"\bstandalone\s+(?:statement\s+of\s+)?cash\s+flows?\b",
            re.IGNORECASE,
        ),
        ["standalone_cash_flow"],
    ),
    (
        re.compile(
            r"\bconsolidated\s+(?:statement\s+of\s+)?cash\s+flows?\b",
            re.IGNORECASE,
        ),
        ["consolidated_cash_flow"],
    ),
    # Generic section patterns — map to ALL statements of that entity
    (
        re.compile(
            r"\bstandalone\s+financial\s+(?:statements?|s)\b",
            re.IGNORECASE,
        ),
        ["standalone_balance_sheet", "standalone_profit_and_loss", "standalone_cash_flow"],
    ),
    (
        re.compile(
            r"\bconsolidated\s+financial\s+(?:statements?|s)\b",
            re.IGNORECASE,
        ),
        ["consolidated_balance_sheet", "consolidated_profit_and_loss", "consolidated_cash_flow"],
    ),
    # Shorter forms
    (
        re.compile(
            r"\bstandalone\s+financials\b",
            re.IGNORECASE,
        ),
        ["standalone_balance_sheet", "standalone_profit_and_loss", "standalone_cash_flow"],
    ),
    (
        re.compile(
            r"\bconsolidated\s+financials\b",
            re.IGNORECASE,
        ),
        ["consolidated_balance_sheet", "consolidated_profit_and_loss", "consolidated_cash_flow"],
    ),
    # Entity-agnostic patterns — match without "Standalone"/"Consolidated"
    # prefix.  These map to BOTH entity variants; entity context is
    # resolved later in _match_entries_to_statements() using section
    # boundaries from nearby section-level entries.
    # IMPORTANT: These must come AFTER the specific patterns above so
    # that "Standalone Balance Sheet" matches the specific pattern first.
    (
        re.compile(
            r"\bbalance\s+sheet\b",
            re.IGNORECASE,
        ),
        ["standalone_balance_sheet", "consolidated_balance_sheet"],
    ),
    (
        re.compile(
            r"\bstatement\s+of\s+financial\s+position\b",
            re.IGNORECASE,
        ),
        ["standalone_balance_sheet", "consolidated_balance_sheet"],
    ),
    (
        re.compile(
            r"\b(?:statement\s+of\s+)?profit\s+(?:and|&)\s+(?:loss|or\s+loss)\b",
            re.IGNORECASE,
        ),
        ["standalone_profit_and_loss", "consolidated_profit_and_loss"],
    ),
    (
        re.compile(
            r"\bincome\s+statement\b",
            re.IGNORECASE,
        ),
        ["standalone_profit_and_loss", "consolidated_profit_and_loss"],
    ),
    (
        re.compile(
            r"\b(?:statement\s+of\s+)?cash\s+flows?\b",
            re.IGNORECASE,
        ),
        ["standalone_cash_flow", "consolidated_cash_flow"],
    ),
    # Fix 36: Additional entity-agnostic patterns common in Indian
    # annual reports.  These use phrasings like "Profit & Loss Account",
    # "Cash Flow Statement", "Balance Sheet as at", etc.
    (
        re.compile(
            r"\bprofit\s+(?:and|&)\s+loss\s+account\b",
            re.IGNORECASE,
        ),
        ["standalone_profit_and_loss", "consolidated_profit_and_loss"],
    ),
    (
        re.compile(
            r"\bcash\s+flow\s+statement\b",
            re.IGNORECASE,
        ),
        ["standalone_cash_flow", "consolidated_cash_flow"],
    ),
    (
        re.compile(
            r"\bbalance\s+sheet\s+as\s+at\b",
            re.IGNORECASE,
        ),
        ["standalone_balance_sheet", "consolidated_balance_sheet"],
    ),
    (
        re.compile(
            r"\bstatement\s+of\s+profit\s+(?:and|&)\s+loss\b",
            re.IGNORECASE,
        ),
        ["standalone_profit_and_loss", "consolidated_profit_and_loss"],
    ),
    # NOTE: We do NOT add an entity-agnostic "Financial Statements"
    # pattern here because it is too broad — it matches entries like
    # "Integrated Reporting Framework Financial Statements" which are
    # NOT financial statement section headers.  Section-level context
    # is already captured by the entity-specific patterns above
    # ("Standalone Financial Statements", "Consolidated Financials", etc.).
]

# Keywords that identify a TOC/Index page
_TOC_PAGE_KEYWORDS = [
    "contents",
    "content",
    "table of contents",
    "index",
    "list of",
    "list of tables",
    "list of contents",
]

# Maximum number of pages to scan from the start for a TOC
_MAX_TOC_SCAN_PAGES = 40

# Search window around a TOC-referenced page number when
# verifying content (accounts for page offset uncertainty)
_PAGE_SEARCH_WINDOW = 5


# ===================================================================
# Main entry point
# ===================================================================

def parse_toc_for_page_hints(
    pdf_path: str | Path,
    pages: list[dict] | None = None,
    progress_callback=None,
) -> TocPageHints:
    """Parse the Table of Contents from a PDF and derive page hints.

    Parameters
    ----------
    pdf_path : str | Path
        Path to the annual report PDF.
    pages : list[dict], optional
        Pre-parsed page dicts with ``{"page": int, "text": str}``.
        If not provided, the PDF is opened and parsed.
    progress_callback : callable, optional
        Called with progress message strings.

    Returns
    -------
    TocPageHints
        Page hints derived from the TOC.  The ``hints`` dict maps
        statement types to lists of 1-based PDF page numbers.
    """
    import pdfplumber

    pdf_path = Path(pdf_path)

    def _log(msg: str):
        if progress_callback:
            progress_callback(msg)

    # Parse pages if not provided
    if pages is None:
        pages = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                pages.append({"page": i + 1, "text": text})

    # Step 1: Find TOC pages
    toc_pages = _find_toc_pages(pages)
    if not toc_pages:
        _log("  TOC: No Table of Contents page found")
        return TocPageHints()

    _log(f"  TOC: Found on page(s) {toc_pages}")

    # Step 2: Parse TOC entries
    toc_text = "\n".join(
        next((p["text"] for p in pages if p["page"] == pnum), "")
        for pnum in toc_pages
    )
    entries = _parse_toc_entries(toc_text)
    if not entries:
        _log("  TOC: Regex parsing found no entries — trying LLM fallback")
        entries = _llm_parse_toc_entries(toc_text, progress_callback)
        if not entries:
            _log("  TOC: No entries parsed from TOC page(s)")
            return TocPageHints(toc_pages=toc_pages)
        _log(f"  TOC: LLM parsed {len(entries)} entries")
    else:
        _log(f"  TOC: Parsed {len(entries)} entries")

    # Step 3: Match entries to statement types
    statement_entries = _match_entries_to_statements(entries)
    if not statement_entries:
        _log("  TOC: Regex matching found no financial entries — trying LLM fallback")
        statement_entries = _llm_match_toc_entries(entries, progress_callback)
        if not statement_entries:
            _log("  TOC: No financial statement entries found in TOC")
            return TocPageHints(toc_pages=toc_pages, raw_entries=entries)
        _log(f"  TOC: LLM matched {len(statement_entries)} financial statement entries")

    # Step 4: Detect page offset (printed page number → PDF page index)
    # Compute per-entity offsets because many Indian annual reports
    # use different page numbering for standalone vs consolidated sections.
    page_offsets = _detect_page_offsets(pdf_path, pages, statement_entries)
    if page_offsets:
        offset_summary = ", ".join(
            f"{entity}={offset}" for entity, offset in page_offsets.items()
        )
        _log(f"  TOC: Detected page offsets: {offset_summary}")
    else:
        _log("  TOC: Could not detect page offsets — using search window")

    # Global offset for backward compatibility
    page_offset = None
    if page_offsets:
        # Use the most common offset as the global default
        from collections import Counter
        offset_counts = Counter(page_offsets.values())
        page_offset = offset_counts.most_common(1)[0][0]

    # Step 5: Build page hints
    hints = _build_page_hints(statement_entries, page_offset, len(pages), page_offsets)
    if hints:
        hint_summary = ", ".join(
            f"{k}={v}" for k, v in hints.items()
        )
        _log(f"  TOC: Page hints: {hint_summary}")
    else:
        _log("  TOC: No page hints generated")

    return TocPageHints(
        hints=hints,
        toc_pages=toc_pages,
        page_offset=page_offset,
        page_offsets=page_offsets,
        raw_entries=entries,
    )


# ===================================================================
# Step 1: Find TOC pages
# ===================================================================

def _find_toc_pages(pages: list[dict]) -> list[int]:
    """Find pages that contain a Table of Contents / Index.

    Scans the first ``_MAX_TOC_SCAN_PAGES`` pages for TOC keywords.
    A page is considered a TOC page if:
      1. It contains a TOC keyword in the first few lines, AND
      2a. Has multiple lines with trailing page numbers (dotted or plain), OR
      2b. Contains financial-statement keywords (some TOCs have CID-encoded
          page numbers that pdfplumber can't decode as digits, but the
          section names are still readable).

    Additionally, a second pass detects TOC pages that lack a traditional
    TOC heading but have multiple financial section keywords AND page-number
    patterns — this handles CID-encoded TOC headings and PDFs where the
    TOC is labeled differently (e.g. "INDEX" in a non-standard position).
    """
    toc_pages: list[int] = []

    # Keywords that indicate financial statement sections in a TOC.
    # Includes both entity-specific and entity-agnostic keywords.
    _fin_section_keywords = [
        # Entity-specific
        "standalone financial",
        "consolidated financial",
        "standalone financials",
        "consolidated financials",
        "standalone balance sheet",
        "consolidated balance sheet",
        "standalone profit",
        "consolidated profit",
        "standalone cash flow",
        "consolidated cash flow",
        "standalone statement",
        "consolidated statement",
        # Entity-agnostic (for TOCs that list statement names without
        # "Standalone"/"Consolidated" prefix)
        "balance sheet",
        "profit and loss",
        "profit & loss",
        "cash flow",
        "income statement",
        "statement of profit",
        "statement of cash flow",
        # Other financial section indicators
        "auditor",
        "independent auditor",
        "financial statements",
    ]

    for page in pages[:_MAX_TOC_SCAN_PAGES]:
        text = page.get("text", "")
        if not text.strip():
            continue

        lines = text.splitlines()
        lower = text.lower()

        # Check if any TOC keyword appears in the first 5 lines
        has_toc_heading = False
        for line in lines[:5]:
            line_lower = line.strip().lower()
            if any(kw in line_lower for kw in _TOC_PAGE_KEYWORDS):
                has_toc_heading = True
                break

        if not has_toc_heading:
            continue

        # Verify it looks like a TOC by checking for page-number patterns
        # Count lines that have a page number (before or after description)
        page_num_lines = 0
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Match lines ending with a number (with optional dots/dashes before)
            if re.search(r"[.\s\-…—–]+\s*\d{1,3}\s*$", stripped):
                page_num_lines += 1
            # Also match lines like "Standalone Financials 155"
            elif re.search(r"\s\d{1,3}\s*$", stripped) and len(stripped) > 5:
                page_num_lines += 1
            # Also match lines STARTING with a number like "98 Standalone financial"
            elif re.match(r"^\d{1,3}\s+[a-zA-Z]", stripped):
                page_num_lines += 1
            # Also match lines with CID-encoded numbers like "(cid:56)(cid:56)"
            elif re.search(r"\(cid:\d+\)\s*$", stripped):
                page_num_lines += 1

        # Standard check: enough lines with page numbers
        if page_num_lines >= 3:
            toc_pages.append(page["page"])
            continue

        # Fallback: TOC heading + financial section keywords
        # (handles CID-encoded page numbers that pdfplumber can't decode)
        has_fin_keywords = any(kw in lower for kw in _fin_section_keywords)
        if has_fin_keywords:
            toc_pages.append(page["page"])

    # --- Second pass: detect TOC pages without traditional heading ---
    # Some PDFs have CID-encoded TOC headings, or the TOC is labeled
    # differently.  We look for pages with:
    #   - Multiple financial section keywords (>= 3)
    #   - Page-number patterns (>= 2 lines)
    #   - Not already detected as a TOC page
    #   - Not a financial statement page itself (no section headings
    #     like "ASSETS", "EQUITY AND LIABILITIES", etc.)
    if not toc_pages:
        _stmt_section_keywords = [
            "equity and liabilities", "non-current assets",
            "current assets", "revenue from operations",
            "operating activities", "investing activities",
            "financing activities",
        ]

        for page in pages[:_MAX_TOC_SCAN_PAGES]:
            if page["page"] in toc_pages:
                continue

            text = page.get("text", "")
            if not text.strip():
                continue

            lower = text.lower()

            # Skip pages that look like actual financial statements
            if any(kw in lower for kw in _stmt_section_keywords):
                continue

            # Count financial section keywords
            fin_keyword_count = sum(
                1 for kw in _fin_section_keywords if kw in lower
            )

            # Count page-number patterns
            page_num_lines = 0
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if re.search(r"[.\s\-…—–]+\s*\d{1,3}\s*$", stripped):
                    page_num_lines += 1
                elif re.search(r"\s\d{1,3}\s*$", stripped) and len(stripped) > 5:
                    page_num_lines += 1
                elif re.match(r"^\d{1,3}\s+[a-zA-Z]", stripped):
                    page_num_lines += 1
                elif re.search(r"\(cid:\d+\)\s*$", stripped):
                    page_num_lines += 1

            # Also check for CID-heavy pages (many CID tokens)
            cid_count = len(re.findall(r"\(cid:\d+\)", text))

            # Accept if: multiple financial keywords + page-number patterns
            # OR: financial keywords + heavy CID encoding (TOC with CID numbers)
            if fin_keyword_count >= 3 and page_num_lines >= 2:
                toc_pages.append(page["page"])
            elif fin_keyword_count >= 2 and cid_count >= 10:
                toc_pages.append(page["page"])

    return toc_pages


# ===================================================================
# Step 2: Parse TOC entries
# ===================================================================

def _parse_toc_entries(toc_text: str) -> list[TocEntry]:
    """Parse TOC text into structured entries.

    Handles multiple formats:
      - "Balance Sheet ........... 180"
      - "Standalone Financials 155"
      - "STANDALONE FINANCIALS 11 5"  (split number in columns)
      - "98 Standalone financial statements"  (number before description)
      - CID-encoded page numbers (custom font encoding)
      - Two-column TOC lines (pdfplumber merges left+right columns)

    Also handles multi-line entries where pdfplumber splits a long
    entry across two lines, e.g.::
        "98 Standalone financial"
        "statements"
    These are merged before parsing.
    """
    entries: list[TocEntry] = []
    lines = toc_text.splitlines()

    # Check if any lines contain CID tokens — if so, detect the base
    # first so all lines use a consistent decoding.
    cid_base: int | None = None
    has_cid = any("(cid:" in line for line in lines)
    if has_cid:
        cid_base = _detect_cid_base(lines)
        if cid_base is not None:
            _log_cid_base = cid_base  # for debugging

    # Pre-process 1: Split two-column TOC lines.
    # pdfplumber merges two-column TOC layouts into single lines where
    # the left column entry and right column entry are concatenated.
    # E.g. "Management Team...05 Consolidated Balance Sheet...180"
    # should be split into:
    #   "Management Team...05"
    #   "Consolidated Balance Sheet...180"
    #
    # Detection: a line that contains TWO "dots/dashes + page_number"
    # patterns.  The split point is after the first page number, before
    # the start of the right column description (uppercase letter).
    split_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            split_lines.append(stripped)
            continue

        # Count "dots/dashes + number" patterns in this line
        dot_num_matches = list(re.finditer(r'[.\-…—–]+\s*\d{1,3}', stripped))
        if len(dot_num_matches) >= 2:
            # This is likely a two-column line — try to split.
            # The split point is after the first "dots + number" pattern,
            # at the start of the right column description.
            first_end = dot_num_matches[0].end()
            rest = stripped[first_end:]

            # The right column starts with whitespace + uppercase letter
            right_start = re.match(r'\s+([A-Z])', rest)
            if right_start:
                left_part = stripped[:first_end].strip()
                right_part = rest[right_start.start() + 1:].strip()

                # Verify right part also has a "dots + number" pattern
                # (to avoid splitting single entries that happen to have
                # a number in the middle)
                if right_part and re.search(r'[.\-…—–]+\s*\d{1,3}', right_part):
                    split_lines.append(left_part)
                    split_lines.append(right_part)
                    continue

        split_lines.append(stripped)

    # Pre-process 2: Merge multi-line TOC entries.
    # pdfplumber often splits long entries across lines when the text
    # wraps in a narrow column.  We detect continuation lines (short
    # lines with only alphabetic text, no page numbers) and merge them
    # with the previous line.
    #
    # Fix 37: Also handle CID-only continuation lines.  Some PDFs
    # (e.g. Brightcom 2017-18) have the section name on one line and
    # the CID-encoded page number on the next line:
    #   "STANDALONE FINANCIAL STATEMENTS"
    #   "(cid:56)(cid:53)"
    # These CID-only lines should be merged with the previous line
    # so that _parse_toc_line() can decode the page number.
    merged_lines: list[str] = []
    for line in split_lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Fix 37: Check if this line is ONLY CID tokens (no alphabetic
        # text outside the CID syntax).  If so, merge with the previous
        # line — it's a page number that was split onto a separate line.
        # NOTE: We must strip CID tokens before checking for alphabetic
        # characters, because "(cid:56)(cid:53)" contains 'c','i','d'
        # as part of the CID syntax, not as meaningful text.
        _without_cid = re.sub(r"\(cid:\d+\)", "", stripped).strip()
        _is_cid_only = (
            re.search(r"\(cid:\d+\)", stripped)
            and not re.search(r"[a-zA-Z]", _without_cid)
            and merged_lines
        )
        if _is_cid_only:
            # Merge CID-only line with previous line
            merged_lines[-1] = merged_lines[-1] + " " + stripped
            continue

        # A continuation line is:
        #   - Short (<= 60 chars)
        #   - Contains only alphabetic text (no digits, no dots/dashes)
        #   - Not a standalone TOC entry itself
        #   - Not an ALL CAPS section header (like "FORWARD LOOKING STATEMENT")
        _alpha_chars = [c for c in stripped if c.isalpha()]
        _upper_ratio = sum(1 for c in _alpha_chars if c.isupper()) / max(len(_alpha_chars), 1)
        is_continuation = (
            len(stripped) <= 60
            and not re.search(r"\d", stripped)
            and not re.search(r"[.\-…—–]{3,}", stripped)
            and not re.search(r"\(cid:\d+\)", stripped)
            and re.search(r"[a-zA-Z]", stripped)
            and _upper_ratio < 0.8  # not ALL CAPS
            and merged_lines  # there's a previous line to merge with
        )

        # FIX: Don't merge if the previous line already ends with a
        # page number pattern — it's a complete entry, and the current
        # line is a new entry (or section header), not a continuation.
        # This prevents corruption like:
        #   "Cash Flows...184" + "Notes forming part of the Consolidated"
        #   → "Cash Flows...184 Notes forming part of the Consolidated"
        # which can't be parsed because it doesn't end with a number.
        if is_continuation and merged_lines:
            prev_line = merged_lines[-1]
            if re.search(r'\d{1,3}\s*$', prev_line):
                is_continuation = False

        if is_continuation:
            # Merge with previous line
            merged_lines[-1] = merged_lines[-1] + " " + stripped
        else:
            merged_lines.append(stripped)

    for line in merged_lines:
        if not line or len(line) < 5:
            continue

        entry = _parse_toc_line(line, cid_base=cid_base)
        if entry:
            entries.append(entry)

    return entries


def _parse_toc_line(line: str, cid_base: int | None = None) -> TocEntry | None:
    """Parse a single TOC line into a TocEntry.

    Returns None if the line doesn't look like a TOC entry.
    """
    # Pattern 0: CID-encoded page numbers
    # Some PDFs use custom font encoding where digits appear as (cid:NN).
    # E.g. "(cid:56)(cid:56) STANDALONE FINANCIAL STATEMENTS"
    # or "STANDALONE FINANCIAL STATEMENTS (cid:56)(cid:56)"
    if "(cid:" in line:
        cid_page = _try_parse_cid_line(line, cid_base=cid_base)
        if cid_page is not None:
            return cid_page

    # Pattern 1: Dotted leaders with page number
    # "Consolidated Balance Sheet………………........ 180"
    m = re.match(
        r"^(.+?)\s*[.\-…—–]+\s*(\d{1,3})\s*$",
        line,
    )
    if m:
        desc = m.group(1).strip()
        page_num = int(m.group(2))
        if _is_valid_toc_description(desc):
            return TocEntry(description=desc, page_number=page_num, raw_line=line)

    # Pattern 2: Description followed by page number(s)
    # "Standalone Financials 155"
    # "STANDALONE FINANCIALS 11 5"  (split: 11 and 5 → 115)
    m = re.match(
        r"^(.+?)\s+(\d{1,3})\s+(\d{1,2})\s*$",
        line,
    )
    if m:
        desc = m.group(1).strip()
        part1 = m.group(2)
        part2 = m.group(3)
        # Try combining the two number parts (e.g., "11 5" → 115)
        combined = int(part1 + part2)
        # Also try treating them as separate (part1=page, part2=something else)
        separate = int(part1)
        if _is_valid_toc_description(desc):
            # Heuristic: if combined is a plausible page number (> 20)
            # and separate is also plausible, prefer combined if it's larger
            # (more likely to be a page number in a 200+ page report)
            if combined > 20:
                return TocEntry(description=desc, page_number=combined, raw_line=line)
            elif separate > 20:
                return TocEntry(description=desc, page_number=separate, raw_line=line)

    # Pattern 3: Simple "Description N" at end of line
    m = re.match(
        r"^(.+?)\s+(\d{1,3})\s*$",
        line,
    )
    if m:
        desc = m.group(1).strip()
        page_num = int(m.group(2))
        # Only accept if the description has alphabetic content
        # and the page number is plausible (> 1)
        if _is_valid_toc_description(desc) and page_num > 1:
            return TocEntry(description=desc, page_number=page_num, raw_line=line)

    # Pattern 4: "NUMBER DESCRIPTION" — page number before description
    # Common in some Indian annual reports where the INDEX format is:
    #   "03 Corporate Information"
    #   "98 Standalone financial statements"
    #   "149 Consolidated financial statements"
    m = re.match(
        r"^(\d{1,3})\s+(.+)$",
        line,
    )
    if m:
        page_num = int(m.group(1))
        desc = m.group(2).strip()
        # Only accept if the description is valid and page number is plausible
        if _is_valid_toc_description(desc) and page_num > 1:
            return TocEntry(description=desc, page_number=page_num, raw_line=line)

    return None


def _detect_cid_base(lines: list[str]) -> int | None:
    """Detect the CID base value for digit decoding.

    Only considers CID sequences from lines that have readable text
    (after removing CID tokens), to avoid pollution from lines where
    CID tokens encode letters rather than digits.

    Strategy:
      1. Find lines with readable text + adjacent CID token sequences
      2. Collect CID values only from those number-like sequences
      3. Try base values and pick the one that produces the most
         plausible page numbers

    Returns the detected base, or None if no consistent base found.
    """
    # Step 1: Find CID sequences from lines with readable descriptions
    candidate_sequences: list[list[int]] = []

    for line in lines:
        # Remove CID tokens to check if there's readable text
        clean = re.sub(r"\(cid:\d+\)", "", line).strip()
        if not _is_valid_toc_description(clean):
            continue

        # Extract consecutive CID token sequences from this line
        current_seq: list[int] = []
        last_cid_end = -1

        for m in re.finditer(r"\(cid:(\d+)\)", line):
            cid_val = int(m.group(1))
            if current_seq and m.start() <= last_cid_end + 3:
                current_seq.append(cid_val)
            else:
                if len(current_seq) >= 2:
                    candidate_sequences.append(current_seq)
                current_seq = [cid_val]
            last_cid_end = m.end()

        if current_seq and len(current_seq) >= 2:
            candidate_sequences.append(current_seq)

    if not candidate_sequences:
        return None

    # Step 2: Collect all CID values from candidate sequences
    number_cid_values: list[int] = []
    for seq in candidate_sequences:
        number_cid_values.extend(seq)

    if not number_cid_values:
        return None

    min_cid = min(number_cid_values)

    # Step 3: Try base values (min_cid is likely digit 0, 1, or 2)
    best_base: int | None = None
    best_score: int = 0

    for digit_for_min in range(4):  # min_cid = digit 0, 1, 2, or 3
        base = min_cid - digit_for_min
        if base < 0:
            continue

        # Count how many sequences decode to plausible page numbers
        valid_seqs = 0
        for seq in candidate_sequences:
            digits = []
            valid = True
            for cid_val in seq:
                digit = cid_val - base
                if 0 <= digit <= 9:
                    digits.append(digit)
                else:
                    valid = False
                    break
            if valid and digits:
                page_num = 0
                for d in digits:
                    page_num = page_num * 10 + d
                if 2 <= page_num <= 500:
                    valid_seqs += 1

        if valid_seqs > best_score:
            best_score = valid_seqs
            best_base = base

    # Only return a base if it decodes most sequences successfully
    if best_base is not None and best_score >= len(candidate_sequences) * 0.5:
        return best_base

    return None


def _try_parse_cid_line(line: str, cid_base: int | None = None) -> TocEntry | None:
    """Try to parse a TOC line with CID-encoded page numbers.

    Some PDFs use custom font encodings where digits appear as
    ``(cid:NN)`` tokens.  For example::

        (cid:56)(cid:56) STANDALONE FINANCIAL STATEMENTS
        STANDALONE FINANCIAL STATEMENTS (cid:56)(cid:56)

    The CID-to-digit mapping is font-specific.  If ``cid_base`` is
    provided, it is used directly (digit = cid_value - base).
    Otherwise, common base values are tried.

    Returns a TocEntry if a CID-encoded page number is found, else None.
    """
    # Check if line contains CID tokens
    if "(cid:" not in line:
        return None

    # Extract the description part (text without CID tokens)
    # Remove CID tokens to get the clean description
    clean = re.sub(r"\(cid:\d+\)", "", line).strip()
    if not _is_valid_toc_description(clean):
        return None

    # Extract all consecutive CID token sequences from the line.
    # A page number is a consecutive run of (cid:NN) tokens.
    cid_sequences: list[list[int]] = []
    current_seq: list[int] = []
    last_cid_end = -1

    for m in re.finditer(r"\(cid:(\d+)\)", line):
        cid_val = int(m.group(1))
        # Check if this token is adjacent to the previous one
        # (allowing only whitespace between)
        if current_seq and m.start() <= last_cid_end + 3:
            current_seq.append(cid_val)
        else:
            if len(current_seq) >= 2:
                cid_sequences.append(current_seq)
            current_seq = [cid_val]
        last_cid_end = m.end()

    if current_seq and len(current_seq) >= 2:
        cid_sequences.append(current_seq)

    if not cid_sequences:
        return None

    # Decode CID sequences using the provided base or try common bases
    bases_to_try = [cid_base] if cid_base is not None else range(40, 70)

    for base in bases_to_try:
        for cid_seq in cid_sequences:
            digits = []
            valid = True
            for cid_val in cid_seq:
                digit = cid_val - base
                if 0 <= digit <= 9:
                    digits.append(digit)
                else:
                    valid = False
                    break
            if valid and digits:
                page_num = 0
                for d in digits:
                    page_num = page_num * 10 + d
                if 2 <= page_num <= 500:
                    return TocEntry(
                        description=clean,
                        page_number=page_num,
                        raw_line=line,
                    )

    return None


def _is_valid_toc_description(desc: str) -> bool:
    """Check if a TOC description is valid (has meaningful text)."""
    if not desc or len(desc) < 4:
        return False
    # Must contain at least one alphabetic character
    if not re.search(r"[a-zA-Z]", desc):
        return False
    # Should not be just a number
    if re.fullmatch(r"\d+", desc.strip()):
        return False
    # Should not be a common non-TOC line (page header, etc.)
    lower = desc.lower().strip()
    skip_phrases = [
        "integrated annual report",
        "annual report",
        "page",
    ]
    if any(lower == p for p in skip_phrases):
        return False
    return True


# ===================================================================
# Step 3: Match entries to statement types
# ===================================================================

def _match_entries_to_statements(
    entries: list[TocEntry],
) -> list[tuple[TocEntry, list[str]]]:
    """Match TOC entries to internal statement types.

    For entity-agnostic patterns (e.g. "Balance Sheet" without
    "Standalone"/"Consolidated" prefix), the entity context is
    resolved using section boundaries from nearby section-level
    entries (e.g. "Standalone Financials" or "Consolidated Financials").

    Returns a list of (entry, [statement_types]) tuples.
    """
    matched: list[tuple[TocEntry, list[str]]] = []

    for entry in entries:
        desc = entry.description
        for pattern, stypes in _TOC_STATEMENT_PATTERNS:
            if pattern.search(desc):
                matched.append((entry, stypes))
                break

    # Resolve entity context for ambiguous entries (entries that map
    # to both standalone and consolidated variants due to entity-
    # agnostic patterns like "Balance Sheet" without entity prefix).
    _resolve_entity_context(matched, entries)

    return matched


def _resolve_entity_context(
    matched: list[tuple[TocEntry, list[str]]],
    all_entries: list[TocEntry],
) -> None:
    """Resolve entity context for ambiguous TOC entries in-place.

    When an entry matches an entity-agnostic pattern (e.g. "Balance Sheet"
    maps to both standalone_balance_sheet and consolidated_balance_sheet),
    this function determines the correct entity based on section boundaries.

    Section boundaries are defined by section-level entries like
    "Standalone Financials" or "Consolidated Financials".  Entries
    between two section boundaries belong to the section defined by
    the earlier boundary.

    For example, given:
        "Standalone Financials" → page 155
        "Balance Sheet" → page 160
        "Consolidated Financials" → page 243
        "Balance Sheet" → page 250

    The first "Balance Sheet" (page 160) is resolved to standalone
    (nearest section boundary before page 160 is "Standalone Financials"
    at page 155).  The second "Balance Sheet" (page 250) is resolved
    to consolidated (nearest boundary before page 250 is "Consolidated
    Financials" at page 243).
    """
    # Find section-level entries that define entity boundaries.
    # A section boundary is an entry that maps to 3+ types of the
    # SAME entity (e.g. all 3 standalone types or all 3 consolidated).
    section_boundaries: list[tuple[int, str]] = []  # (page_number, entity)

    for entry, stypes in matched:
        if len(stypes) >= 3:
            has_standalone = all("standalone" in s for s in stypes)
            has_consolidated = all("consolidated" in s for s in stypes)
            if has_standalone:
                section_boundaries.append((entry.page_number, "standalone"))
            elif has_consolidated:
                section_boundaries.append((entry.page_number, "consolidated"))
            # If types include both entities (shouldn't happen after
            # removing the broad "Financial Statements" pattern), skip

    # Also scan all_entries for section headers that weren't matched
    # but contain entity keywords.  This catches section headers that
    # appear in two-column TOC lines where pdfplumber merges them with
    # left-column entries, causing them to not be parsed as separate
    # TocEntry objects.  We look for entity keywords in the raw
    # description text of ALL entries (including non-matched ones).
    matched_descs = {e.description for e, _ in matched}
    for entry in all_entries:
        if entry.description in matched_descs:
            continue
        desc_lower = entry.description.lower()
        if re.search(r"\bstandalone\s+financial", desc_lower):
            section_boundaries.append((entry.page_number, "standalone"))
        elif re.search(r"\bconsolidated\s+financial", desc_lower):
            section_boundaries.append((entry.page_number, "consolidated"))

    if not section_boundaries:
        return  # No section boundaries to resolve against

    # Sort by page number
    section_boundaries.sort(key=lambda x: x[0])

    # Remove duplicate boundaries (same page, same entity)
    seen: set[tuple[int, str]] = set()
    unique_boundaries: list[tuple[int, str]] = []
    for bound in section_boundaries:
        if bound not in seen:
            seen.add(bound)
            unique_boundaries.append(bound)
    section_boundaries = unique_boundaries

    # Resolve ambiguous entries
    for i, (entry, stypes) in enumerate(matched):
        # Check if this entry is ambiguous (maps to both entities)
        has_standalone = any("standalone" in s for s in stypes)
        has_consolidated = any("consolidated" in s for s in stypes)
        if not (has_standalone and has_consolidated):
            continue  # Not ambiguous — skip

        # Find the nearest section boundary before this entry's page
        entry_page = entry.page_number
        resolved_entity: str | None = None
        for bound_page, entity in reversed(section_boundaries):
            if bound_page <= entry_page:
                resolved_entity = entity
                break

        if resolved_entity is None:
            # Entry is before any section boundary.
            # Default to the first section's entity (usually standalone
            # in Indian annual reports).
            if section_boundaries:
                resolved_entity = section_boundaries[0][1]
            else:
                continue  # Can't resolve

        # Replace ambiguous types with resolved entity types
        resolved_stypes: list[str] = []
        for stype in stypes:
            base = stype.replace("standalone_", "").replace("consolidated_", "")
            resolved = f"{resolved_entity}_{base}"
            if resolved not in resolved_stypes:
                resolved_stypes.append(resolved)

        matched[i] = (entry, resolved_stypes)


# ===================================================================
# Step 4: Detect page offset
# ===================================================================

def _detect_page_offsets(
    pdf_path: Path,
    pages: list[dict],
    statement_entries: list[tuple[TocEntry, list[str]]],
) -> dict[str, int]:
    """Detect per-entity page offsets between printed page numbers and PDF page indices.

    The offset is defined as: pdf_page_index = printed_page_number + offset

    Many Indian annual reports use different page numbering for standalone
    vs consolidated sections (e.g. standalone pages are numbered starting
    from a different offset than consolidated pages).  This function
    detects the offset separately for each entity.

    Returns
    -------
    dict[str, int]
        Mapping of entity ("standalone" or "consolidated") to offset.
        May be empty if no offset could be detected.
    """
    page_text_map = {p["page"]: p.get("text", "") for p in pages}
    total_pages = len(pages)

    # Group entries by entity
    entity_entries: dict[str, list[tuple[TocEntry, list[str]]]] = {
        "standalone": [],
        "consolidated": [],
    }

    for entry, stypes in statement_entries:
        # Determine entity from the statement types.
        # After entity resolution, entries should have a clear entity.
        # If still ambiguous (both entities present), add to BOTH groups
        # so offset detection can evaluate each independently.
        has_standalone = any("standalone" in s for s in stypes)
        has_consolidated = any("consolidated" in s for s in stypes)
        if has_standalone and has_consolidated:
            # Ambiguous — add to both groups
            entity_entries["standalone"].append((entry, stypes))
            entity_entries["consolidated"].append((entry, stypes))
        elif has_standalone:
            entity_entries["standalone"].append((entry, stypes))
        else:
            entity_entries["consolidated"].append((entry, stypes))

    entity_offsets: dict[str, int] = {}

    for entity, entries in entity_entries.items():
        if not entries:
            continue

        # offset → (vote_count, total_keyword_hits)
        # We track both the number of entries that matched and the
        # total keyword quality, so we can pick the best offset.
        offset_scores: dict[int, tuple[int, int]] = {}

        # Prefer specific entries for offset detection
        specific = [(e, s) for e, s in entries if len(s) == 1]
        check_entries = specific if specific else entries

        for entry, stypes in check_entries[:6]:  # limit checks
            printed_page = entry.page_number

            # Keywords to look for at the target page
            check_keywords = _get_verification_keywords(stypes)

            # Evaluate ALL offsets and record the best match for this entry
            best_offset_for_entry: int | None = None
            best_hits_for_entry: int = 0

            for offset in range(-20, 21):
                pdf_page_1based = printed_page + offset
                if pdf_page_1based < 1 or pdf_page_1based > total_pages:
                    continue

                page_text = page_text_map.get(pdf_page_1based, "")
                if not page_text.strip():
                    continue

                page_lower = page_text.lower()

                # Check if the page contains relevant keywords
                keyword_hits = sum(
                    1 for kw in check_keywords if kw in page_lower
                )

                # Fix 21: Penalize auditor's report pages.  These pages
                # often mention financial keywords ("balance sheet",
                # "consolidated", "profit") in their narrative, causing
                # false-positive offset matches.  We detect auditor's
                # report pages by checking for characteristic phrases
                # and reduce the effective keyword score.
                _auditor_report_phrases = [
                    "independent auditor",
                    "auditor's report",
                    "auditors' report",
                    "report on the audit",
                    "opinion on the financial",
                    "basis for opinion",
                    "key audit matters",
                    "we have audited",
                ]
                _is_auditor_report = any(p in page_lower for p in _auditor_report_phrases)
                if _is_auditor_report:
                    keyword_hits = max(0, keyword_hits - 3)

                # Fix 21: Bonus for pages with actual table structure
                # (amounts with commas, "particulars", "note no.").
                # These are much more likely to be actual financial
                # statement pages than prose pages that merely mention
                # financial terms.
                _table_structure_phrases = [
                    "particulars",
                    "note no",
                    "as at",
                    "as on",
                    "for the year ended",
                    "for the period ended",
                ]
                _table_structure_count = sum(1 for p in _table_structure_phrases if p in page_lower)
                if _table_structure_count >= 2:
                    keyword_hits += 2

                # Require at least 3 keyword hits (was 2) to avoid
                # false positives from auditor's reports and other
                # prose pages that mention financial terms.
                if keyword_hits >= 3 and keyword_hits > best_hits_for_entry:
                    best_hits_for_entry = keyword_hits
                    best_offset_for_entry = offset

            if best_offset_for_entry is not None:
                votes, hits = offset_scores.get(best_offset_for_entry, (0, 0))
                offset_scores[best_offset_for_entry] = (votes + 1, hits + best_hits_for_entry)

        if offset_scores:
            # Pick the offset with the most votes; break ties by keyword
            # quality, then by proximity to 0 (prefer smaller |offset|)
            best_offset = max(
                offset_scores,
                key=lambda o: (
                    offset_scores[o][0],      # vote count
                    offset_scores[o][1],      # keyword hits
                    -abs(o),                  # prefer closer to 0
                ),
            )
            entity_offsets[entity] = best_offset

    return entity_offsets


def _get_verification_keywords(stypes: list[str]) -> list[str]:
    """Get keywords to verify a page matches a statement type.

    Uses specific financial-statement terminology that is unlikely to
    appear in prose text (directors' report, auditor's report, etc.).
    Generic terms like "assets", "profit", "expenses" are avoided because
    they appear frequently in non-statement pages.
    """
    keywords: list[str] = []

    for stype in stypes:
        if "balance_sheet" in stype:
            # "equity and liabilities" is very specific to BS pages
            keywords.extend([
                "balance sheet", "equity and liabilities",
                "non-current assets", "current assets",
                "non-current liabilities", "current liabilities",
                "total equity", "as at", "as on",
            ])
        if "profit_and_loss" in stype:
            # "revenue from operations" is very specific to P&L pages
            keywords.extend([
                "profit and loss", "statement of profit",
                "revenue from operations", "other income",
                "earnings per share", "other comprehensive income",
                "for the year ended", "for the period ended",
            ])
        if "cash_flow" in stype:
            # "operating activities" is very specific to CF pages
            keywords.extend([
                "cash flow", "operating activities",
                "investing activities", "financing activities",
                "cash and cash equivalents", "net cash",
                "for the year ended", "for the period ended",
            ])
        if "standalone" in stype:
            keywords.append("standalone")
        if "consolidated" in stype:
            keywords.append("consolidated")

    return keywords


# Search window for section-level TOC entries (e.g. "Standalone Financials 155")
# These point to the start of a section, not a specific statement,
# so we need a wider window to find the actual statement within.
# Some annual reports have long auditor's reports (10+ pages) between
# the section start and the first financial statement.
_SECTION_SEARCH_WINDOW = 18

# Window around specific TOC entries when offset is known.
# Must be generous because the global offset may be wrong for some
# sections — many Indian annual reports use different page numbering
# for standalone vs consolidated sections, so a single detected offset
# can be off by 5+ pages for one of the entities.
_SPECIFIC_OFFSET_TOLERANCE = 3


# ===================================================================
# Step 5: Build page hints
# ===================================================================

def _build_page_hints(
    statement_entries: list[tuple[TocEntry, list[str]]],
    page_offset: int | None,
    total_pages: int,
    page_offsets: dict[str, int] | None = None,
) -> dict[str, list[int]]:
    """Build page hints from matched TOC entries.

    For each statement type, the hint is a list of 1-based PDF page
    numbers where the statement is likely to be found.

    Two kinds of entries are handled differently:

    **Specific entries** (e.g. "Standalone Balance Sheet … 180"):
      - With known per-entity offset: page ± ``_SPECIFIC_OFFSET_TOLERANCE``
      - With global offset: page ± ``_SPECIFIC_OFFSET_TOLERANCE``
      - Without offset: ``_PAGE_SEARCH_WINDOW`` around printed page

    **Section-level entries** (e.g. "Standalone Financials 155"):
      - These point to the *start* of a financial section (usually the
        auditor's report), not the specific statement.  We generate a
        forward search window of ``_SECTION_SEARCH_WINDOW`` pages.
      - Balance Sheet is typically first (section_start + 0..2),
        P&L follows (section_start + 2..5), Cash Flow last
        (section_start + 4..8).
      - We assign staggered windows so each statement type gets a
        prioritized range within the section.
    """
    if page_offsets is None:
        page_offsets = {}

    hints: dict[str, list[int]] = {}

    for entry, stypes in statement_entries:
        printed_page = entry.page_number
        is_section_level = len(stypes) > 1

        # Process each statement type independently, using the
        # per-entity offset for that specific type.  This handles
        # entity-agnostic entries correctly — e.g. "Balance Sheet"
        # mapped to both standalone_balance_sheet and
        # consolidated_balance_sheet after entity resolution, where
        # each entity may have a different page offset.
        for stype in stypes:
            # Determine entity for this specific stype
            entity = "standalone" if "standalone" in stype else "consolidated"
            effective_offset = page_offsets.get(entity, page_offset)

            if is_section_level:
                # Section-level entry: generate a forward search window
                if effective_offset is not None:
                    section_start = printed_page + effective_offset
                else:
                    section_start = printed_page

                section_start = max(1, min(section_start, total_pages))

                # Fix 20: Generate overlapping windows for each statement type
                # within the section.  The order is always:
                #   Balance Sheet → Profit & Loss → Cash Flow
                #
                # Previously we used staggered windows (BS starts at
                # section_start, P&L at section_start+2, CF at
                # section_start+4).  But this fails when statements are on
                # consecutive pages (e.g. BS on p130, P&L on p130, CF on
                # p132 with section_start=130 — the P&L window started at
                # 131, missing p130).
                #
                # Now ALL statement types get the same window starting from
                # section_start - 1 (to catch the case where the first
                # statement is on the section_start page itself).  The
                # _find_statement_in_window() function uses heading detection
                # to find the right page within the window, and Fix 18
                # prevents the same page from being used for both entities.
                window_size = _SECTION_SEARCH_WINDOW
                start = max(1, section_start - 1)
                end = min(total_pages, section_start + window_size - 1)
                pages_list = list(range(start, end + 1))

                if stype not in hints:
                    hints[stype] = pages_list
                else:
                    # Merge with existing, keeping the narrower range
                    existing = set(hints[stype])
                    existing.update(pages_list)
                    hints[stype] = sorted(existing)

            else:
                # Specific entry: precise or small window
                if effective_offset is not None:
                    pdf_page = printed_page + effective_offset
                    pdf_page = max(1, min(pdf_page, total_pages))
                    # Small tolerance window around the detected page
                    start = max(1, pdf_page - _SPECIFIC_OFFSET_TOLERANCE)
                    end = min(total_pages, pdf_page + _SPECIFIC_OFFSET_TOLERANCE)
                    pages_list = list(range(start, end + 1))
                else:
                    # Fallback: provide a search window around the printed page
                    start = max(1, printed_page - _PAGE_SEARCH_WINDOW)
                    end = min(total_pages, printed_page + _PAGE_SEARCH_WINDOW)
                    pages_list = list(range(start, end + 1))

                if stype not in hints:
                    hints[stype] = pages_list
                else:
                    # Merge: prefer specific (narrower) over section-level (wider)
                    if len(pages_list) <= len(hints[stype]):
                        # New hint is narrower or same — replace
                        hints[stype] = pages_list
                    # If existing is narrower, keep it (don't widen)

    return hints


# ===================================================================
# LLM fallback functions
# ===================================================================

def _get_llm_client(temperature: float = 0.0, max_tokens: int = 2048):
    """Get the on-prem LLM client (LangChain ChatOpenAI).

    Returns None if the LLM is not available.
    """
    try:
        from .llm_config import get_llm
        return get_llm(temperature=temperature, max_tokens=max_tokens)
    except Exception as exc:
        logger.warning(f"LLM client not available: {exc}")
        return None


def _call_llm(prompt: str, max_tokens: int = 2048, temperature: float = 0.0) -> str | None:
    """Call the LLM with retry logic. Returns response text or None."""
    try:
        from .llm_utils import llm_call_with_retry
        llm = _get_llm_client(temperature=temperature, max_tokens=max_tokens)
        if llm is None:
            return None
        return llm_call_with_retry(llm, prompt, max_retries=2, retry_delay=3.0)
    except Exception as exc:
        logger.warning(f"LLM call failed: {exc}")
        return None


def _extract_json_from_llm(response_text: str) -> dict | list | None:
    """Extract JSON from LLM response."""
    if not response_text:
        return None
    try:
        from .llm_utils import extract_json_from_response
        return extract_json_from_response(response_text)
    except ImportError:
        pass
    # Fallback: basic JSON extraction
    import json
    text = response_text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    return None


_TOC_PARSE_PROMPT = """You are a document parsing specialist. Extract the Table of Contents entries from the following text of an Indian annual report's Table of Contents / Index page.

The text was extracted by pdfplumber and may have formatting issues:
- Page numbers may appear after dots, dashes, or spaces
- Some page numbers may be CID-encoded like (cid:56)(cid:56) — ignore those lines
- Two-column layouts may interleave entries
- Some entries may be section headers (e.g. "Standalone Financial Statements") while others are specific (e.g. "Balance Sheet")

Raw TOC text:
{toc_text}

Extract ALL entries that have both a description and a page number. Return as JSON:
```json
{{
  "entries": [
    {{
      "description": "<the section/statement name>",
      "page_number": <printed page number as integer>
    }}
  ]
}}
```

Rules:
- Only include entries that have a readable page number (ignore CID-encoded ones)
- Keep the description exactly as it appears (preserve "Standalone"/"Consolidated" prefixes)
- Page numbers are the printed page numbers from the TOC, NOT PDF page indices
- Include ALL entries, not just financial statement ones
- If you cannot confidently parse any entries, return an empty list
"""


def _llm_parse_toc_entries(
    toc_text: str,
    progress_callback=None,
) -> list[TocEntry]:
    """Use LLM to parse TOC entries when regex parsing fails.

    This is a fallback for unusual TOC formats that the regex parser
    can't handle (e.g. two-column layouts, unusual separators, etc.).

    Parameters
    ----------
    toc_text : str
        Raw text from the TOC page(s).
    progress_callback : callable, optional
        Called with progress message strings.

    Returns
    -------
    list[TocEntry]
        Parsed entries. Empty list if LLM is unavailable or fails.
    """
    if progress_callback:
        progress_callback("  TOC: Calling LLM for entry parsing...")

    # Truncate very long TOC text to avoid exceeding context window
    truncated = toc_text[:3000] if len(toc_text) > 3000 else toc_text

    prompt = _TOC_PARSE_PROMPT.format(toc_text=truncated)
    response = _call_llm(prompt, max_tokens=1500, temperature=0.0)

    if not response:
        if progress_callback:
            progress_callback("  TOC: LLM returned no response")
        return []

    parsed = _extract_json_from_llm(response)
    if not parsed:
        if progress_callback:
            progress_callback("  TOC: LLM response could not be parsed as JSON")
        return []

    # Handle both {"entries": [...]} and direct list formats
    if isinstance(parsed, dict):
        raw_entries = parsed.get("entries", [])
    elif isinstance(parsed, list):
        raw_entries = parsed
    else:
        return []

    entries: list[TocEntry] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        desc = str(item.get("description", "")).strip()
        page_num = item.get("page_number")
        if not desc or page_num is None:
            continue
        try:
            page_num = int(page_num)
        except (ValueError, TypeError):
            continue
        if page_num < 1 or page_num > 999:
            continue
        if not _is_valid_toc_description(desc):
            continue
        entries.append(TocEntry(
            description=desc,
            page_number=page_num,
            raw_line=f"[LLM] {desc} {page_num}",
        ))

    return entries


_TOC_MATCH_PROMPT = """You are a financial document specialist. Given the following Table of Contents entries from an Indian annual report, identify which ones refer to financial statements and classify them.

The six financial statement types we need are:
1. standalone_balance_sheet — Standalone Balance Sheet / Statement of Financial Position
2. standalone_profit_and_loss — Standalone Statement of Profit and Loss / Income Statement
3. standalone_cash_flow — Standalone Cash Flow Statement
4. consolidated_balance_sheet — Consolidated Balance Sheet / Statement of Financial Position
5. consolidated_profit_and_loss — Consolidated Statement of Profit and Loss / Income Statement
6. consolidated_cash_flow — Consolidated Cash Flow Statement

TOC entries:
{entries_text}

For each entry that refers to a financial statement, classify it. Return as JSON:
```json
{{
  "matches": [
    {{
      "entry_index": <0-based index of the entry>,
      "statement_types": ["<one or more of the 6 types above>"]
    }}
  ]
}}
```

Rules:
- An entry like "Standalone Financial Statements" or "Standalone Financials" maps to ALL 3 standalone types
- An entry like "Consolidated Financial Statements" maps to ALL 3 consolidated types
- An entry like "Balance Sheet" without entity prefix → map to both standalone_balance_sheet and consolidated_balance_sheet
- An entry like "Standalone Balance Sheet" → just standalone_balance_sheet
- Only include entries that clearly refer to financial statements
- If no entries match, return an empty matches list
"""


def _llm_match_toc_entries(
    entries: list[TocEntry],
    progress_callback=None,
) -> list[tuple[TocEntry, list[str]]]:
    """Use LLM to match TOC entries to statement types when regex matching fails.

    This is a fallback when the regex patterns don't cover the specific
    wording used in a company's TOC (e.g. "Statement of Standalone
    Financial Position" instead of "Standalone Balance Sheet").

    Parameters
    ----------
    entries : list[TocEntry]
        All parsed TOC entries.
    progress_callback : callable, optional
        Called with progress message strings.

    Returns
    -------
    list[tuple[TocEntry, list[str]]]
        Matched (entry, [statement_types]) tuples.
    """
    if progress_callback:
        progress_callback("  TOC: Calling LLM for entry matching...")

    # Format entries for the prompt
    entries_text = "\n".join(
        f"  [{i}] {e.description} (page {e.page_number})"
        for i, e in enumerate(entries)
    )

    prompt = _TOC_MATCH_PROMPT.format(entries_text=entries_text)
    response = _call_llm(prompt, max_tokens=1000, temperature=0.0)

    if not response:
        if progress_callback:
            progress_callback("  TOC: LLM returned no response for matching")
        return []

    parsed = _extract_json_from_llm(response)
    if not parsed:
        if progress_callback:
            progress_callback("  TOC: LLM matching response could not be parsed")
        return []

    if isinstance(parsed, dict):
        raw_matches = parsed.get("matches", [])
    elif isinstance(parsed, list):
        raw_matches = parsed
    else:
        return []

    # Valid statement type names
    valid_types = {
        "standalone_balance_sheet", "standalone_profit_and_loss", "standalone_cash_flow",
        "consolidated_balance_sheet", "consolidated_profit_and_loss", "consolidated_cash_flow",
    }

    matched: list[tuple[TocEntry, list[str]]] = []
    for item in raw_matches:
        if not isinstance(item, dict):
            continue
        idx = item.get("entry_index")
        stypes = item.get("statement_types", [])
        if idx is None or not stypes:
            continue
        try:
            idx = int(idx)
        except (ValueError, TypeError):
            continue
        if idx < 0 or idx >= len(entries):
            continue
        # Validate statement types
        valid_stypes = [s for s in stypes if s in valid_types]
        if valid_stypes:
            matched.append((entries[idx], valid_stypes))

    return matched


# ===================================================================
# Convenience function
# ===================================================================

def get_toc_page_hints(
    pdf_path: str | Path,
    pages: list[dict] | None = None,
    progress_callback=None,
) -> dict[str, list[int]]:
    """Get page hints from the Table of Contents.

    Shortcut for :func:`parse_toc_for_page_hints` that returns
    just the ``hints`` dict.

    Parameters
    ----------
    pdf_path : str | Path
        Path to the annual report PDF.
    pages : list[dict], optional
        Pre-parsed page dicts with ``{"page": int, "text": str}``.
    progress_callback : callable, optional
        Called with progress message strings.

    Returns
    -------
    dict[str, list[int]]
        Page hints mapping statement types to 1-based PDF page numbers.
        Empty dict if no TOC found or no financial statement entries.
    """
    result = parse_toc_for_page_hints(pdf_path, pages, progress_callback)
    return result.hints
