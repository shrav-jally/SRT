"""Table Inventory Adapter — converts detected tables into CanonicalTable objects."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from contracts import (
    BoundingBox,
    CanonicalCell,
    CanonicalColumn,
    CanonicalRow,
    CanonicalTable,
    ValidationStatus,
)


def build_canonical_tables(
    detected_tables_raw: list[dict[str, Any]],
    table_extractions_raw: list[dict[str, Any]] | None = None,
) -> list[CanonicalTable]:
    """Convert detected and extracted tables into CanonicalTable objects."""
    canonical_tables: list[CanonicalTable] = []
    table_extractions_raw = table_extractions_raw or []

    # Group table extractions by their source page to strictly enforce page provenance
    extractions_by_page: dict[int, list[dict[str, Any]]] = {}
    for ext in table_extractions_raw:
        pg = ext.get("source_page")
        if pg:
            if pg not in extractions_by_page:
                extractions_by_page[pg] = []
            extractions_by_page[pg].append(ext)

    for idx, dt in enumerate(detected_tables_raw):
        table_id = dt.get("table_id") or f"tbl_p{dt.get('page_no', 1)}_{idx + 1:02d}"
        page_no = dt.get("page_no") or dt.get("page_number", 1)
        t_type = dt.get("table_type") or dt.get("table_name", "generic_table")

        # Create bounding box
        bbox = BoundingBox(x0=50.0, y0=100.0, x1=540.0, y1=500.0)

        # STRICT PROVENANCE MATCH: Only use an extraction if it was actually extracted from this exact page
        ext_data = None
        if page_no in extractions_by_page:
            # If multiple extractions on the same page, disambiguate by name/type
            page_exts = extractions_by_page[page_no]
            if len(page_exts) == 1:
                ext_data = page_exts[0]
            else:
                for ext in page_exts:
                    ext_name = ext.get("table_name", "").lower()
                    if t_type.lower() in ext_name or ext_name in t_type.lower():
                        ext_data = ext
                        break
                # Fallback if names don't match cleanly but they are on the same page
                if not ext_data:
                    ext_data = page_exts[0]
        cells: list[CanonicalCell] = []
        rows: list[CanonicalRow] = []
        cols: list[CanonicalColumn] = []

        if ext_data and isinstance(ext_data.get("table_json"), dict):
            t_json = ext_data["table_json"]
            periods = t_json.get("periods", [])
            ext_rows = t_json.get("rows", [])

            # Build header columns
            cols.append(CanonicalColumn(column_index=0, column_id="col_0", header_text="Particulars", role="label"))
            for p_idx, p_label in enumerate(periods):
                cols.append(CanonicalColumn(column_index=p_idx + 1, column_id=f"col_{p_idx+1}", header_text=str(p_label), role="numeric"))

            # Header row
            rows.append(CanonicalRow(row_index=0, row_id="row_0", cell_ids=[], is_header=True, role="header"))

            # Data rows
            for r_idx, r_item in enumerate(ext_rows, start=1):
                r_id = f"row_{r_idx}"
                cell_ids_in_row = []

                if isinstance(r_item, dict):
                    raw_label = str(r_item.get("line_item") or r_item.get("particulars", ""))
                    c_label_id = f"cell_r{r_idx}_c0"
                    c_label = CanonicalCell(
                        cell_id=c_label_id,
                        row_index=r_idx,
                        column_index=0,
                        bbox=BoundingBox(x0=50.0, y0=100.0 + (r_idx * 15), x1=250.0, y1=115.0 + (r_idx * 15)),
                        raw_text=raw_label,
                        role="data",
                    )
                    cells.append(c_label)
                    cell_ids_in_row.append(c_label_id)

                    # Period values dynamically extracted from any unknown keys
                    ignore_keys = {"line_item", "particulars", "note_no", "note", "notes"}
                    col_index = 1
                    for k, v in r_item.items():
                        if k.lower() not in ignore_keys:
                            cur_val = str(v or "").strip()
                            if cur_val:
                                c_val_id = f"cell_r{r_idx}_c{col_index}"
                                parsed = _parse_decimal(cur_val)
                                c_val = CanonicalCell(
                                    cell_id=c_val_id,
                                    row_index=r_idx,
                                    column_index=col_index,
                                    bbox=BoundingBox(x0=250.0 + (col_index * 10), y0=100.0 + (r_idx * 15), x1=400.0 + (col_index * 10), y1=115.0 + (r_idx * 15)),
                                    raw_text=cur_val,
                                    parsed_numeric=parsed,
                                    role="data",
                                )
                                cells.append(c_val)
                                cell_ids_in_row.append(c_val_id)
                                col_index += 1

                rows.append(CanonicalRow(row_index=r_idx, row_id=r_id, cell_ids=cell_ids_in_row, is_header=False, role="data"))

        canonical_tables.append(
            CanonicalTable(
                table_id=table_id,
                page_numbers=[page_no],
                bbox=bbox,
                detection_method=dt.get("detection_method", "table_detector"),
                structure_method="inventory_only" if not cells else "vlm_structured",
                rows=rows,
                columns=cols,
                cells=cells,
                validation_status=ValidationStatus.VALIDATED if cells else ValidationStatus.NOT_RUN,
                confidence=dt.get("detection_confidence", 0.85),
            )
        )

    return canonical_tables


def _parse_decimal(val_str: str) -> Decimal | None:
    cleaned = val_str.replace(",", "").strip()
    if not cleaned or cleaned in ("-", "—"):
        return None
    try:
        return Decimal(cleaned)
    except Exception:
        return None
