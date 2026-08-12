"""Master Data Layer — SQLite-backed normalized page repository.

This module manages a per-extraction SQLite database that stores
page-level data and serves as the single source of truth for all
downstream extraction layers.

Schema
------
Table ``pages``:
    page_number     INTEGER PRIMARY KEY  — 1-based page index
    raw_text        TEXT                 — full extracted text
    detected_heading TEXT                — heading detected on this page
    section_name    TEXT                 — cascaded section name
    confidence      REAL                — heading detection confidence
    char_count      INTEGER             — character count
    word_count      INTEGER             — word count
    line_count      INTEGER             — line count
    has_tables      INTEGER             — 1 if pdfplumber detected tables

Table ``taxonomy_mappings``:
    id              INTEGER PRIMARY KEY AUTOINCREMENT
    page_number     INTEGER             — FK to pages
    category        TEXT                — taxonomy category
    subcategory     TEXT                — taxonomy subcategory
    confidence      REAL                — classification confidence
    method          TEXT                — "llm" | "keyword_regex"

Table ``detected_tables``:
    id              INTEGER PRIMARY KEY AUTOINCREMENT
    page_number     INTEGER             — FK to pages
    table_type      TEXT                — e.g. "balance_sheet"
    detection_confidence REAL
    needs_vlm       INTEGER             — 1 if VLM fallback needed
    numeric_density REAL
    column_count    INTEGER

Usage::

    from master_data import MasterDataStore

    store = MasterDataStore()
    store.load_pages(pages_data)  # from pdf_ingestion
    pages = store.get_pages_by_section("Directors Report")
    store.close()
"""

from __future__ import annotations

