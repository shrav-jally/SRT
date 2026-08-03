"""Core database store — generic, column-based, auto-persisting.

Every extraction result is saved in two formats (JSON + Excel) and
registered in a column-based index that supports efficient queries.

Index schema (``index.json``)
-----------------------------
Each entry in the index is a flat dict with these columns::

    {
        "id":              "rajesh_exports_limited__2023-24",   # unique key
        "company":         "rajesh_exports_limited",           # slug
        "financial_year":  "2023-24",                          # FY
        "source_file":     "2023-24_nse_annual_report.pdf",    # original filename
        "page_count":      140,                                # pages in PDF
        "extraction_method": "word_position_clustering",       # method used
        "extraction_timestamp": "2026-07-02T05:21:57Z",       # ISO 8601
        "quality_score":   0.82,                               # agent quality (if available)
        "standalone_bs_rows":  22,                             # row counts per statement
        "standalone_pl_rows":  20,
        "standalone_cf_rows":  31,
        "standalone_notes":    0,
        "consolidated_bs_rows": 23,
        "consolidated_pl_rows": 20,
        "consolidated_cf_rows": 32,
        "consolidated_notes":   0,
        "json_path":  "json/rajesh_exports_limited/2023-24.json",
        "excel_path": "excel/rajesh_exports_limited/2023-24.xlsx",
    }

This flat column structure makes it trivial to load into pandas,
SQL, or any other analysis tool.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Paths ────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parent          # .../ews_finance/db
_INDEX_PATH = _ROOT / "index.json"
_JSON_DIR = _ROOT / "json"
_EXCEL_DIR = _ROOT / "excel"

# ── Lock for thread-safe writes ──────────────────────────────────────────

_lock = threading.Lock()


# ── Public API ───────────────────────────────────────────────────────────

class Database:
    """Flat-file database for financial table extractions.

    Typical usage::

        from db import get_db

        db = get_db()
        entry = db.save(extraction_result)
        rows  = db.query(company="rajesh_exports_limited")
        all   = db.list_entries()
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _ROOT
        self.index_path = self.root / "index.json"
        self.json_dir = self.root / "json"
        self.excel_dir = self.root / "excel"
        self._ensure_dirs()

    # ── save ──────────────────────────────────────────────────────────

    def save(self, result: dict[str, Any]) -> dict[str, Any]:
        """Persist an extraction result to JSON + Excel and update the index.

        Parameters
        ----------
        result : dict
            The full extraction result dict (as returned by the agent or
            legacy pipeline).  Must contain at least ``metadata``.

        Returns
        -------
        dict
            The index entry that was created / updated.
        """
        metadata = result.get("metadata", {})
        company = _slug(metadata.get("company") or _guess_company(result)) or "unknown_company"
        fy = metadata.get("financial_year") or _guess_fy(metadata.get("source_file", "")) or "unknown_fy"

        entry_id = f"{company}__{fy}"

        # Build columnar index entry
        entry = self._build_entry(entry_id, company, fy, result)

        with _lock:
            # Save JSON
            json_path = self.json_dir / company / f"{fy}.json"
            json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(json_path, "w") as f:
                json.dump(result, f, indent=2, default=str)

            # Save Excel
            excel_path = self.excel_dir / company / f"{fy}.xlsx"
            excel_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._save_excel(result, excel_path)
            except Exception as exc:
                entry["excel_path"] = None
                entry["excel_error"] = str(exc)

            # Update index
            index = self._load_index()
            # Replace existing entry or append new
            index = [e for e in index if e["id"] != entry_id]
            index.append(entry)
            index.sort(key=lambda e: (e["company"], e["financial_year"]))
            self._write_index(index)

        return entry

    # ── query ─────────────────────────────────────────────────────────

    def query(
        self,
        company: str | None = None,
        financial_year: str | None = None,
        method: str | None = None,
        min_quality: float | None = None,
    ) -> list[dict[str, Any]]:
        """Search the index by column values.

        All parameters are optional filters; multiple filters are AND-ed.
        Company filter uses case-insensitive substring matching.
        """
        index = self._load_index()
        results = []
        company_slug = _slug(company) if company else None
        for entry in index:
            if company_slug:
                entry_company = entry.get("company", "")
                # Substring match: "rajesh" matches "rajesh_exports_limited"
                if company_slug not in entry_company and entry_company not in company_slug:
                    continue
            if financial_year and entry.get("financial_year") != financial_year:
                continue
            if method and entry.get("extraction_method") != method:
                continue
            if min_quality is not None:
                score = entry.get("quality_score")
                if score is None or score < min_quality:
                    continue
            results.append(entry)
        return results

    # ── list_entries ──────────────────────────────────────────────────

    def list_entries(self) -> list[dict[str, Any]]:
        """Return all entries from the index."""
        return self._load_index()

    # ── get_json ──────────────────────────────────────────────────────

    def get_json(self, company: str, financial_year: str) -> dict[str, Any] | None:
        """Load the full JSON result for a given company + year.

        Looks up the actual stored company slug from the index to handle
        cases where the query company name doesn't exactly match.
        """
        entry = self._find_entry(company, financial_year)
        if not entry:
            return None
        json_rel = entry.get("json_path")
        if not json_rel:
            return None
        path = self.root / json_rel
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    # ── get_excel_bytes ───────────────────────────────────────────────

    def get_excel_bytes(self, company: str, financial_year: str) -> bytes | None:
        """Load the Excel bytes for a given company + year."""
        entry = self._find_entry(company, financial_year)
        if not entry:
            return None
        excel_rel = entry.get("excel_path")
        if not excel_rel:
            return None
        path = self.root / excel_rel
        if not path.exists():
            return None
        return path.read_bytes()

    # ── delete ────────────────────────────────────────────────────────

    def delete(self, company: str, financial_year: str) -> bool:
        """Remove an entry from the database."""
        with _lock:
            index = self._load_index()
            # Find the matching entry (supports substring matching)
            target = self._find_entry_in(company, financial_year, index)
            if not target:
                return False  # not found

            entry_id = target["id"]
            new_index = [e for e in index if e["id"] != entry_id]

            # Remove files using stored paths
            for rel_key in ("json_path", "excel_path"):
                rel = target.get(rel_key)
                if rel:
                    p = self.root / rel
                    if p.exists():
                        p.unlink()

            self._write_index(new_index)
        return True

    # ── companies ─────────────────────────────────────────────────────

    def companies(self) -> dict[str, list[str]]:
        """Return ``{company_slug: [fy1, fy2, ...]}`` for all entries."""
        index = self._load_index()
        result: dict[str, list[str]] = {}
        for entry in index:
            c = entry["company"]
            result.setdefault(c, []).append(entry["financial_year"])
        for v in result.values():
            v.sort()
        return result

    # ── Internal ──────────────────────────────────────────────────────

    def _find_entry(self, company: str, financial_year: str) -> dict[str, Any] | None:
        """Find an entry by company (substring match) + financial_year."""
        index = self._load_index()
        return self._find_entry_in(company, financial_year, index)

    @staticmethod
    def _find_entry_in(
        company: str, financial_year: str, index: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Find an entry in a given index list."""
        company_slug = _slug(company)
        for entry in index:
            if entry.get("financial_year") != financial_year:
                continue
            entry_company = entry.get("company", "")
            if company_slug == entry_company or company_slug in entry_company or entry_company in company_slug:
                return entry
        return None

    def _ensure_dirs(self) -> None:
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.excel_dir.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        with open(self.index_path) as f:
            data = json.load(f)
        # Support both formats: bare list or {"entries": [...]}
        if isinstance(data, list):
            return data
        return data.get("entries", [])

    def _write_index(self, entries: list[dict[str, Any]]) -> None:
        # Write as a bare list for easy pandas/jsonl loading
        with open(self.index_path, "w") as f:
            json.dump(entries, f, indent=2, default=str)

    def _build_entry(
        self, entry_id: str, company: str, fy: str, result: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = result.get("metadata", {})
        pipeline = result.get("pipeline", {})

        # Count rows per statement
        sa = result.get("standalone", {})
        co = result.get("consolidated", {})

        entry = {
            "id": entry_id,
            "company": company,
            "financial_year": fy,
            "source_file": metadata.get("file_name", ""),
            "page_count": metadata.get("page_count"),
            "extraction_method": pipeline.get("extraction_method") or metadata.get("extraction_method", "unknown"),
            "extraction_timestamp": metadata.get("extraction_timestamp") or datetime.now(timezone.utc).isoformat(),
            "quality_score": result.get("quality_score"),
            # Standalone row counts
            "standalone_bs_rows": len(sa.get("balance_sheet", {}).get("rows", [])),
            "standalone_pl_rows": len(sa.get("profit_and_loss", {}).get("rows", [])),
            "standalone_cf_rows": len(sa.get("cash_flow", {}).get("rows", [])),
            "standalone_notes": len(sa.get("notes_to_accounts", [])),
            # Consolidated row counts
            "consolidated_bs_rows": len(co.get("balance_sheet", {}).get("rows", [])),
            "consolidated_pl_rows": len(co.get("profit_and_loss", {}).get("rows", [])),
            "consolidated_cf_rows": len(co.get("cash_flow", {}).get("rows", [])),
            "consolidated_notes": len(co.get("notes_to_accounts", [])),
            # File paths (relative to db/)
            "json_path": f"json/{company}/{fy}.json",
            "excel_path": f"excel/{company}/{fy}.xlsx",
        }

        # Add validation summary if present
        for entity, prefix in [("standalone", "sa"), ("consolidated", "co")]:
            for stmt in ("balance_sheet", "profit_and_loss", "cash_flow"):
                validation = result.get(entity, {}).get(stmt, {}).get("validation")
                if validation:
                    key = f"{prefix}_{stmt[:2]}_validation"
                    entry[key] = validation

        # Add cross-validation score if present
        cv = result.get("cross_validation")
        if cv and cv.get("overall_score") is not None:
            entry["cross_validation_score"] = cv["overall_score"]

        return entry

    def _save_excel(self, result: dict[str, Any], path: Path) -> None:
        """Generate and save Excel using the excel_builder module."""
        import sys
        graph_src = str(Path(__file__).resolve().parent.parent / "graph")
        if graph_src not in sys.path:
            sys.path.insert(0, graph_src)
        from sources.annual_report.excel_builder import save_excel
        save_excel(result, path)


# ── Singleton ────────────────────────────────────────────────────────────

_db_instance: Database | None = None


def get_db() -> Database:
    """Return the singleton Database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance


# ── Helpers ──────────────────────────────────────────────────────────────

def _slug(name: str) -> str:
    """Convert a name to a filesystem-friendly slug."""
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _guess_company(result: dict[str, Any]) -> str:
    """Try to infer company name from the extraction result."""
    # Check metadata
    metadata = result.get("metadata", {})
    for key in ("company", "company_name", "entity"):
        val = metadata.get(key)
        if val:
            return str(val)

    # Check source_file path for known company names
    source = metadata.get("source_file", "")
    # Look for known patterns in path
    known_companies = [
        "rajesh_exports_limited",
        "brightcom_group_limited",
        "cg_power_and_industrial_solutions_limited",
        "tata_consultancy_services_limited",
        "cox_and_kings_limited",
        "gensol_engineering_limited",
    ]
    source_lower = source.lower().replace("-", "_")
    for company in known_companies:
        if company in source_lower:
            return company

    # Fallback: use the parent directory name from source path
    if source:
        parts = Path(source).parts
        for part in reversed(parts):
            part_clean = part.lower().replace("-", "_").replace(" ", "_")
            if part_clean not in ("pdfs", "data", "downloads", "uploads", "company"):
                return part_clean

    return "unknown_company"


def _guess_fy(filename: str) -> str:
    """Extract financial year from a filename like '2023-24_nse_annual_report.pdf'."""
    m = re.search(r"(20\d{2}[-_]\d{2,4})", filename)
    return m.group(1).replace("_", "-") if m else ""
