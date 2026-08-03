"""Indexes Adapter — constructs inverted lookups and section indexes for Product 2."""

from __future__ import annotations

from contracts import (
    CanonicalBlock,
    CanonicalIndexes,
    CanonicalPage,
    CanonicalSection,
    CanonicalTable,
)


def build_canonical_indexes(
    sections: list[CanonicalSection],
    tables: list[CanonicalTable],
    blocks: list[CanonicalBlock],
    pages: list[CanonicalPage],
) -> CanonicalIndexes:
    """Build fast inverted index maps for domain extraction engines."""
    sections_by_type: dict[str, list[str]] = {}
    table_ids_by_section_id: dict[str, list[str]] = {}
    blocks_by_page: dict[int, list[str]] = {}
    token_ids_by_page: dict[int, list[str]] = {}
    tables_by_page: dict[int, list[str]] = {}
    normalized_title_to_section_ids: dict[str, list[str]] = {}

    for sec in sections:
        s_type = sec.section_type
        sections_by_type.setdefault(s_type, []).append(sec.section_id)

        n_title = sec.title_normalized
        normalized_title_to_section_ids.setdefault(n_title, []).append(sec.section_id)

        if sec.table_ids:
            table_ids_by_section_id[sec.section_id] = sec.table_ids

    for tbl in tables:
        for p in tbl.page_numbers:
            tables_by_page.setdefault(p, []).append(tbl.table_id)

    for blk in blocks:
        blocks_by_page.setdefault(blk.page_number, []).append(blk.block_id)

    for pg in pages:
        token_ids_by_page[pg.page_number] = pg.token_ids

    return CanonicalIndexes(
        sections_by_type=sections_by_type,
        table_ids_by_section_id=table_ids_by_section_id,
        blocks_by_page=blocks_by_page,
        token_ids_by_page=token_ids_by_page,
        tables_by_page=tables_by_page,
        normalized_title_to_section_ids=normalized_title_to_section_ids,
    )
