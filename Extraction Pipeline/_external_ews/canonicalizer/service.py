"""Canonicalizer Service — Product 1 primary entry point."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

# Ensure graph directory is on path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_GRAPH_DIR = _PROJECT_ROOT / "graph"
for p in (str(_PROJECT_ROOT), str(_GRAPH_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from contracts import CanonicalDocument
from .primitives import build_canonical_primitives
from .sections import build_canonical_sections
from .table_inventory_adapter import build_canonical_tables
from .metadata import build_canonical_metadata
from .indexes import build_canonical_indexes
from .persistence import save_canonical_document

logger = logging.getLogger(__name__)


def canonicalize_pdf(
    pdf_path: str | Path,
    progress_callback=None,
    use_llm_taxonomy: bool = False,
    output_dir: Path | str | None = None,
) -> CanonicalDocument:
    """Ingest a raw PDF and emit a production-grade CanonicalDocument v0.

    Parameters
    ----------
    pdf_path : str | Path
        Path to input PDF file.
    progress_callback : callable, optional
        Status callback.
    use_llm_taxonomy : bool
        Whether to use LLM for taxonomy classification (default False for fast demo runs).
    output_dir : Path | str, optional
        Directory to save canonical JSON. Defaults to output/{document_id}.

    Returns
    -------
    CanonicalDocument
        Lossless canonical document intermediate representation.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    _log(f"[Canonicalizer] Starting Canonicalization v0 for: {pdf_path.name}")

    # 1. Run baseline 9-layer extraction pipeline (preserves legacy behavior)
    from sources.annual_report.extraction_pipeline import run_full_extraction

    raw_result = run_full_extraction(
        pdf_path=pdf_path,
        use_llm_taxonomy=use_llm_taxonomy,
        progress_callback=progress_callback,
    )

    doc_id = pdf_path.stem
    raw_metadata = raw_result.get("metadata", {})

    # 2. Build metadata
    src_meta, doc_meta = build_canonical_metadata(pdf_path, raw_metadata)

    # 3. Build primitives (pages, tokens, blocks)
    raw_pages = raw_result.get("raw_pages_text", [])
    pages, token_registry, blocks = build_canonical_primitives(raw_pages)

    # 4. Build sections
    raw_sections = raw_result.get("master_sections", [])
    sections = build_canonical_sections(raw_sections)

    # 5. Build tables
    raw_tables = raw_result.get("table_inventory", [])
    raw_table_extractions = raw_result.get("table_extractions", [])
    tables = build_canonical_tables(raw_tables, raw_table_extractions)

    # 6. Build indexes
    indexes = build_canonical_indexes(sections, tables, blocks, pages)

    # 7. Construct CanonicalDocument v0
    canonical_doc = CanonicalDocument(
        schema_version="v0",
        document_id=doc_id,
        source_metadata=src_meta,
        document_metadata=doc_meta,
        pages=pages,
        token_registry=token_registry,
        blocks=blocks,
        tables=tables,
        sections=sections,
        indexes=indexes,
        processing_metadata={
            "canonicalizer_version": "v0.1.0",
            "pipeline_elapsed_seconds": raw_metadata.get("pipeline_elapsed_seconds", 0.0),
            "raw_extractions": raw_result.get("structured_intelligence", {}),
            "raw_text_extractions": raw_result.get("text_extractions", []),
            "raw_evidence_map": raw_result.get("evidence_map", {}),
        },
    )

    # 8. Persist JSON to disk
    out_file = save_canonical_document(canonical_doc, output_dir=output_dir)
    _log(f"[Canonicalizer] Saved CanonicalDocument v0 to: {out_file}")

    return canonical_doc
