"""Stage 0 — Document Classification.

Classifies a PDF into one of: text, scanned, hybrid, unknown.
Determines whether OCR is required (for future Stage 2).

This is a *lightweight* pass that opens the PDF once, samples a
subset of pages, and makes a classification decision without
performing any extraction.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .models import DocumentInfo, DocumentType

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────

# Pages with fewer characters than this are considered "low text"
LOW_TEXT_CHAR_THRESHOLD = 100

# If more than this fraction of pages are low-text, classify as scanned
SCANNED_FRACTION_THRESHOLD = 0.50

# If between this and SCANNED, classify as hybrid
HYBRID_FRACTION_THRESHOLD = 0.15


# ── Public API ────────────────────────────────────────────────────

def classify_document(
    pdf_path: str | Path,
    progress_callback=None,
) -> DocumentInfo:
    """Classify a PDF and return document-level metadata.

    Parameters
    ----------
    pdf_path : str | Path
        Path to the PDF file.
    progress_callback : callable, optional
        Called with progress messages.

    Returns
    -------
    DocumentInfo
        Document-level classification and metadata.
    """
    import pdfplumber

    pdf_path = Path(pdf_path)

    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    _log(f"[Stage 0] Classifying document: {pdf_path.name}")

    pages_char_counts: list[tuple[int, int]] = []  # (page_number, char_count)

    with pdfplumber.open(str(pdf_path)) as pdf:
        page_count = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            char_count = len(text.strip())
            pages_char_counts.append((i + 1, char_count))

    total_chars = sum(cc for _, cc in pages_char_counts)
    low_text_pages = [(pn, cc) for pn, cc in pages_char_counts if cc < LOW_TEXT_CHAR_THRESHOLD]
    low_text_count = len(low_text_pages)
    low_text_page_numbers = [pn for pn, _ in low_text_pages]

    # Classify
    if page_count == 0:
        doc_type = DocumentType.UNKNOWN
        confidence = 0.0
    else:
        low_fraction = low_text_count / page_count
        if low_fraction > SCANNED_FRACTION_THRESHOLD:
            doc_type = DocumentType.SCANNED
            confidence = min(low_fraction, 1.0)
        elif low_fraction > HYBRID_FRACTION_THRESHOLD:
            doc_type = DocumentType.HYBRID
            confidence = 0.7
        else:
            doc_type = DocumentType.TEXT
            confidence = 1.0 - low_fraction

    ocr_required = doc_type in (DocumentType.SCANNED, DocumentType.HYBRID)

    # Infer financial year from filename + first few pages
    fy = _infer_financial_year(pdf_path, pages_char_counts, pdf_path)

    info = DocumentInfo(
        file_path=pdf_path,
        file_name=pdf_path.name,
        page_count=page_count,
        document_type=doc_type,
        ocr_required=ocr_required,
        total_chars=total_chars,
        low_text_pages=low_text_count,
        low_text_page_numbers=low_text_page_numbers,
        confidence=confidence,
        financial_year=fy,
    )

    _log(
        f"[Stage 0] Classification: {doc_type.value} | "
        f"pages={page_count} | low_text={low_text_count} | "
        f"ocr_required={ocr_required} | confidence={confidence:.2f}"
    )

    return info


# ── Helpers ───────────────────────────────────────────────────────

def _infer_financial_year(
    pdf_path: Path,
    pages_char_counts: list[tuple[int, int]],
    original_path: Path,
) -> str | None:
    """Infer financial year from filename or early page text."""
    # Try filename first
    fy = _fy_from_text(pdf_path.name)
    if fy:
        return fy

    # Try first 5 pages with substantial text
    import pdfplumber
    with pdfplumber.open(str(original_path)) as pdf:
        for pn, cc in pages_char_counts[:5]:
            if cc < 50:
                continue
            text = pdf.pages[pn - 1].extract_text() or ""
            fy = _fy_from_text(text[:500])
            if fy:
                return fy
    return None


def _fy_from_text(text: str) -> str | None:
    """Extract financial year pattern from text."""
    patterns = [
        r"(20\d{2})\s*[-_/]\s*(20\d{2})",
        r"(20\d{2})\s*[-_/]\s*(\d{2})",
        r"financial year\s*(20\d{2})\s*[-_/]\s*(\d{2,4})",
        r"annual report\s*(20\d{2})\s*[-_/]\s*(\d{2,4})",
    ]
    lower = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lower)
        if not match:
            continue
        start = int(match.group(1))
        raw_end = match.group(2)
        end = int(raw_end) if len(raw_end) == 4 else 2000 + int(raw_end)
        if start <= end <= start + 1:
            return f"{start}-{str(end)[-2:]}"
    return None
