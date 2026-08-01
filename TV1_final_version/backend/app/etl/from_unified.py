"""
Adapter ETL: unified_tv1_tv2.db (user-curated, 20,143 usable companies)
-> the engine's `companies` + `history` schema. The engine is untouched.

Why not use the unified `comps` view directly: its "latest period" CTE takes
MAX(period_rank), but ranks are newest-first (0 = current), so the view serves
~6-year-old multiples (ACC: 8.3x from FY20 instead of the current 6.79x). We
read `valuation_ratios` ourselves at rank 0, falling back to later ranks only
when the current value is missing/zero.

The unified DB carries only the LATEST fiscal year of financials, so the
7-year financial history (needed by the auto-analyst for CAGR / normalized
margins) is preserved from the existing comps.db where the accord codes match.

Run:  python -m app.etl.from_unified          (from backend/)
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..config import DATA_DIR, RECENT_YEAR_END
from .. import db
from .build_db import COLUMNS, DDL, HISTORY_COLUMNS, HISTORY_DDL

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent.parent.parent   # valuation-platform/
UNIFIED = ROOT / "unified_tv1_tv2.db"


def _nz(v):
    """0 == not-reported in this source for metric fields."""
    return None if (v is None or v == 0) else v


def _ratio_current(rows: list[tuple]) -> dict:
    """rows = [(period_rank, pe, pbv, ev_ebitda, mcap_sales, mode)] sorted by
    rank. First positive value per metric, preferring the current rank 0."""
    out = {"pe": None, "pbv": None, "ev_ebitda": None, "mktcap_sales": None,
           "mode": None, "mult_block": None}
    for rank, pe, pbv, eve, ms, mode in rows:
        if out["pe"] is None and pe and pe > 0:
            out["pe"] = pe
            out["mult_block"] = rank if out["mult_block"] is None else out["mult_block"]
        if out["pbv"] is None and pbv and pbv > 0:
            out["pbv"] = pbv
        if out["ev_ebitda"] is None and eve and eve > 0:
            out["ev_ebitda"] = eve
        if out["mktcap_sales"] is None and ms and ms > 0:
            out["mktcap_sales"] = ms
        if out["mode"] is None and mode:
            out["mode"] = mode
    return out


def build() -> None:
    if not UNIFIED.is_file():
        sys.exit(f"unified DB not found: {UNIFIED}")
    src = sqlite3.connect(str(UNIFIED))
    src.row_factory = sqlite3.Row

    # ---- preserve financial history from the current comps.db (same codes)
    old_history: list[tuple] = []
    old_db = DATA_DIR / "comps.db"
    if old_db.is_file():
        oc = sqlite3.connect(str(old_db))
        try:
            old_history = oc.execute(
                f"SELECT {','.join(HISTORY_COLUMNS)} FROM history").fetchall()
        except sqlite3.OperationalError:
            pass
        oc.close()
    print(f"history rows carried over: {len(old_history)}")

    # ---- ratios per company, rank-ordered (0 = current)
    ratios: dict[int, list] = {}
    for r in src.execute(
            """SELECT accord, period_rank, pe, pbv, ev_ebitda, mcap_sales, mode
               FROM valuation_ratios ORDER BY accord, period_rank"""):
        ratios.setdefault(r["accord"], []).append(
            (r["period_rank"], r["pe"], r["pbv"], r["ev_ebitda"],
             r["mcap_sales"], r["mode"]))

    rows = []
    q = """SELECT c.accord, c.name, c.sector, c.industry, c.macro_sector,
                  f.year_end, f.revenue, f.ebitda, f.pbit, f.pat, f.pbt,
                  f.net_worth, f.capital_employed, f.total_debt, f.net_debt,
                  f.market_cap, f.market_ev, f.interest_earned, f.total_income,
                  f.listed, cb.cash_bank
           FROM companies c
           JOIN fin f ON f.accord = c.accord
           LEFT JOIN cash_bank cb ON cb.accord = c.accord"""
    for r in src.execute(q):
        code = r["accord"]
        net_sales = _nz(r["revenue"])
        total_income = _nz(r["total_income"])
        interest_earned = _nz(r["interest_earned"])
        revenue = net_sales if net_sales is not None else total_income
        ebitda = _nz(r["ebitda"])
        ebit = _nz(r["pbit"])
        pat = r["pat"]
        ev = _nz(r["market_ev"])
        market_cap = _nz(r["market_cap"])
        year_end = int(r["year_end"]) if r["year_end"] else None

        rat = _ratio_current(ratios.get(code, []))
        ev_revenue = round(ev / net_sales, 4) if (ev and net_sales) else None
        is_bank = bool(net_sales is None and (total_income or interest_earned))
        has_sector = bool(r["sector"])
        has_multiple = bool(rat["pe"] or rat["ev_ebitda"] or rat["mktcap_sales"])
        is_current = bool(year_end and year_end >= RECENT_YEAR_END)
        grade = bool(has_sector and has_multiple and is_current)

        rows.append({
            "code": code, "name": r["name"] or "",
            "sector": r["sector"], "industry": r["industry"],
            "macro_sector": r["macro_sector"],
            "net_sales": net_sales, "total_income": total_income,
            "revenue": revenue, "ebitda": ebitda, "ebit": ebit,
            "pat": pat, "pbt": r["pbt"], "net_worth": _nz(r["net_worth"]),
            "capital_employed": _nz(r["capital_employed"]),
            "total_debt": r["total_debt"], "net_debt": r["net_debt"],
            "cash": r["cash_bank"], "market_cap": market_cap,
            "enterprise_value": ev,
            "ebitda_margin": round(ebitda / revenue, 4) if (ebitda is not None and revenue) else None,
            "pat_margin": round(pat / revenue, 4) if (pat is not None and revenue) else None,
            "pe": rat["pe"], "ev_ebitda": rat["ev_ebitda"],
            "ev_revenue": ev_revenue, "mktcap_sales": rat["mktcap_sales"],
            "pbv": rat["pbv"], "year_end": year_end, "mode": rat["mode"],
            "is_bank": int(is_bank), "has_sector": int(has_sector),
            "is_current": int(is_current), "has_multiple": int(has_multiple),
            "valuation_grade": int(grade), "mult_block": rat["mult_block"],
        })
    src.close()

    codes = {r["code"] for r in rows}
    kept_history = [h for h in old_history if h[0] in codes]

    placeholders = ",".join(["?"] * len(COLUMNS))
    insert = f"INSERT INTO companies ({','.join(COLUMNS)}) VALUES ({placeholders})"
    h_ins = f"INSERT INTO history ({','.join(HISTORY_COLUMNS)}) VALUES ({','.join(['?']*len(HISTORY_COLUMNS))})"
    with db.connect() as conn:
        db.execute(conn, "DROP TABLE IF EXISTS companies")
        db.execute(conn, DDL)
        db.executemany(conn, insert, ([r[c] for c in COLUMNS] for r in rows))
        db.execute(conn, "DROP TABLE IF EXISTS history")
        db.execute(conn, HISTORY_DDL)
        db.executemany(conn, h_ins, kept_history)
        db.execute(conn, "CREATE INDEX ix_sector ON companies(sector)")
        db.execute(conn, "CREATE INDEX ix_industry ON companies(industry)")
        db.execute(conn, "CREATE INDEX ix_grade ON companies(valuation_grade)")
        db.execute(conn, f"CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
        for k, v in [("built", datetime.now(timezone.utc).isoformat(timespec="seconds")),
                     ("source", "unified_tv1_tv2.db"),
                     ("n_companies", str(len(rows))),
                     ("n_grade", str(sum(r["valuation_grade"] for r in rows)))]:
            db.execute(conn, "DELETE FROM meta WHERE k=?", (k,))
            db.execute(conn, "INSERT INTO meta (k, v) VALUES (?, ?)", (k, v))

    grade = sum(r["valuation_grade"] for r in rows)
    banks = sum(r["is_bank"] for r in rows)
    print(f"companies stored : {len(rows):>6}  (from unified_tv1_tv2.db)")
    print(f"valuation-grade  : {grade:>6}   banks/NBFC: {banks}")
    print(f"history retained : {len(kept_history):>6} rows")


if __name__ == "__main__":
    build()