import logging
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MasterDataStore:
    """SQLite-backed master data repository for a single extraction session.

    Creates an in-memory SQLite database by default, or a file-based one
    if ``db_path`` is provided.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path:
            self.db_path = str(db_path)
        else:
            # Use in-memory DB for single-session extraction
            self.db_path = ":memory:"

        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._create_tables()

    def _create_tables(self) -> None:
        """Create the schema tables if they don't exist."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS pages (
                page_number     INTEGER PRIMARY KEY,
                raw_text        TEXT DEFAULT '',
                detected_heading TEXT DEFAULT '',
                section_name    TEXT DEFAULT '',
                confidence      REAL DEFAULT 0.0,
                char_count      INTEGER DEFAULT 0,
                word_count      INTEGER DEFAULT 0,
                line_count      INTEGER DEFAULT 0,
                has_tables      INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS taxonomy_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_number INTEGER,
                section_type TEXT DEFAULT '',
                section_subtype TEXT DEFAULT '',
                category TEXT,
                subcategory TEXT,
                confidence REAL,
                extraction_method TEXT
            );

            CREATE TABLE IF NOT EXISTS master_sections (
                section_id TEXT PRIMARY KEY,
                section_name TEXT,
                section_type TEXT DEFAULT '',
                section_subtype TEXT DEFAULT '',
                category TEXT,
                subcategory TEXT DEFAULT '',
                start_page INTEGER,
                end_page INTEGER,
                content_type TEXT,
                extraction_strategy TEXT,
                confidence REAL,
                section_status TEXT DEFAULT 'confirmed',
                boundary_source TEXT DEFAULT 'classifier',
                source TEXT DEFAULT 'taxonomy',
                toc_entry TEXT DEFAULT '',
                page_count INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS table_inventory (
                table_id TEXT PRIMARY KEY,
                table_name TEXT,
                table_category TEXT DEFAULT 'other',
                page_no INTEGER,
                complexity_score REAL,
                needs_vlm INTEGER,
                parent_section_id TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS detected_tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_number INTEGER,
                table_type TEXT,
                detection_confidence REAL,
                needs_vlm INTEGER,
                numeric_density REAL,
                column_count INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_pages_section
                ON pages(section_name);
            CREATE INDEX IF NOT EXISTS idx_pages_heading
                ON pages(detected_heading);
            CREATE INDEX IF NOT EXISTS idx_taxonomy_category
                ON taxonomy_mappings(category);
            CREATE INDEX IF NOT EXISTS idx_taxonomy_page
                ON taxonomy_mappings(page_number);
            CREATE INDEX IF NOT EXISTS idx_tables_type
                ON detected_tables(table_type);
            CREATE INDEX IF NOT EXISTS idx_master_sections_cat
                ON master_sections(category);
            CREATE INDEX IF NOT EXISTS idx_table_inventory_page
                ON table_inventory(page_no);
        """)
        self._conn.commit()

    # ── Page operations ──────────────────────────────────────────────

    def load_pages(self, pages_data: list[dict[str, Any]]) -> int:
        """Bulk-insert page data from the ingestion layer.

        Parameters
        ----------
        pages_data : list[dict]
            List of page dicts from ``pdf_ingestion.ingest_pdf()``.

        Returns
        -------
        int
            Number of pages inserted.
        """
        count = 0
        for page in pages_data:
            try:
                self._conn.execute(
                    """INSERT OR REPLACE INTO pages
                       (page_number, raw_text, detected_heading, section_name,
                        confidence, char_count, word_count, line_count, has_tables)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        page["page_number"],
                        page.get("raw_text", ""),
                        page.get("detected_heading", ""),
                        page.get("section_name", ""),
                        page.get("confidence", 0.0),
                        page.get("char_count", 0),
                        page.get("word_count", 0),
                        page.get("line_count", 0),
                        1 if page.get("has_tables") else 0,
                    ),
                )
                count += 1
            except Exception as exc:
                logger.warning(f"Failed to insert page {page.get('page_number')}: {exc}")
        self._conn.commit()
        logger.info(f"[MasterData] Loaded {count} pages into SQLite")
        return count

    def get_page(self, page_number: int) -> dict[str, Any] | None:
        """Get a single page by number."""
        row = self._conn.execute(
            "SELECT * FROM pages WHERE page_number = ?", (page_number,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_pages(self) -> list[dict[str, Any]]:
        """Get all pages ordered by page number."""
        rows = self._conn.execute(
            "SELECT * FROM pages ORDER BY page_number"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_pages_by_section(self, section_name: str) -> list[dict[str, Any]]:
        """Get all pages belonging to a section (case-insensitive match)."""
        rows = self._conn.execute(
            "SELECT * FROM pages WHERE LOWER(section_name) = LOWER(?) ORDER BY page_number",
            (section_name,),
        ).fetchall()
        return [dict(r) for r in rows]

    def search_pages_by_section(self, keyword: str) -> list[dict[str, Any]]:
        """Search pages whose section_name contains the keyword (case-insensitive)."""
        rows = self._conn.execute(
            "SELECT * FROM pages WHERE LOWER(section_name) LIKE LOWER(?) ORDER BY page_number",
            (f"%{keyword}%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_pages_in_range(self, start: int, end: int) -> list[dict[str, Any]]:
        """Get pages in a page number range (inclusive)."""
        rows = self._conn.execute(
            "SELECT * FROM pages WHERE page_number >= ? AND page_number <= ? ORDER BY page_number",
            (start, end),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_pages_with_tables(self) -> list[dict[str, Any]]:
        """Get all pages that have detected tables."""
        rows = self._conn.execute(
            "SELECT * FROM pages WHERE has_tables = 1 ORDER BY page_number"
        ).fetchall()
        return [dict(r) for r in rows]

    def search_text(self, keyword: str) -> list[dict[str, Any]]:
        """Search pages whose raw_text contains the keyword (case-insensitive)."""
        rows = self._conn.execute(
            "SELECT * FROM pages WHERE LOWER(raw_text) LIKE LOWER(?) ORDER BY page_number",
            (f"%{keyword}%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_unique_sections(self) -> list[str]:
        """Get all unique section names ordered by their first appearance."""
        rows = self._conn.execute(
            """SELECT section_name, MIN(page_number) as first_page
               FROM pages WHERE section_name != ''
               GROUP BY section_name
               ORDER BY first_page"""
        ).fetchall()
        return [r["section_name"] for r in rows]

    def get_total_pages(self) -> int:
        """Get total number of pages."""
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM pages").fetchone()
        return row["cnt"] if row else 0

    # ── Taxonomy operations ──────────────────────────────────────────

    def save_taxonomy_mapping(
        self,
        page_number: int,
        category: str,
        subcategory: str = "",
        confidence: float = 0.0,
        method: str = "keyword_regex",
        section_type: str = "",
        section_subtype: str = "",
    ) -> None:
        """Insert a taxonomy mapping for a page."""
        self._conn.execute(
            """INSERT INTO taxonomy_mappings
               (page_number, section_type, section_subtype, category, subcategory, confidence, extraction_method)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (page_number, section_type, section_subtype, category, subcategory, confidence, method),
        )
        self._conn.commit()

    def save_taxonomy_mappings_bulk(
        self, mappings: list[dict[str, Any]]
    ) -> int:
        """Bulk-insert taxonomy mappings."""
        count = 0
        for m in mappings:
            try:
                self._conn.execute(
                    """INSERT INTO taxonomy_mappings
                       (page_number, section_type, section_subtype, category, subcategory, confidence, extraction_method)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        m["page_number"],
                        m.get("section_type", ""),
                        m.get("section_subtype", ""),
                        m.get("category", ""),
                        m.get("subcategory", ""),
                        m.get("confidence", 0.0),
                        m.get("method", "keyword_regex"),
                    ),
                )
                count += 1
            except Exception as exc:
                logger.warning(f"Failed to insert taxonomy mapping: {exc}")
        self._conn.commit()
        return count

    def get_taxonomy_by_category(self, category: str) -> list[dict[str, Any]]:
        """Get all taxonomy mappings for a category."""
        rows = self._conn.execute(
            """SELECT tm.*, p.raw_text, p.section_name
               FROM taxonomy_mappings tm
               JOIN pages p ON tm.page_number = p.page_number
               WHERE LOWER(tm.category) = LOWER(?)
               ORDER BY tm.page_number""",
            (category,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_taxonomy_for_page(self, page_number: int) -> list[dict[str, Any]]:
        """Get all taxonomy mappings for a specific page."""
        rows = self._conn.execute(
            "SELECT * FROM taxonomy_mappings WHERE page_number = ?",
            (page_number,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_taxonomy_mappings(self) -> list[dict[str, Any]]:
        """Get all taxonomy mappings."""
        rows = self._conn.execute(
            "SELECT * FROM taxonomy_mappings ORDER BY page_number"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Section Registry operations (Phase 2) ────────────────────────

    def save_master_sections(self, sections: list[dict[str, Any]]) -> None:
        """Bulk save Master Sections."""
        if not sections:
            return
        
        self._conn.executemany(
            """INSERT OR REPLACE INTO master_sections
               (section_id, section_name, section_type, section_subtype, category, subcategory, start_page, end_page,
                content_type, extraction_strategy, confidence, section_status, boundary_source, source, toc_entry, page_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    s["section_id"], s.get("normalized_section_name", s.get("raw_section_name", "")), s.get("section_type", ""), s.get("section_subtype", ""),
                    s.get("category", ""), s.get("subcategory", ""), s["start_page"], s["end_page"],
                    s["content_type"], s["extraction_strategy"], s["confidence"],
                    s.get("section_status", "confirmed"), s.get("boundary_source", "classifier"),
                    s.get("source", "taxonomy"), s.get("toc_entry", ""),
                    s.get("page_count", s["end_page"] - s["start_page"] + 1)
                )
                for s in sections
            ]
        )
        self._conn.commit()

    def get_master_sections(self) -> list[dict[str, Any]]:
        """Get all Master Sections ordered by start page."""
        rows = self._conn.execute(
            "SELECT * FROM master_sections ORDER BY start_page"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Table operations (Phase 3) ───────────────────────────────────

    def save_table_inventory(self, inventory: list[dict[str, Any]]) -> None:
        """Bulk save Table Inventory Items."""
        if not inventory:
            return
            
        self._conn.executemany(
            """INSERT OR REPLACE INTO table_inventory
               (table_id, table_name, table_category, page_no, complexity_score, needs_vlm, parent_section_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    t["table_id"], t["table_name"],
                    t.get("table_category", "other"),
                    t["page_no"],
                    t["complexity_score"], 1 if t["needs_vlm"] else 0,
                    t.get("parent_section_id", ""),
                )
                for t in inventory
            ]
        )
        self._conn.commit()

    def get_table_inventory(self) -> list[dict[str, Any]]:
        """Get all Table Inventory Items ordered by page."""
        rows = self._conn.execute(
            "SELECT table_id, table_name, page_no, complexity_score, needs_vlm FROM table_inventory ORDER BY page_no"
        ).fetchall()
        return [
            {
                "table_id": r["table_id"],
                "table_name": r["table_name"],
                "page_no": r["page_no"],
                "complexity_score": r["complexity_score"],
                "needs_vlm": bool(r["needs_vlm"]),
            }
            for r in rows
        ]

    # ── Detected tables operations ───────────────────────────────────

    def save_detected_table(
        self,
        page_number: int,
        table_type: str,
        detection_confidence: float = 0.0,
        needs_vlm: bool = False,
        numeric_density: float = 0.0,
        column_count: int = 0,
    ) -> None:
        """Insert a detected table entry."""
        self._conn.execute(
            """INSERT INTO detected_tables
               (page_number, table_type, detection_confidence, needs_vlm,
                numeric_density, column_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (page_number, table_type, detection_confidence,
             1 if needs_vlm else 0, numeric_density, column_count),
        )
        self._conn.commit()

    def get_detected_tables(self, table_type: str | None = None) -> list[dict[str, Any]]:
        """Get detected tables, optionally filtered by type."""
        if table_type:
            rows = self._conn.execute(
                "SELECT * FROM detected_tables WHERE LOWER(table_type) = LOWER(?) ORDER BY page_number",
                (table_type,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM detected_tables ORDER BY page_number"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_tables_needing_vlm(self) -> list[dict[str, Any]]:
        """Get all detected tables that need VLM extraction."""
        rows = self._conn.execute(
            "SELECT * FROM detected_tables WHERE needs_vlm = 1 ORDER BY page_number"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Summary / stats ──────────────────────────────────────────────

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the master data store."""
        total_pages = self.get_total_pages()
        pages_with_headings = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM pages WHERE detected_heading != ''"
        ).fetchone()["cnt"]
        pages_with_tables = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM pages WHERE has_tables = 1"
        ).fetchone()["cnt"]
        unique_sections = len(self.get_unique_sections())
        taxonomy_count = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM taxonomy_mappings"
        ).fetchone()["cnt"]
        detected_table_count = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM detected_tables"
        ).fetchone()["cnt"]

        return {
            "total_pages": total_pages,
            "pages_with_headings": pages_with_headings,
            "pages_with_tables": pages_with_tables,
            "unique_sections": unique_sections,
            "taxonomy_mappings": taxonomy_count,
            "detected_tables": detected_table_count,
        }

    # ── Lifecycle ────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the SQLite connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def export_to_file(self, output_path: str | Path) -> Path:
        """Export the in-memory database to a file for persistence.

        Only useful when db_path is ':memory:'.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        file_conn = sqlite3.connect(str(output_path))
        self._conn.backup(file_conn)
        file_conn.close()

        logger.info(f"[MasterData] Exported database to {output_path}")
        return output_path

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
