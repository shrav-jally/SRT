"""Primitives Adapter — converts raw PDF pages and text layout into CanonicalToken and CanonicalBlock objects."""

from __future__ import annotations

import re
from typing import Any
from contracts import BoundingBox, CanonicalBlock, CanonicalPage, CanonicalToken


def build_canonical_primitives(
    pages_raw: list[dict[str, Any]],
) -> tuple[list[CanonicalPage], dict[str, CanonicalToken], list[CanonicalBlock]]:
    """Convert raw ingested pages into CanonicalPage, CanonicalToken, and CanonicalBlock objects.

    Parameters
    ----------
    pages_raw : list[dict]
        Raw page dicts from pdf_ingestion / SQLite store.

    Returns
    -------
    tuple[list[CanonicalPage], dict[str, CanonicalToken], list[CanonicalBlock]]
        Pages list, token registry, and blocks list.
    """
    canonical_pages: list[CanonicalPage] = []
    token_registry: dict[str, CanonicalToken] = {}
    canonical_blocks: list[CanonicalBlock] = []

    for page_dict in pages_raw:
        page_num = page_dict.get("page_number", 1)
        raw_text = page_dict.get("raw_text", "")
        width = page_dict.get("width", 595.0)
        height = page_dict.get("height", 842.0)

        page_token_ids: list[str] = []
        page_block_ids: list[str] = []

        if not raw_text.strip():
            canonical_pages.append(
                CanonicalPage(
                    page_number=page_num,
                    width=width,
                    height=height,
                    rotation=0,
                    token_ids=[],
                    block_ids=[],
                )
            )
            continue

        lines = raw_text.splitlines()
        line_y_start = 50.0
        line_height = 14.0

        for line_idx, line in enumerate(lines):
            line_str = line.strip()
            if not line_str:
                continue

            y0 = line_y_start + (line_idx * line_height)
            y1 = y0 + 10.0

            words = line_str.split()
            word_x_start = 50.0
            block_token_ids: list[str] = []

            for word_idx, word in enumerate(words):
                token_id = f"p{page_num}_t{len(token_registry) + 1:04d}"
                x0 = word_x_start + (word_idx * 40.0)
                x1 = x0 + (len(word) * 6.0)

                tok = CanonicalToken(
                    token_id=token_id,
                    page_number=page_num,
                    text=word,
                    bbox=BoundingBox(x0=round(x0, 2), y0=round(y0, 2), x1=round(x1, 2), y1=round(y1, 2)),
                    reading_order_index=len(block_token_ids),
                )

                token_registry[token_id] = tok
                page_token_ids.append(token_id)
                block_token_ids.append(token_id)

            if block_token_ids:
                block_id = f"blk_p{page_num}_{len(canonical_blocks) + 1:03d}"
                b_x0 = min(token_registry[t].bbox.x0 for t in block_token_ids)
                b_y0 = min(token_registry[t].bbox.y0 for t in block_token_ids)
                b_x1 = max(token_registry[t].bbox.x1 for t in block_token_ids)
                b_y1 = max(token_registry[t].bbox.y1 for t in block_token_ids)

                is_heading = (
                    line_idx < 3 and len(line_str) < 80 and line_str.isupper()
                ) or (page_dict.get("detected_heading") and line_str in page_dict.get("detected_heading", ""))

                block_type = "heading" if is_heading else "paragraph"

                block = CanonicalBlock(
                    block_id=block_id,
                    page_number=page_num,
                    block_type=block_type,
                    bbox=BoundingBox(x0=b_x0, y0=b_y0, x1=b_x1, y1=b_y1),
                    token_ids=block_token_ids,
                    reading_order_index=line_idx,
                    confidence=0.90 if is_heading else 0.80,
                )

                canonical_blocks.append(block)
                page_block_ids.append(block_id)

        canonical_pages.append(
            CanonicalPage(
                page_number=page_num,
                width=width,
                height=height,
                rotation=0,
                token_ids=page_token_ids,
                block_ids=page_block_ids,
            )
        )

    return canonical_pages, token_registry, canonical_blocks
