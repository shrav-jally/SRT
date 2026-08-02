"""Financial tables flat-file database.

A generic, column-based database that automatically stores extraction
results in both JSON and Excel formats.  Every time the app processes
a PDF the result is persisted here — no manual steps required.

Structure on disk::

    db/
    ├── index.json              # manifest of all saved entries
    ├── json/                   # one JSON file per extraction
    │   └── {company}/{fy}.json
    ├── excel/                  # one Excel file per extraction
    │   └── {company}/{fy}.xlsx
    └── README.md

Public API
----------
- ``save(result)``   — persist an extraction result (auto-called by the API)
- ``query(...)``     — search by company, year, statement type, etc.
- ``list_entries()`` — return all entries from the index
- ``export_excel()`` — build a master Excel with all data
"""

from db.store import Database, get_db

__all__ = ["Database", "get_db"]
