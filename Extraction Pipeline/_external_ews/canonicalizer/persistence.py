"""Persistence Adapter — saves and loads CanonicalDocument v0 JSON files to disk."""

from __future__ import annotations

import json
from pathlib import Path
from contracts import CanonicalDocument


def save_canonical_document(doc: CanonicalDocument, output_dir: Path | str | None = None) -> Path:
    """Save CanonicalDocument v0 to output/{document_id}/canonical_document.v0.json."""
    if output_dir:
        base_dir = Path(output_dir)
    else:
        base_dir = Path("output") / doc.document_id

    base_dir.mkdir(parents=True, exist_ok=True)
    out_file = base_dir / "canonical_document.v0.json"

    doc_json = doc.model_dump_json(indent=2)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(doc_json)

    return out_file


def load_canonical_document(json_path: Path | str) -> CanonicalDocument:
    """Load CanonicalDocument v0 from a JSON file."""
    path = Path(json_path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return CanonicalDocument.model_validate_json(content)
