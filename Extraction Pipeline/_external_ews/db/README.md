# Financial Tables Database (`db/`)

A generic, column-based flat-file database that automatically stores every
extraction result in **both JSON and Excel** formats.

## Structure

```
db/
├── index.json              # Column-based index of all entries
├── json/                   # Full extraction results as JSON
│   └── {company}/{fy}.json
├── excel/                  # Full extraction results as Excel
│   └── {company}/{fy}.xlsx
└── README.md
```

## Index Schema

Each row in `index.json` has these columns:

| Column                    | Type     | Description                              |
|---------------------------|----------|------------------------------------------|
| `id`                      | string   | Unique key: `{company}__{fy}`            |
| `company`                 | string   | Company slug                             |
| `financial_year`          | string   | e.g. `"2023-24"`                         |
| `source_file`             | string   | Original PDF filename                    |
| `page_count`              | int      | Pages in the PDF                         |
| `extraction_method`       | string   | Method used (e.g. `word_position_clustering`) |
| `extraction_timestamp`    | string   | ISO 8601 timestamp                       |
| `quality_score`           | float    | Agent quality score (0–1)                |
| `standalone_bs_rows`      | int      | Standalone Balance Sheet row count       |
| `standalone_pl_rows`      | int      | Standalone P&L row count                 |
| `standalone_cf_rows`      | int      | Standalone Cash Flow row count           |
| `standalone_notes`        | int      | Standalone notes count                   |
| `consolidated_bs_rows`    | int      | Consolidated Balance Sheet row count     |
| `consolidated_pl_rows`    | int      | Consolidated P&L row count               |
| `consolidated_cf_rows`    | int      | Consolidated Cash Flow row count         |
| `consolidated_notes`      | int      | Consolidated notes count                 |
| `json_path`               | string   | Relative path to JSON file               |
| `excel_path`              | string   | Relative path to Excel file              |

## Auto-Save

When the app processes a PDF via any `/extract` endpoint, the result is
automatically saved to `db/`. No manual steps required.

## Query API

- `GET /db/entries` — list all entries
- `GET /db/entries?company=rajesh_exports_limited` — filter by company
- `GET /db/entries?financial_year=2023-24` — filter by year
- `GET /db/companies` — list all companies with their years
- `GET /db/json/{company}/{fy}` — download JSON for a specific entry
- `GET /db/excel/{company}/{fy}` — download Excel for a specific entry

## Python API

```python
from db import get_db

db = get_db()

# Save (auto-called by the API)
entry = db.save(extraction_result)

# Query
rows = db.query(company="rajesh_exports_limited")
rows = db.query(financial_year="2023-24")
rows = db.query(min_quality=0.7)

# Load data
result = db.get_json("rajesh_exports_limited", "2023-24")
xlsx   = db.get_excel_bytes("rajesh_exports_limited", "2023-24")

# List all
entries = db.list_entries()
comps   = db.companies()
```

## Loading into pandas

```python
import pandas as pd
df = pd.read_json("db/index.json")
```
