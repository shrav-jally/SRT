"""Stage 9 — Screenshot Extraction.

Renders the final identified pages into images (JPEG or PNG bytes)
using PyMuPDF (fitz).  The output format is identical to what the
existing ``vlm_extractor.render_page_images()`` produces, so the
VLM pipeline requires zero changes.

Since Layout Analysis (Stages 5/8) is ON HOLD, this stage performs
full-page rendering.  When layout detection is added later, this
module can be extended to crop table bounding boxes.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from .models import DiscoveryResult, StatementPages

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────

DEFAULT_DPI = 150
DEFAULT_MAX_PIXELS = 1500
DEFAULT_FORMAT = "jpeg"
DEFAULT_JPEG_QUALITY = 80


# ── Public API ────────────────────────────────────────────────────

def render_discovery_pages(
    pdf_path: str | Path,
    discovery: DiscoveryResult,
    dpi: int = DEFAULT_DPI,
    max_pixels: int = DEFAULT_MAX_PIXELS,
    fmt: str = DEFAULT_FORMAT,
    quality: int = DEFAULT_JPEG_QUALITY,
    progress_callback=None,
) -> dict[str, list[bytes]]:
    """Render identified pages into image bytes for each statement type.

    Parameters
    ----------
    pdf_path : str | Path
        Path to the PDF file.
    discovery : DiscoveryResult
        Output from the discovery pipeline (Stage 7).
    dpi : int
        Rendering resolution (default 150).
    max_pixels : int
        Maximum dimension — images larger than this are downscaled.
    fmt : str
        Output format: ``"jpeg"`` (default) or ``"png"``.
    quality : int
        JPEG quality (1-100, default 80). Ignored for PNG.
    progress_callback : callable, optional
        Called with progress messages.

    Returns
    -------
    dict[str, list[bytes]]
        Mapping of statement type string → list of image bytes,
        one image per page.
    """
    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    pdf_path = Path(pdf_path)
    _log(f"[Stage 9] Rendering identified pages from: {pdf_path.name}")

    result: dict[str, list[bytes]] = {}

    for stype_str, sp in discovery.statements.items():
        if not sp.pages:
            continue

        _log(f"[Stage 9] Rendering {stype_str}: pages {sp.pages}")
        images = _render_pages(
            pdf_path, sp.pages,
            dpi=dpi, max_pixels=max_pixels,
            fmt=fmt, quality=quality,
        )
        result[stype_str] = images
        _log(f"[Stage 9] {stype_str}: {len(images)} image(s) rendered")

    return result


def _render_pages(
    pdf_path: Path,
    page_numbers: list[int],
    dpi: int = DEFAULT_DPI,
    max_pixels: int = DEFAULT_MAX_PIXELS,
    fmt: str = DEFAULT_FORMAT,
    quality: int = DEFAULT_JPEG_QUALITY,
) -> list[bytes]:
    """Render specific PDF pages as image bytes.

    This mirrors ``vlm_extractor.render_page_images()`` to maintain
    full compatibility with the VLM pipeline.
    """
    import fitz  # PyMuPDF
    from PIL import Image

    images: list[bytes] = []
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)

    for pg_num in page_numbers:
        if pg_num < 1 or pg_num > total_pages:
            logger.warning(f"Page {pg_num} out of range (1-{total_pages}), skipping")
            continue

        page = doc[pg_num - 1]  # 0-based index
        pix = page.get_pixmap(dpi=dpi)

        # Convert to PIL Image
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        # Downscale if needed
        if max(img.size) > max_pixels:
            scale = max_pixels / max(img.size)
            new_size = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new_size, Image.LANCZOS)

        # Save to bytes
        buf = io.BytesIO()
        if fmt == "jpeg":
            img.save(buf, format="JPEG", quality=quality, optimize=True)
        else:
            img.save(buf, format="PNG", optimize=True)
        img_bytes = buf.getvalue()

        images.append(img_bytes)
        logger.debug(
            f"Rendered page {pg_num} ({len(img_bytes):,} bytes, "
            f"{fmt}, {img.width}x{img.height})"
        )

    doc.close()
    return images
