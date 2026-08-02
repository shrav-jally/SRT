"""
Maximal-coverage ETL: five Capitaline .xls extracts -> one `companies` table.

Design goals (these are the whole point of the rebuild):
  * NEVER inner-join. The universe is the UNION of company codes across all
    files. A company missing from one file is kept with blanks, not dropped.
    (The old etl used `set(basic) & set(fin) & set(rat)` and lost ~2/3 of rows.)
  * 0 means "not applicable / not reported" in this sector-tagged source, so 0
    is stored as NULL for metrics/drivers — a bank's Net Sales of 0 does not
    disqualify it; it is priced on the fields it does report.
  * Published multiples are used as-is ("as per Cline"), never recomputed. For
    each metric we take the current snapshot (block 0), falling back to a later
    block only when the current cell is 0.

Run:  python -m app.etl.build_db
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import xlrd

from ..config import RECENT_YEAR_END, SOURCE_DIR, ZERO_IS_NULL_FIELDS
from .. import db
from . import columns as C

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# --------------------------------------------------------------- helpers
def _num(x):
    try:
        v = float(x)
        return v if v == v else None      # drop NaN
    except (TypeError, ValueError):
        return None


def _code(raw):
    """Capitaline codes are numeric. Non-numeric rows (footer 'Source:' and the
    licence disclaimer that trail every extract) return None and are skipped."""
    if isinstance(raw, (int, float)):
        return int(raw)
    return None


def _open(fname):
    wb = xlrd.open_workbook(str(SOURCE_DIR / fname), on_demand=True)
    return wb, wb.sheet_by_index(0)


def _zap_zero(field: str, value):
    """Apply the 0-is-NULL rule for metric/driver fields only."""
    if value is None:
        return None
    if field in ZERO_IS_NULL_FIELDS and value == 0:
        return None
    return value


def read_basic() -> dict:
    wb, sh = _open(C.BASIC_FILE)
    out = {}
    for r in range(1, sh.nrows):
        code = _code(sh.cell_value(r, 0))
        if code is None:
            continue
        rec = {"co_name": str(sh.cell_value(r, 1)).strip()}
        for k, c in C.BASIC.items():
            v = str(sh.cell_value(r, c)).strip()
            rec[k] = v or None
        out[code] = rec
    wb.release_resources()
    return out


def read_finance() -> tuple[dict, list]:
    """Returns (latest snapshot per code, history rows). History = 7 annual
    periods newest-first, long format: one row per (code, years_back)."""
    wb, sh = _open(C.FINANCE_FILE)
    out = {}
    history = []
    hist_fields = list(C.FINANCE_HISTORY.keys())
    for r in range(1, sh.nrows):
        code = _code(sh.cell_value(r, 0))
        if code is None:
            continue
        rec = {"co_name": str(sh.cell_value(r, 1)).strip()}
        for k, c in C.FINANCE.items():
            rec[k] = _zap_zero(k, _num(sh.cell_value(r, c)))
        out[code] = rec
        for t in range(C.N_HISTORY):
            row = {"code": code, "years_back": t}
            any_val = False
            for f in hist_fields:
                col = C.FINANCE_HISTORY[f][t]
                v = _num(sh.cell_value(r, col)) if col is not None else None
                if v == 0:
                    v = None          # 0 == not reported in this source
                row[f] = v
                any_val = any_val or (v is not None)
            if any_val:
                history.append(row)
    wb.release_resources()
    return out, history


def _pick_block(sh, r, cols, positive=True):
    """First usable value across the 7 snapshot blocks (current preferred)."""
    for i, c in enumerate(cols):
        v = _num(sh.cell_value(r, c))
        if v is None:
            continue
        if positive and v <= 0:
            continue
        return v, i
    return None, None


def read_ratios() -> dict:
    wb, sh = _open(C.RATIOS_FILE)
    blk = C.RATIO_BLOCKS
    out = {}
    for r in range(1, sh.nrows):
        code = _code(sh.cell_value(r, 0))
        if code is None:
            continue
        pe, blk_i = _pick_block(sh, r, blk["pe"])
        ev_ebitda, _ = _pick_block(sh, r, blk["ev_ebitda"])
        mktcap_sales, _ = _pick_block(sh, r, blk["mktcap_sales"])
        pbv, _ = _pick_block(sh, r, blk["pbv"])
        year_end = _num(sh.cell_value(r, blk["year_end"][0]))
        # mode from the block that supplied the P/E (else block 0)
        mi = blk_i if blk_i is not None else 0
        mode = str(sh.cell_value(r, blk["mode"][mi])).strip() or None
        out[code] = {
            "co_name": str(sh.cell_value(r, 1)).strip(),
            "pe": pe, "ev_ebitda": ev_ebitda, "mktcap_sales": mktcap_sales,
            "pbv": pbv, "year_end": int(year_end) if year_end else None,
            "mode": mode, "mult_block": blk_i,
        }
    wb.release_resources()
    return out


def read_cash() -> dict:
    wb, sh = _open(C.CASH_FILE)
    out = {}
    for r in range(1, sh.nrows):
        code = _code(sh.cell_value(r, 0))
        if code is None:
            continue
        out[code] = _num(sh.cell_value(r, C.CASH["cash"]))
    wb.release_resources()
    return out


# --------------------------------------------------------------- assemble
def _safe_div(a, b):
    return round(a / b, 4) if (a is not None and b) else None


def assemble(basic, fin, rat, cash) -> list[dict]:
    universe = set(basic) | set(fin) | set(rat) | set(cash)
    rows = []
    for code in universe:
        b = basic.get(code, {})
        f = fin.get(code, {})
        v = rat.get(code, {})
        name = b.get("long_name") or f.get("co_name") or v.get("co_name") or ""

        net_sales = f.get("net_sales")
        total_income = f.get("total_income")
        interest_earned = f.get("interest_earned")
        is_bank = bool((net_sales is None) and (total_income or interest_earned))
        # Effective revenue: real Net Sales, else bank Total Income.
        revenue = net_sales if net_sales is not None else total_income

        ebitda = f.get("ebitda")
        pat = f.get("pat")
        ev = f.get("enterprise_value")
        market_cap = f.get("market_cap")

        ebitda_margin = _safe_div(ebitda, revenue)
        pat_margin = _safe_div(pat, revenue)
        ev_revenue = _safe_div(ev, net_sales)      # only where real sales exist

        pe = v.get("pe")
        ev_ebitda = v.get("ev_ebitda")
        mktcap_sales = v.get("mktcap_sales")
        year_end = v.get("year_end")

        has_sector = bool(b.get("sector"))
        has_multiple = bool(pe or ev_ebitda or mktcap_sales)
        is_current = bool(year_end and year_end >= RECENT_YEAR_END)
        # A company is usable AS A PEER when it can be matched (sector) and priced
        # off a current published multiple. Its own market cap is not required —
        # that only feeds the target's optional market cross-check.
        valuation_grade = bool(has_sector and has_multiple and is_current)

        rows.append({
            "code": code, "name": name,
            "sector": b.get("sector"), "industry": b.get("industry"),
            "macro_sector": b.get("macro_sector"),
            "net_sales": net_sales, "total_income": total_income,
            "revenue": revenue, "ebitda": ebitda, "ebit": f.get("ebit"),
            "pat": pat, "pbt": f.get("pbt"),
            "net_worth": f.get("net_worth"),
            "capital_employed": f.get("capital_employed"),
            "total_debt": f.get("total_debt"), "net_debt": f.get("net_debt"),
            "cash": cash.get(code), "market_cap": market_cap,
            "enterprise_value": ev,
            "ebitda_margin": ebitda_margin, "pat_margin": pat_margin,
            "pe": pe, "ev_ebitda": ev_ebitda, "ev_revenue": ev_revenue,
            "mktcap_sales": mktcap_sales, "pbv": v.get("pbv"),
            "year_end": year_end, "mode": v.get("mode"),
            "is_bank": int(is_bank), "has_sector": int(has_sector),
            "is_current": int(is_current), "has_multiple": int(has_multiple),
            "valuation_grade": int(valuation_grade),
            "mult_block": v.get("mult_block"),
        })
    return rows


COLUMNS = [
    "code", "name", "sector", "industry", "macro_sector",
    "net_sales", "total_income", "revenue", "ebitda", "ebit", "pat", "pbt",
    "net_worth", "capital_employed", "total_debt", "net_debt", "cash",
    "market_cap", "enterprise_value", "ebitda_margin", "pat_margin",
    "pe", "ev_ebitda", "ev_revenue", "mktcap_sales", "pbv",
    "year_end", "mode", "is_bank", "has_sector", "is_current",
    "has_multiple", "valuation_grade", "mult_block",
]

DDL = f"""
CREATE TABLE companies (
    code INTEGER PRIMARY KEY,
    name {db.TEXT},
    sector {db.TEXT}, industry {db.TEXT}, macro_sector {db.TEXT},
    net_sales {db.REAL}, total_income {db.REAL}, revenue {db.REAL},
    ebitda {db.REAL}, ebit {db.REAL}, pat {db.REAL}, pbt {db.REAL},
    net_worth {db.REAL}, capital_employed {db.REAL},
    total_debt {db.REAL}, net_debt {db.REAL}, cash {db.REAL},
    market_cap {db.REAL}, enterprise_value {db.REAL},
    ebitda_margin {db.REAL}, pat_margin {db.REAL},
    pe {db.REAL}, ev_ebitda {db.REAL}, ev_revenue {db.REAL},
    mktcap_sales {db.REAL}, pbv {db.REAL},
    year_end {db.INT}, mode {db.TEXT},
    is_bank {db.BOOL}, has_sector {db.BOOL}, is_current {db.BOOL},
    has_multiple {db.BOOL}, valuation_grade {db.BOOL},
    mult_block {db.INT}
)
"""


HISTORY_COLUMNS = ["code", "years_back", "sales", "ebitda", "pat",
                   "net_worth", "capital_employed", "total_debt", "market_cap"]

HISTORY_DDL = f"""
CREATE TABLE history (
    code INTEGER, years_back INTEGER,
    sales {db.REAL}, ebitda {db.REAL}, pat {db.REAL},
    net_worth {db.REAL}, capital_employed {db.REAL},
    total_debt {db.REAL}, market_cap {db.REAL},
    PRIMARY KEY (code, years_back)
)
"""


def write_db(rows: list[dict], history: list[dict]) -> None:
    placeholders = ",".join(["?"] * len(COLUMNS))
    insert = f"INSERT INTO companies ({','.join(COLUMNS)}) VALUES ({placeholders})"
    h_placeholders = ",".join(["?"] * len(HISTORY_COLUMNS))
    h_insert = f"INSERT INTO history ({','.join(HISTORY_COLUMNS)}) VALUES ({h_placeholders})"
    with db.connect() as conn:
        db.execute(conn, "DROP TABLE IF EXISTS companies")
        db.execute(conn, DDL)
        db.executemany(conn, insert, ([r[c] for c in COLUMNS] for r in rows))
        db.execute(conn, "DROP TABLE IF EXISTS history")
        db.execute(conn, HISTORY_DDL)
        db.executemany(conn, h_insert, ([h[c] for c in HISTORY_COLUMNS] for h in history))
        db.execute(conn, "CREATE INDEX ix_sector ON companies(sector)")
        db.execute(conn, "CREATE INDEX ix_industry ON companies(industry)")
        db.execute(conn, "CREATE INDEX ix_grade ON companies(valuation_grade)")
        db.execute(conn, f"CREATE TABLE IF NOT EXISTS meta (k {db.TEXT} PRIMARY KEY, v {db.TEXT})")
        for k, val in [
            ("built", datetime.now(timezone.utc).isoformat(timespec="seconds")),
            ("n_companies", str(len(rows))),
            ("n_grade", str(sum(r["valuation_grade"] for r in rows))),
        ]:
            db.execute(conn, "DELETE FROM meta WHERE k=?", (k,))
            db.execute(conn, "INSERT INTO meta (k, v) VALUES (?, ?)", (k, val))


def build() -> None:
    print(f"source: {SOURCE_DIR}")
    basic = read_basic();  print(f"  basic   {len(basic):>6}")
    fin, history = read_finance()
    print(f"  finance {len(fin):>6}  (history rows {len(history)})")
    rat = read_ratios();   print(f"  ratios  {len(rat):>6}")
    cash = read_cash();    print(f"  cash    {len(cash):>6}")

    rows = assemble(basic, fin, rat, cash)
    write_db(rows, history)

    grade = sum(r["valuation_grade"] for r in rows)
    banks = sum(r["is_bank"] for r in rows)
    grade_banks = sum(r["valuation_grade"] and r["is_bank"] for r in rows)
    print(f"\nUNIVERSE stored : {len(rows):>6}  (union, blanks kept)")
    print(f"valuation-grade : {grade:>6}  (sector + current + published multiple + mkt cap)")
    print(f"  incl. banks   : {grade_banks:>6}  (of {banks} banks/NBFCs total)")
    print(f"target DB       : {'PostgreSQL' if db.IS_POSTGRES else 'SQLite'}")


if __name__ == "__main__":
    build()
