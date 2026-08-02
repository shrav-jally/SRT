import json

with open('canonical_document.v0.json', encoding='utf-8') as f:
    doc = json.load(f)

sections = doc.get('sections', [])
tables = doc.get('tables', [])

# Build table lookup
tbl_by_id = {t['table_id']: t for t in tables}

print("=== SECTION -> TABLE LINKS ===")
for s in sections:
    tbl_ids = s.get('table_ids') or []
    if tbl_ids:
        pg = s.get('start_page', '?')
        title = (s.get('title_raw') or '')[:80]
        stype = s.get('section_type') or '?'
        print(f"\n  Section pg={pg} [{stype}] '{title}'")
        for tid in tbl_ids:
            tbl = tbl_by_id.get(tid)
            if tbl:
                cells = tbl.get('cells') or []
                pages = tbl.get('page_numbers') or []
                print(f"    -> Table {tid} pg={pages} cells={len(cells)}")
                if cells:
                    for c in cells[:8]:
                        rt = c.get('raw_text') or ''
                        print(f"       row={c.get('row_index')},col={c.get('col_index') or c.get('column_index')} => {str(rt)[:60]}")

print("\n\n=== TABLES WITH CELLS ON KEY PAGES ===")
for tbl in tables:
    cells = tbl.get('cells') or []
    pages = tbl.get('page_numbers') or []
    if cells and any(p in [68, 108, 109, 110] for p in pages):
        tid = tbl['table_id']
        print(f"\nTable {tid} pg={pages} cells={len(cells)}")
        # Show first 10 cells
        sorted_cells = sorted(cells, key=lambda c: (c.get('row_index',0), c.get('column_index') or c.get('col_index', 0)))
        for c in sorted_cells[:10]:
            rt = c.get('raw_text') or ''
            print(f"  r={c.get('row_index')},c={c.get('column_index') or c.get('col_index')} => {str(rt)[:80]}")
