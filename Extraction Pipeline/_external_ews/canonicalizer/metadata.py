"""Metadata Adapter — builds SourceMetadata and DocumentMetadata from pipeline execution metadata."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from contracts import DocumentMetadata, SourceMetadata


def build_canonical_metadata(
    pdf_path: Path,
    raw_metadata: dict[str, Any],
) -> tuple[SourceMetadata, DocumentMetadata]:
    """Construct SourceMetadata and DocumentMetadata objects."""
    file_hash = None
    if pdf_path.exists():
        try:
            h = hashlib.sha256()
            with open(pdf_path, "rb") as f:
                h.update(f.read(1024 * 1024))  # First 1MB for speed
            file_hash = f"sha256:{h.hexdigest()}"
        except Exception:
            pass

    src_meta = SourceMetadata(
        file_name=pdf_path.name,
        file_hash=file_hash,
        file_size_bytes=pdf_path.stat().st_size if pdf_path.exists() else 0,
        page_count=raw_metadata.get("page_count", 0),
        creation_date=raw_metadata.get("creation_date"),
        title=raw_metadata.get("title"),
        author=raw_metadata.get("author"),
        producer=raw_metadata.get("producer"),
    )

    doc_meta = DocumentMetadata(
        company_name=raw_metadata.get("company") or raw_metadata.get("company_name", "Unknown Company"),
        reporting_period=raw_metadata.get("financial_year") or raw_metadata.get("reporting_period", "2024-25"),
        fy_end=raw_metadata.get("fy_end", "31 March 2025"),
        currency="INR",
        unit_denomination=raw_metadata.get("unit_denomination", "Crore"),
        consolidation_type="consolidated" if "consolidated" in str(raw_metadata).lower() else "standalone",
    )

    return src_meta, doc_meta
