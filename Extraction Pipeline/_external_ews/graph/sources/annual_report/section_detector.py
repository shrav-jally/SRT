"""Section Detector — groups page-level taxonomy mappings into Master Sections.

This module takes the output of the taxonomy classification layer and collapses
contiguous pages belonging to the same subcategory into a single MasterSection.
It also assigns `content_type` and `extraction_strategy` based on the section.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# Sections that should be extracted as tables using VLM
TABLE_VLM_SECTIONS = {
    "Standalone Balance Sheet",
    "Standalone Profit & Loss",
    "Standalone Cash Flow",
    "Standalone Changes in Equity",
    "Consolidated Balance Sheet",
    "Consolidated Profit & Loss",
    "Consolidated Cash Flow",
    "Consolidated Changes in Equity",
    "Shareholding Pattern",
    "Segment Information",
    "Related Party Transactions",
    "Key Financial Ratios",
    "Ten Year Summary",
    "Financial Highlights"
}

def build_master_sections(
    taxonomy_mappings: list[dict[str, Any]],
    progress_callback=None,
) -> list[dict[str, Any]]:
    """Group contiguous pages of the same subcategory into Master Sections.

    Parameters
    ----------
    taxonomy_mappings : list[dict]
        Output from `taxonomy.classify_pages`. Expected to have `page_number`,
        `category`, `subcategory`, `confidence`.

    Returns
    -------
    list[dict]
        List of MasterSection dicts conforming to the Pydantic schema.
    """
    if not taxonomy_mappings:
        return []

    def _log(msg: str):
        logger.info(msg)
        if progress_callback:
            progress_callback(msg)

    _log(f"[SectionDetector] Building Master Sections from {len(taxonomy_mappings)} page mappings...")

    # Sort mappings by page number to ensure contiguous processing
    sorted_mappings = sorted(taxonomy_mappings, key=lambda x: x.get("page_number", 0))

    master_sections = []
    current_section = None

    for mapping in sorted_mappings:
        page_num = mapping.get("page_number", 0)
        category = mapping.get("category", "")
        subcategory = mapping.get("subcategory", "")
        confidence = mapping.get("confidence", 0.0)

        # Skip empty mappings
        if not category or not subcategory:
            continue

        if current_section is None:
            # Start first section
            current_section = _init_section(category, subcategory, page_num, confidence)
        else:
            # Check if this page continues the current section
            if current_section["category"] == category and current_section["section_name"] == subcategory:
                # Same section, extend end_page
                current_section["end_page"] = max(current_section["end_page"], page_num)
                # Average confidence tracking
                current_section["_conf_sum"] += confidence
                current_section["_conf_count"] += 1
            else:
                # New section started, finalize current
                master_sections.append(_finalize_section(current_section))
                current_section = _init_section(category, subcategory, page_num, confidence)

    if current_section is not None:
        master_sections.append(_finalize_section(current_section))

    _log(f"[SectionDetector] Created {len(master_sections)} Master Sections")
    return master_sections


def _init_section(category: str, subcategory: str, page_num: int, confidence: float) -> dict[str, Any]:
    content_type = "table" if subcategory in TABLE_VLM_SECTIONS else "text"
    strategy = "vlm" if content_type == "table" else "pdf_text"
    
    # Generate a readable section ID (e.g., FS_STANDALONE_BALANCE_SHEET_A1B2)
    prefix = "".join(word[0].upper() for word in category.split() if word)
    sub_clean = subcategory.upper().replace(" ", "_").replace("&", "AND")
    section_id = f"{prefix}_{sub_clean}_{uuid.uuid4().hex[:4].upper()}"

    return {
        "section_id": section_id,
        "section_name": subcategory,
        "category": category,
        "start_page": page_num,
        "end_page": page_num,
        "content_type": content_type,
        "extraction_strategy": strategy,
        "_conf_sum": confidence,
        "_conf_count": 1
    }


def _finalize_section(section: dict[str, Any]) -> dict[str, Any]:
    # Calculate final confidence
    conf_sum = section.pop("_conf_sum")
    conf_count = section.pop("_conf_count")
    section["confidence"] = round(conf_sum / max(conf_count, 1), 3)
    return section
