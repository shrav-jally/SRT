"""Sections Adapter — converts pipeline section registry into CanonicalSection objects."""

from __future__ import annotations

import re
from typing import Any
from contracts import CanonicalSection


def build_canonical_sections(
    master_sections_raw: list[dict[str, Any]],
) -> list[CanonicalSection]:
    """Convert raw master_sections dicts into CanonicalSection objects."""
    canonical_sections: list[CanonicalSection] = []

    for idx, sec in enumerate(master_sections_raw):
        sec_id = sec.get("section_id") or f"sec_{idx + 1:03d}"
        title_raw = sec.get("raw_section_name") or sec.get("section_name") or sec.get("category", f"Section {idx+1}")
        title_norm = sec.get("normalized_section_name") or _slugify(title_raw)

        category = sec.get("category", "Unclassified")
        subcategory = sec.get("subcategory") or sec.get("section_subtype") or title_norm
        section_type = sec.get("section_type") or "other"

        start_page = sec.get("start_page", 1)
        end_page = sec.get("end_page", start_page)

        c_sec = CanonicalSection(
            section_id=sec_id,
            title_raw=title_raw,
            title_normalized=title_norm,
            section_type=section_type,
            subcategory=subcategory,
            start_page=start_page,
            end_page=end_page,
            confidence=sec.get("confidence", 0.90),
            taxonomy_path=f"{category} > {subcategory}",
        )
        canonical_sections.append(c_sec)

    return canonical_sections


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "_", cleaned).strip("_")
