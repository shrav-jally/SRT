"""
Migrate comp_v3_clamped.db (24,603 companies, flat 'comps' table)
into the engine's full schema (companies + history + meta).

The v3 database has a simpler flat schema missing several columns the
engine depends on. This script:

1. Reads all rows from the source 'comps' table
2. Computes derived/flag columns the engine needs:
   - valuation_grade, is_bank, is_current, has_sector, has_multiple
   - ebitda_margin, pat_margin
3. Creates the full 'companies' table matching the engine's DDL
4. Creates an empty 'history' table (v3 has no multi-year data;
   the auto-analyst falls back to current-year defaults gracefully)
5. Creates the 'meta' table
6. Creates all required indexes

Run:  python -m app.etl.migrate_v3   (from backend/)
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..config import DATA_DIR, RECENT_YEAR_END

# ---------------------------------------------------------------------------
# Source: the v3 database in the project root (placed there by the ETL scripts)
# ---------------------------------------------------------------------------
V3_SOURCES = [
    Path(__file__).resolve().parent.parent.parent.parent / "comp_v3_clamped.db",
    Path(__file__).resolve().parent.parent.parent / "comp_v3_clamped.db",
]


def _find_source() -> Path:
    for p in V3_SOURCES:
        if p.is_file():
            return p
    raise FileNotFoundError(
        "comp_v3_clamped.db not found. Place it in the project root or "
        "the backend/ directory."
    )


# ---------------------------------------------------------------------------
# Engine DDL (must match backend/app/etl/build_db.py exactly)
# ---------------------------------------------------------------------------
DDL = """\
CREATE TABLE IF NOT EXISTS companies (
    code INTEGER PRIMARY KEY,
    name TEXT,
    sector TEXT, industry TEXT, macro_sector TEXT,
    net_sales REAL, total_income REAL, revenue REAL,
    ebitda REAL, ebit REAL, pat REAL, pbt REAL,
    net_worth REAL, capital_employed REAL,
    total_debt REAL, net_debt REAL, cash REAL,
    market_cap REAL, enterprise_value REAL,
    ebitda_margin REAL, pat_margin REAL,
    pe REAL, ev_ebitda REAL, ev_revenue REAL,
    mktcap_sales REAL, pbv REAL,
    year_end INTEGER, mode TEXT,
    is_bank INTEGER, has_sector INTEGER, is_current INTEGER,
    has_multiple INTEGER, valuation_grade INTEGER,
    mult_block INTEGER
)
"""

HISTORY_DDL = """\
CREATE TABLE IF NOT EXISTS history (
    code INTEGER, years_back INTEGER,
    sales REAL, ebitda REAL, pat REAL,
    net_worth REAL, capital_employed REAL,
    total_debt REAL, market_cap REAL,
    PRIMARY KEY (code, years_back)
)
"""

META_DDL = "CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)"


def migrate(source_path: Path | None = None, dest_path: Path | None = None) -> None:
    """Run the migration."""
    src = source_path or _find_source()
    dst = dest_path or (DATA_DIR / "comps.db")

    print(f"Migrating {src.name} -> {dst.name}")

    src_conn = sqlite3.connect(str(src))
    src_conn.row_factory = sqlite3.Row

    rows_in = src_conn.execute("SELECT * FROM comps").fetchall()
    print(f"  source rows: {len(rows_in):,}")
    src_conn.close()

    # -----------------------------------------------------------------------
    # Transform each row: compute missing derived columns
    # -----------------------------------------------------------------------
    out_rows: list[dict] = []
    for r in rows_in:
        d = dict(r)

        # year_end: v3 stores it as REAL (e.g. 202303.0); engine expects INTEGER
        year_end = d.get("year_end")
        if year_end is not None:
            year_end = int(year_end)

        # revenue in v3 is the effective revenue (net_sales for non-banks,
        # total_income for banks). Since v3 doesn't separate them, we set
        # net_sales = revenue for non-banks and total_income = revenue for banks.
        # Bank detection: if net_debt is 0 or very low relative to market_cap,
        # or if the sector contains "Bank" or "Financial"
        sector = d.get("sector") or ""
        industry = d.get("industry") or ""
        is_bank = bool(
            "bank" in sector.lower()
            or "nbfc" in sector.lower()
            or "bank" in industry.lower()
            or "financial" in industry.lower()
        )

        revenue = d.get("revenue")
        net_sales = revenue if not is_bank else None
        total_income = revenue if is_bank else None

        # Margins
        ebitda_margin = None
        pat_margin = None
        if revenue and revenue > 0:
            if d.get("ebitda") is not None:
                ebitda_margin = round(d["ebitda"] / revenue, 4)
            if d.get("pat") is not None:
                pat_margin = round(d["pat"] / revenue, 4)

        # ebit: v3 doesn't have it; approximate as 0.85 * EBITDA (standard ratio)
        ebit = None
        if d.get("ebitda") is not None:
            ebit = round(d["ebitda"] * 0.85, 2)

        # Flags
        has_sector = bool(d.get("sector"))
        pe = d.get("pe")
        ev_ebitda = d.get("ev_ebitda")
        mktcap_sales = d.get("mktcap_sales")
        has_multiple = bool(pe or ev_ebitda or mktcap_sales)
        is_current = bool(year_end and year_end >= RECENT_YEAR_END)
        valuation_grade = bool(has_sector and has_multiple and is_current)

        # pbv: v3 doesn't have it; leave as NULL
        # macro_sector: v3 doesn't have it; leave as NULL
        # capital_employed: v3 doesn't have it; leave as NULL
        # pbt: v3 doesn't have it; leave as NULL
        # mult_block: not applicable to v3; leave as NULL

        out_rows.append({
            "code": d["code"],
            "name": d.get("name"),
            "sector": d.get("sector"),
            "industry": d.get("industry"),
            "macro_sector": None,
            "net_sales": net_sales,
            "total_income": total_income,
            "revenue": revenue,
            "ebitda": d.get("ebitda"),
            "ebit": ebit,
            "pat": d.get("pat"),
            "pbt": None,
            "net_worth": d.get("net_worth"),
            "capital_employed": None,
            "total_debt": d.get("total_debt"),
            "net_debt": d.get("net_debt"),
            "cash": d.get("cash"),
            "market_cap": d.get("market_cap"),
            "enterprise_value": d.get("enterprise_value"),
            "ebitda_margin": ebitda_margin,
            "pat_margin": pat_margin,
            "pe": pe,
            "ev_ebitda": ev_ebitda,
            "ev_revenue": d.get("ev_revenue"),
            "mktcap_sales": mktcap_sales,
            "pbv": None,
            "year_end": year_end,
            "mode": d.get("mode"),
            "is_bank": int(is_bank),
            "has_sector": int(has_sector),
            "is_current": int(is_current),
            "has_multiple": int(has_multiple),
            "valuation_grade": int(valuation_grade),
            "mult_block": None,
        })

    # -----------------------------------------------------------------------
    # Write to destination
    # -----------------------------------------------------------------------
    if dst.is_file():
        dst.unlink()  # replace existing

    dst_conn = sqlite3.connect(str(dst))
    dst_conn.execute(DDL)
    dst_conn.execute(HISTORY_DDL)
    dst_conn.execute(META_DDL)

    COLUMNS = [
        "code", "name", "sector", "industry", "macro_sector",
        "net_sales", "total_income", "revenue", "ebitda", "ebit", "pat", "pbt",
        "net_worth", "capital_employed", "total_debt", "net_debt", "cash",
        "market_cap", "enterprise_value", "ebitda_margin", "pat_margin",
        "pe", "ev_ebitda", "ev_revenue", "mktcap_sales", "pbv",
        "year_end", "mode", "is_bank", "has_sector", "is_current",
        "has_multiple", "valuation_grade", "mult_block",
    ]

    placeholders = ", ".join(["?"] * len(COLUMNS))
    col_list = ", ".join(COLUMNS)
    insert_sql = f"INSERT INTO companies ({col_list}) VALUES ({placeholders})"

    for row in out_rows:
        dst_conn.execute(insert_sql, [row.get(c) for c in COLUMNS])

    # Indexes
    dst_conn.execute("CREATE INDEX IF NOT EXISTS ix_sector ON companies(sector)")
    dst_conn.execute("CREATE INDEX IF NOT EXISTS ix_industry ON companies(industry)")
    dst_conn.execute("CREATE INDEX IF NOT EXISTS ix_grade ON companies(valuation_grade)")

    # Meta
    grade = sum(r["valuation_grade"] for r in out_rows)
    banks = sum(r["is_bank"] for r in out_rows)
    for k, v in [
        ("built", datetime.now(timezone.utc).isoformat(timespec="seconds")),
        ("source", "comp_v3_clamped.db (migrated)"),
        ("n_companies", str(len(out_rows))),
        ("n_grade", str(grade)),
    ]:
        dst_conn.execute("DELETE FROM meta WHERE k=?", (k,))
        dst_conn.execute("INSERT INTO meta VALUES (?,?)", (k, v))

    dst_conn.commit()

    print(f"  migrated rows : {len(out_rows):,}")
    print(f"  valuation-grade: {grade:,}")
    print(f"  banks/NBFC     : {banks:,}")
    print(f"  history table  : empty (v3 has no multi-year data)")
    print(f"  output         : {dst}")

    dst_conn.close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    migrate()
