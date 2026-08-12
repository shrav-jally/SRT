"""Pipeline Orchestrator — wires all discovery stages together.

Entry point: ``run_discovery(pdf_path)`` → ``DiscoveryResult``

Execution order:
  Stage 0 → Stage 1 → Stage 3 → Stage 4 → Stage 7

The ``DiscoveryResult`` can then be used by Stage 9 (extraction.py)
to render pages, and by Stage 10 (existing VLM pipeline) to extract
financial data.

Stages ON HOLD: 2 (OCR), 5/8 (Layout), 6 (Embeddings).
Stage 10: existing ``vlm_extractor.py`` (untouched).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from .models import DiscoveryResult
from .classifier import classify_document
from .parser import parse_all_pages
from .candidates import generate_candidates
from .scoring import score_and_rank_candidates
from .validation import validate_and_resolve

logger = logging.getLogger(__name__)


def run_discovery(
    pdf_path: str | Path,
    page_hints: dict[str, list[int]] | None = None,
    progress_callback=None,
) -> DiscoveryResult:
    """Run the full page discovery pipeline.

    Parameters
    ----------
    pdf_path : str | Path
        Path to the annual report PDF.
    page_hints : dict, optional
        External page hints (e.g. from user input or prior run).
        These are treated as high-confidence bookmark-like signals.
    progress_callback : callable, optional
        Called with progress messages.

    Returns
    -------
    DiscoveryResult
        Contains the document info, parsed pages, and resolved
        statement pages.  Use ``result.to_page_hints()`` to get
        the dict that the VLM extractor expects.
    """
    pdf_path = Path(pdf_path)

    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    t0 = time.time()
    _log(f"[Discovery] Starting pipeline for: {pdf_path.name}")

    # ── Stage 0: Document Classification ─────────────────────────
    doc_info = classify_document(pdf_path, progress_callback)

    # ── Stage 1: Unified PDF Parsing ─────────────────────────────
    pages, bookmarks = parse_all_pages(pdf_path, doc_info, progress_callback)

    # ── Inject external page hints as bookmark-like candidates ───
    if page_hints:
        _log(f"[Discovery] Injecting {len(page_hints)} external page hint(s)")
        for stype_str, hint_pages in page_hints.items():
            for pg in hint_pages:
                bookmarks.append({
                    "level": 0,
                    "title": f"External hint: {stype_str}",
                    "page": pg,
                    "_synthetic": True,
                    "_statement_type": stype_str,
                })

    # ── Stage 3: Candidate Generation ────────────────────────────
    all_candidates = generate_candidates(
        pdf_path, pages, bookmarks, progress_callback,
    )

    # ── Stage 4: Confidence Scoring ──────────────────────────────
    ranked = score_and_rank_candidates(all_candidates, pages, progress_callback)

    # ── Stage 7: Sequence Validation ─────────────────────────────
    statements = validate_and_resolve(ranked, pages, progress_callback)

    elapsed = time.time() - t0
    _log(f"[Discovery] Pipeline complete in {elapsed:.2f}s — "
         f"found {len(statements)}/6 statements")

    return DiscoveryResult(
        document=doc_info,
        pages=pages,
        statements=statements,
        all_candidates=all_candidates,
    )
