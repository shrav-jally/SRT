"""Stage 1 — Unified PDF Parser.

Parses every page of the PDF into a rich ``PageInfo`` object that
downstream stages can query without re-opening the PDF.

Data sources:
  - **pdfplumber** — raw text, word count, character count
  - **PyMuPDF (fitz)** — page dimensions, rotation, image count,
    bookmarks/outlines, font statistics

The parser also computes derived metrics:
  - ``numeric_density`` — ratio of numeric tokens to total tokens
  - ``amount_count`` — count of Indian-format financial amounts
  - ``date_count`` — count of date patterns
  - ``table_density`` — heuristic combining amount_count and word_count
  - ``heading_candidates`` — first N non-trivial lines of text
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from .models import (
    DocumentInfo,
    FontInfo,
    PageInfo,
    PageType,
)

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────

# Max heading candidate lines to store per page
_MAX_HEADING_LINES = 12

# Threshold below which a page is classified as IMAGE type
_IMAGE_PAGE_TEXT_THRESHOLD = 30  # words


# ── Regex patterns ────────────────────────────────────────────────

# Indian-format amounts: "1,59,690.91", "(1,234)", "36,25,599.26"
_AMOUNT_RE = re.compile(
    r"\b\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?\b"
)

# Date patterns
_DATE_NUMERIC_RE = re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}")
_DATE_MONTH_RE = re.compile(
    r"\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)"
    r"[,\s']+\d{4}",
    re.IGNORECASE,
)
_DATE_MONTH_DAY_YEAR_RE = re.compile(
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}",
    re.IGNORECASE,
)
_YEAR_RANGE_RE = re.compile(r"\b\d{4}\s*[-/]\s*\d{2,4}\b")

# Numeric tokens (any token that is purely digits or has comma-separated digits)
_NUMERIC_TOKEN_RE = re.compile(r"^[\d,]+\.?\d*$")


# ── Public API ────────────────────────────────────────────────────

def parse_all_pages(
    pdf_path: str | Path,
    doc_info: DocumentInfo | None = None,
    progress_callback=None,
) -> tuple[list[PageInfo], list[dict[str, Any]]]:
    """Parse every page of the PDF into PageInfo objects.

    Parameters
    ----------
    pdf_path : str | Path
        Path to the PDF file.
    doc_info : DocumentInfo, optional
        Document classification from Stage 0 (for context).
    progress_callback : callable, optional
        Called with progress messages.

    Returns
    -------
    tuple[list[PageInfo], list[dict]]
        - List of PageInfo objects, one per page.
        - List of PDF bookmark entries (from PyMuPDF ``get_toc()``),
          each as ``{"level": int, "title": str, "page": int}``.
    """
    import pdfplumber

    pdf_path = Path(pdf_path)

    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    _log(f"[Stage 1] Parsing all pages: {pdf_path.name}")

    # ── Step 1: Extract bookmarks via PyMuPDF ────────────────────
    bookmarks = _extract_bookmarks(pdf_path)
    if bookmarks:
        _log(f"[Stage 1] Found {len(bookmarks)} PDF bookmark(s)")

    # ── Step 2: Extract page-level info via PyMuPDF ──────────────
    fitz_page_info = _extract_fitz_page_info(pdf_path)

    # ── Step 3: Parse text and build PageInfo via pdfplumber ─────
    pages: list[PageInfo] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        total = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            page_num = i + 1
            raw_text = page.extract_text() or ""

            # Basic counts
            words = raw_text.split()
            word_count = len(words)
            char_count = len(raw_text.strip())
            line_count = len(raw_text.splitlines())

            # Numeric density
            numeric_tokens = sum(1 for w in words if _NUMERIC_TOKEN_RE.match(w))
            numeric_density = numeric_tokens / max(word_count, 1)

            # Amount and date counts
            amount_count = len(_AMOUNT_RE.findall(raw_text))
            date_count = (
                len(_DATE_NUMERIC_RE.findall(raw_text))
                + len(_DATE_MONTH_RE.findall(raw_text))
                + len(_DATE_MONTH_DAY_YEAR_RE.findall(raw_text))
            )

            # Table density heuristic
            table_density = amount_count / max(word_count, 1)

            # Page dimensions and rotation from PyMuPDF
            fitz_info = fitz_page_info.get(page_num, {})
            page_width = fitz_info.get("width", float(page.width))
            page_height = fitz_info.get("height", float(page.height))
            rotation = fitz_info.get("rotation", 0)
            image_count = fitz_info.get("image_count", 0)
            fonts = fitz_info.get("fonts", FontInfo())

            # Page type
            if word_count < _IMAGE_PAGE_TEXT_THRESHOLD and image_count > 0:
                page_type = PageType.IMAGE
            elif word_count < _IMAGE_PAGE_TEXT_THRESHOLD:
                page_type = PageType.BLANK
            elif image_count > 2 and word_count < 100:
                page_type = PageType.MIXED
            else:
                page_type = PageType.TEXT

            is_corrupted = False
            if raw_text.count("(cid:") > 10:
                is_corrupted = True
            elif page_type == PageType.IMAGE:
                is_corrupted = True

            # Heading candidates: first N non-trivial lines
            heading_candidates = _extract_heading_candidates(raw_text)

            is_landscape = page_width > page_height

            pi = PageInfo(
                page_number=page_num,
                raw_text=raw_text,
                char_count=char_count,
                word_count=word_count,
                line_count=line_count,
                page_width=page_width,
                page_height=page_height,
                rotation=rotation,
                page_type=page_type,
                is_corrupted=is_corrupted,
                numeric_density=round(numeric_density, 4),
                amount_count=amount_count,
                date_count=date_count,
                table_density=round(table_density, 4),
                fonts=fonts,
                heading_candidates=heading_candidates,
                image_count=image_count,
                is_landscape=is_landscape,
            )
            pages.append(pi)

        _log(f"[Stage 1] Parsed {total} pages")

    # Summary stats
    text_pages = sum(1 for p in pages if p.page_type == PageType.TEXT)
    image_pages = sum(1 for p in pages if p.page_type == PageType.IMAGE)
    _log(
        f"[Stage 1] Page types: text={text_pages}, "
        f"image={image_pages}, "
        f"mixed={sum(1 for p in pages if p.page_type == PageType.MIXED)}, "
        f"blank={sum(1 for p in pages if p.page_type == PageType.BLANK)}"
    )

    return pages, bookmarks


# ── PyMuPDF helpers ───────────────────────────────────────────────

def _extract_bookmarks(pdf_path: Path) -> list[dict[str, Any]]:
    """Extract PDF bookmarks/outlines via PyMuPDF.

    Returns a list of dicts with keys: level, title, page (1-based).
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF (fitz) not installed — skipping bookmark extraction")
        return []

    try:
        doc = fitz.open(str(pdf_path))
        toc = doc.get_toc()  # [[level, title, page_number], ...]
        doc.close()
        return [
            {"level": entry[0], "title": entry[1], "page": entry[2]}
            for entry in toc
            if len(entry) >= 3 and entry[2] > 0
        ]
    except Exception as exc:
        logger.warning(f"Bookmark extraction failed: {exc}")
        return []


