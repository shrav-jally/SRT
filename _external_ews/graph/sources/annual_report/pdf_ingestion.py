"""PDF Ingestion Layer — extracts page-wise text, headings, TOC, and metadata.

Uses pdfplumber as the primary extraction engine, with PyMuPDF (fitz)
as a fallback for metadata and page rendering.

This layer produces a list of PageData objects that feed directly
into the Master Data Layer (SQLite).

Pipeline:
  1. Open PDF with pdfplumber
  2. Extract page-wise raw text
  3. Detect headings via structural cues (font size, position, caps)
  4. Parse TOC (reuses existing toc_parser.py)
  5. Assign section names based on heading cascade
  6. Return list[PageData] with page-level metadata
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ===================================================================
# Heading detection patterns
# ===================================================================

# Patterns that commonly indicate a heading in Indian annual reports.
# Ordered from most specific to least specific.
_HEADING_PATTERNS: list[tuple[re.Pattern, float]] = [
    # Numbered sections: "1. Directors Report", "II. Other Income"
    (re.compile(r"^\s*(?:[IVXLC]+\.|[0-9]{1,3}\.)\s+[A-Z]", re.MULTILINE), 0.85),
    # ALL CAPS lines (min 4 chars, max 120 chars, no digits-only)
    (re.compile(r"^[A-Z][A-Z\s&',.\-/()]{3,120}$", re.MULTILINE), 0.80),
    # Title Case lines that look like headings (short, standalone)
    (re.compile(r"^(?:[A-Z][a-z]+(?:\s+(?:and|&|of|the|to|for|in|on)\s+)?)+[A-Z][a-z]+\s*$", re.MULTILINE), 0.60),
]

# Known section heading keywords for Indian annual reports
_KNOWN_HEADINGS = [
    "corporate information",
    "corporate overview",
    "company information",
    "business overview",
    "chairman's message",
    "chairman's letter",
    "managing director's message",
    "ceo's message",
    "directors' report",
    "director's report",
    "directors report",
    "board of directors",
    "board's report",
    "management discussion and analysis",
    "management discussion & analysis",
    "md&a",
    "corporate governance",
    "corporate governance report",
    "report on corporate governance",
    "corporate social responsibility",
    "csr report",
    "csr policy",
    "business responsibility report",
    "business responsibility and sustainability report",
    "brsr",
    "esg report",
    "sustainability report",
    "risk management",
    "risk management report",
    "internal financial controls",
    "independent auditor's report",
    "independent auditors' report",
    "auditor's report",
    "auditors' report",
    "secretarial audit report",
    "standalone financial statements",
    "consolidated financial statements",
    "standalone financials",
    "consolidated financials",
    "balance sheet",
    "statement of profit and loss",
    "profit and loss account",
    "profit and loss statement",
    "cash flow statement",
    "statement of cash flows",
    "statement of changes in equity",
    "notes to accounts",
    "notes to financial statements",
    "notes forming part of financial statements",
    "significant accounting policies",
    "shareholding pattern",
    "shareholder information",
    "shareholder's information",
    "investor information",
    "related party transactions",
    "notice",
    "notice of annual general meeting",
    "annual general meeting",
    "proxy form",
    "attendance slip",
    "financial highlights",
    "financial summary",
    "ten year financial summary",
    "ratio analysis",
    "key financial ratios",
    "segment information",
    "segment report",
    "human resources",
    "human resource",
    "people",
    "our people",
    "employees",
    "employee stock option",
    "esop",
    "dividend history",
    "subsidiary companies",
    "joint ventures",
    "strategic initiatives",
    "strategy",
    "outlook",
    "future outlook",
    "guidance",
]


def ingest_pdf(pdf_path: str | Path, progress_callback=None) -> list[dict[str, Any]]:
    """Extract page-wise text and metadata from a PDF.

    Parameters
    ----------
    pdf_path : str | Path
        Path to the annual report PDF.
    progress_callback : callable, optional
        Called with progress message strings.

    Returns
    -------
    list[dict]
        List of page dicts with keys:
        - page_number (int, 1-based)
        - raw_text (str)
        - detected_heading (str)
        - section_name (str)
        - confidence (float)
        - char_count (int)
        - word_count (int)
        - line_count (int)
        - has_tables (bool)
    """
    import pdfplumber

    pdf_path = Path(pdf_path)

    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    _log(f"[Ingestion] Opening PDF: {pdf_path.name}")

    pages_data: list[dict[str, Any]] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        total_pages = len(pdf.pages)
        _log(f"[Ingestion] Total pages: {total_pages}")

        for i, page in enumerate(pdf.pages):
            page_num = i + 1

            # Extract raw text
            raw_text = page.extract_text() or ""

            # Extract tables presence
            tables = page.extract_tables() or []
            has_tables = len(tables) > 0

            # Detect heading
            heading, heading_confidence = _detect_heading(raw_text)

            # Basic stats
            char_count = len(raw_text)
            word_count = len(raw_text.split()) if raw_text.strip() else 0
            line_count = len(raw_text.splitlines()) if raw_text.strip() else 0

            pages_data.append({
                "page_number": page_num,
                "raw_text": raw_text,
                "detected_heading": heading,
                "section_name": "",  # Assigned in cascade pass below
                "confidence": heading_confidence,
                "char_count": char_count,
                "word_count": word_count,
                "line_count": line_count,
                "has_tables": has_tables,
            })

            if page_num % 50 == 0:
                _log(f"[Ingestion] Processed {page_num}/{total_pages} pages...")

    # ── Section cascade: propagate headings forward ──
    # Pages without a heading inherit the most recent heading as section_name
    _assign_sections(pages_data)

    _log(f"[Ingestion] Complete: {len(pages_data)} pages ingested, "
         f"{sum(1 for p in pages_data if p['detected_heading'])} headings detected")

    return pages_data


def _detect_heading(raw_text: str) -> tuple[str, float]:
    """Detect the primary heading on a page.

    Returns (heading_text, confidence). Empty string if no heading found.
    """
    if not raw_text or not raw_text.strip():
        return "", 0.0

    lines = raw_text.strip().splitlines()

    # Strategy 1: Check first 5 lines for known heading keywords
    for line in lines[:5]:
        cleaned = line.strip()
        if not cleaned or len(cleaned) < 4:
            continue

        lower = cleaned.lower()

        # Check against known headings
        for known in _KNOWN_HEADINGS:
            if known in lower:
                return cleaned, 0.95

    # Strategy 2: Check first 3 lines for structural heading patterns
    for line in lines[:3]:
        cleaned = line.strip()
        if not cleaned or len(cleaned) < 4 or len(cleaned) > 120:
            continue

        for pattern, conf in _HEADING_PATTERNS:
            if pattern.match(cleaned):
                # Verify it's not a data line (mostly numbers)
                alpha_ratio = sum(1 for c in cleaned if c.isalpha()) / max(len(cleaned), 1)
                if alpha_ratio > 0.5:
                    return cleaned, conf

    return "", 0.0


def _assign_sections(pages: list[dict[str, Any]]) -> None:
    """Cascade headings forward to assign section_name to all pages.

    Pages that have a detected_heading become section starts.
    Subsequent pages without headings inherit the most recent heading
    as their section_name.
    """
    current_section = ""
    for page in pages:
        if page["detected_heading"]:
            current_section = page["detected_heading"]
        page["section_name"] = current_section


def get_pdf_metadata(pdf_path: str | Path) -> dict[str, Any]:
    """Extract file-level metadata from a PDF using PyMuPDF.

    Returns dict with: page_count, title, author, subject, creator,
    producer, creation_date, file_size_bytes.
    """
    import fitz
    pdf_path = Path(pdf_path)

    metadata: dict[str, Any] = {
        "source_file": str(pdf_path),
        "file_name": pdf_path.name,
        "file_size_bytes": pdf_path.stat().st_size if pdf_path.exists() else 0,
    }

    try:
        with fitz.open(str(pdf_path)) as doc:
            metadata["page_count"] = len(doc)
            doc_meta = doc.metadata or {}
            metadata["title"] = doc_meta.get("title", "")
            metadata["author"] = doc_meta.get("author", "")
            metadata["subject"] = doc_meta.get("subject", "")
            metadata["creator"] = doc_meta.get("creator", "")
            metadata["producer"] = doc_meta.get("producer", "")
            metadata["creation_date"] = doc_meta.get("creationDate", "")
    except Exception as exc:
        logger.warning(f"Failed to extract PDF metadata: {exc}")
        metadata["page_count"] = 0

    return metadata
