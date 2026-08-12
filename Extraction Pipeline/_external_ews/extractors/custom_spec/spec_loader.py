"""Spec Loader — loads and validates CustomExtractionSpecDocument JSON files."""

from __future__ import annotations

import json
from pathlib import Path
from contracts import CustomExtractionSpecDocument


def load_custom_spec(spec_path: Path | str) -> CustomExtractionSpecDocument:
    """Load a custom extraction spec from a JSON file."""
    path = Path(spec_path)
    if not path.exists():
        raise FileNotFoundError(f"Custom extraction spec file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    return CustomExtractionSpecDocument.model_validate_json(content)