def _extract_fitz_page_info(pdf_path: Path) -> dict[int, dict]:
    """Extract per-page metadata via PyMuPDF (dimensions, rotation, images, fonts)."""
    try:
        import fitz
    except ImportError:
        return {}

    result: dict[int, dict] = {}
    try:
        doc = fitz.open(str(pdf_path))
        for i, page in enumerate(doc):
            page_num = i + 1
            rect = page.rect
            # Font analysis
            fonts = FontInfo()
            try:
                font_list = page.get_fonts()
                fonts.font_count = len(font_list)
                if font_list:
                    # Font names often contain "Bold" in the name
                    fonts.has_bold = any("bold" in (f[3] or "").lower() for f in font_list)
                    fonts.dominant_font = font_list[0][3] if font_list[0][3] else ""
            except Exception:
                pass

            result[page_num] = {
                "width": rect.width,
                "height": rect.height,
                "rotation": page.rotation,
                "image_count": len(page.get_images(full=True)),
                "fonts": fonts,
            }
        doc.close()
    except Exception as exc:
        logger.warning(f"PyMuPDF page info extraction failed: {exc}")

    return result


# ── Text helpers ──────────────────────────────────────────────────

def _extract_heading_candidates(text: str) -> list[str]:
    """Extract the first N non-trivial lines as heading candidates."""
    candidates: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) < 3:
            continue
        candidates.append(stripped)
        if len(candidates) >= _MAX_HEADING_LINES:
            break
    return candidates
