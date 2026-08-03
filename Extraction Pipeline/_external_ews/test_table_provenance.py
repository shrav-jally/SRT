import json
from canonicalizer.table_inventory_adapter import build_canonical_tables

# Mock data
detected_tables = [
    {"table_id": "TB_1", "page_no": 68, "table_type": "balance_sheet"}, # standalone
    {"table_id": "TB_2", "page_no": 108, "table_type": "balance_sheet"}, # consolidated
    {"table_id": "TB_3", "page_no": 110, "table_type": "balance_sheet"}, # kpi / random
]

extractions_raw = [
    {
        "table_name": "standalone_balance_sheet",
        "source_page": 68,
        "table_json": {"periods": ["2023", "2024"], "rows": [{"line_item": "Standalone Assets", "2023": "100"}]}
    },
    {
        "table_name": "consolidated_balance_sheet",
        "source_page": 108,
        "table_json": {"periods": ["2023", "2024"], "rows": [{"line_item": "Consolidated Assets", "2023": "200"}]}
    }
]

canonical_tables = build_canonical_tables(detected_tables, extractions_raw)

for tbl in canonical_tables:
    print(f"Table ID: {tbl.table_id}, Page: {tbl.page_numbers}")
    if tbl.rows and len(tbl.rows) > 1:
        cell_val = tbl.rows[1].cell_ids[0]
        cell_text = next(c.raw_text for c in tbl.cells if c.cell_id == cell_val)
        print(f"  First cell text: {cell_text}")
    else:
        print("  Empty table")
