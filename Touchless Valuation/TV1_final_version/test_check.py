"""Comprehensive error check for the valuation platform."""
import sys
import os
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, "backend")

from app import db
from app.engine.model import resolve, load_target
from app.engine.pipeline import evaluate
from app.engine.pipeline_pro import evaluate_pro_by_code

ERRORS = []

def check(label, fn):
    try:
        result = fn()
        print(f"  [PASS] {label}: {result}")
        return result
    except Exception as e:
        ERRORS.append(f"{label}: {e}")
        print(f"  [FAIL] {label}: {e}")
        return None

print("=== DATABASE CHECKS ===")
with db.connect() as conn:
    check("Meta query", lambda: {r["k"]: r["v"] for r in db.query(conn, "SELECT k, v FROM meta")})
    check("Total companies", lambda: db.query_one(conn, "SELECT COUNT(*) c FROM companies")["c"])
    check("Valuation-grade companies", lambda: db.query_one(conn, "SELECT COUNT(*) c FROM companies WHERE valuation_grade=1")["c"])
    check("Grade companies with NULL sector", lambda: db.query_one(conn, "SELECT COUNT(*) c FROM companies WHERE valuation_grade=1 AND sector IS NULL")["c"])
    check("History rows", lambda: db.query_one(conn, "SELECT COUNT(*) c FROM history")["c"])
    check("Distinct sectors", lambda: len(db.query(conn, "SELECT DISTINCT sector FROM companies WHERE sector IS NOT NULL")))
    check("Indexes exist", lambda: [r["name"] for r in db.query(conn, "SELECT name FROM sqlite_master WHERE type='index'")])
    check("Year-end sample", lambda: db.query(conn, "SELECT year_end, COUNT(*) c FROM companies WHERE valuation_grade=1 GROUP BY year_end ORDER BY c DESC LIMIT 3"))

print("\n=== SEARCH CHECKS ===")
with db.connect() as conn:
    check("Search 'Tata'", lambda: len(resolve(conn, "Tata")))
    check("Search 'ICICI'", lambda: len(resolve(conn, "ICICI")))
    check("Search by code '20967'", lambda: resolve(conn, "20967")[0]["name"] if resolve(conn, "20967") else "none")
    check("Search empty string", lambda: len(resolve(conn, "")))

print("\n=== TARGET LOADING ===")
with db.connect() as conn:
    hits = resolve(conn, "ICICI AMC")
    if hits:
        code = hits[0]["code"]
        t = check("Load target ICICI AMC", lambda: load_target(conn, code))
        if t:
            check("Target has sector", lambda: t.sector is not None)
            check("Target has revenue", lambda: t.revenue is not None and t.revenue > 0)
            check("Target has ebitda", lambda: t.ebitda is not None)

print("\n=== BASIC PIPELINE (no history) ===")
with db.connect() as conn:
    hits = resolve(conn, "ICICI AMC")
    if hits:
        code = hits[0]["code"]
        check("Basic valuation", lambda: evaluate(conn, load_target(conn, code), max_peers=8).get("status"))

print("\n=== PRO PIPELINE (with auto-analyst fallback) ===")
with db.connect() as conn:
    hits = resolve(conn, "Reliance")
    if hits:
        code = hits[0]["code"]
        def _pro():
            res = evaluate_pro_by_code(conn, code, max_peers=8)
            return f"status={res['status']}, approaches={len(res.get('approaches',[]))}"
        check("Pro valuation Reliance", _pro)

print("\n=== SCHEMA COMPATIBILITY ===")
with db.connect() as conn:
    row = db.query_one(conn, "SELECT * FROM companies LIMIT 1")
    required = ["code","name","sector","industry","revenue","ebitda","pat","net_worth",
                "total_debt","cash","market_cap","enterprise_value","pe","ev_ebitda",
                "ev_revenue","mktcap_sales","year_end","mode","is_bank","valuation_grade",
                "has_sector","is_current","has_multiple"]
    missing = [c for c in required if c not in row]
    if missing:
        ERRORS.append(f"Missing columns: {missing}")
        print(f"  [FAIL] Missing columns: {missing}")
    else:
        print(f"  [PASS] All {len(required)} required columns present")

print("\n=== FRONTEND FILES CHECK ===")
from pathlib import Path
root = Path(".")
fe = root / "frontend" / "app"
check("layout.tsx exists", lambda: (fe / "layout.tsx").is_file())
check("page.tsx exists", lambda: (fe / "page.tsx").is_file())
check("globals.css exists", lambda: (fe / "globals.css").is_file())
check("Dashboard.tsx exists", lambda: (fe / "components" / "Dashboard.tsx").is_file())
check("types.ts exists", lambda: (fe / ".." / "lib" / "types.ts").is_file())
check("format.ts exists", lambda: (fe / ".." / "lib" / "format.ts").is_file())

# Check for Deloitte branding tokens in CSS
css = (fe / "globals.css").read_text(encoding="utf-8")
check("DDS green token", lambda: "--deloitte-green" in css)
check("Open Sans font", lambda: "Open Sans" in css)
check("DDS header class", lambda: "dds-header" in css)
check("Focus color token", lambda: "--focus-color" in css)

# Check layout has Deloitte header
layout = (fe / "layout.tsx").read_text(encoding="utf-8")
check("Layout has dds-header", lambda: "dds-header" in layout)
check("Layout has Deloitte wordmark", lambda: "Deloitte" in layout)
check("Layout has project name", lambda: "Valuation E-Vardhan" in layout)

print("\n" + "=" * 50)
if ERRORS:
    print(f"[FAIL] {len(ERRORS)} ERROR(S):")
    for e in ERRORS:
        print(f"   - {e}")
else:
    print("[PASS] ALL CHECKS PASSED -- no errors found")
