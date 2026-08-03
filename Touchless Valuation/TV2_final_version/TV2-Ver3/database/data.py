"""
database/data.py - comparable-company dataset + Sector -> Industry taxonomy for the
CCM valuation tool (v2).

DATA SOURCE (v2): the exhaustive Capitaline (Cline) extracts, compiled
into database/comps_v2.db - 3,700+ valuation-grade listed companies
across 80+ sectors and ~290 industries.

Uses raw sqlite3 from the Python standard library — no ORM.
"""

import os
import sqlite3

_HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(_HERE, "comps_v2.db")

AS_OF = ("Capitaline (Cline) extracts - published market multiples + latest "
         "audited financials")
MULTIPLE_SOURCE = ("Capitaline database published ratios (P/E, EV/EBITDA) used "
                   "directly; EV/Revenue = published Enterprise Value / Net Sales.")

_CACHE = {"comps": None, "meta": None}

# ---------------------------------------------------------------------------
# Fallback curated list (used only when comps_v2.db is missing)
# ---------------------------------------------------------------------------
_FALLBACK = [
    {"name": "Kirloskar Brothers Ltd.", "sector": "Industrials",
     "sub_sector": "Pumps & Compressors", "revenue": 2901.0, "ebitda": 359.0,
     "pat": 262.0, "net_worth": 1663.0, "market_cap": 14580.0,
     "ev_ebitda": 22.20, "pe": 37.0},
    {"name": "KSB Ltd.", "sector": "Industrials",
     "sub_sector": "Pumps & Compressors", "revenue": 2696.0, "ebitda": 374.0,
     "pat": 264.0, "net_worth": 1613.0, "market_cap": 14520.0,
     "ev_ebitda": 42.75, "pe": 55.0},
    {"name": "Shakti Pumps (India) Ltd.", "sector": "Industrials",
     "sub_sector": "Pumps & Compressors", "revenue": 2479.0, "ebitda": 561.0,
     "pat": 394.0, "net_worth": 1061.0, "market_cap": 7080.0,
     "ev_ebitda": 13.14, "pe": 20.0},
]


def _finalise(rec):
    """Attach derived ratio fields to a comparable (no new data)."""
    rec = dict(rec)
    if rec.get("sub_sector"):
        rec["sub_sector"] = rec["sub_sector"].strip()
    if rec.get("sector"):
        rec["sector"] = rec["sector"].strip()
    if rec.get("name"):
        rec["name"] = rec["name"].strip()
    rev, eb, pat = rec.get("revenue"), rec.get("ebitda"), rec.get("pat")
    rec["ebitda_margin"] = round(eb / rev, 4) if (rev and eb is not None) else None
    rec["pat_margin"] = round(pat / rev, 4) if (rev and pat is not None) else None
    if rec.get("ev_revenue") is None and rec.get("ev_ebitda") is not None and rev and eb:
        rec["ev_revenue"] = round(rec["ev_ebitda"] * eb / rev, 3)
        rec["ev_rev_derived"] = True
    else:
        rec.setdefault("ev_rev_derived", False)
    return rec


def _load_from_db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT name, sector, industry AS sub_sector, revenue, ebitda, pat, "
        "net_worth, total_debt, net_debt, cash, market_cap, enterprise_value, "
        "pe, ev_ebitda, ev_revenue, mktcap_sales, mode FROM comps").fetchall()
    meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
    con.close()
    return [_finalise(dict(r)) for r in rows], meta


def load_comparables():
    """Finalised comparable list. Cached. Reads comps_v2.db when present."""
    if _CACHE["comps"] is None:
        if os.path.exists(DB):
            _CACHE["comps"], _CACHE["meta"] = _load_from_db()
        else:
            _CACHE["comps"] = [_finalise(r) for r in _FALLBACK]
            _CACHE["meta"] = {"source": "fallback"}
    return _CACHE["comps"]


def reset_cache():
    """Clear the in-memory cache. Call this when the DB is rebuilt."""
    _CACHE["comps"] = None
    _CACHE["meta"] = None


def dataset_meta():
    load_comparables()
    m = dict(_CACHE["meta"] or {})
    m["db_present"] = os.path.exists(DB)
    m["n_comparables"] = len(_CACHE["comps"])
    return m


def sectors_with_availability(min_comps=1):
    """Real Sector -> Industry taxonomy with a comparable count per industry."""
    comps = load_comparables()
    by_sector = {}
    for c in comps:
        sec = c.get("sector") or "Unclassified"
        ind = c.get("sub_sector") or "Unclassified"
        by_sector.setdefault(sec, {}).setdefault(ind, 0)
        by_sector[sec][ind] += 1
    out = []
    for sec in sorted(by_sector):
        subs = sorted(by_sector[sec].items(), key=lambda kv: (-kv[1], kv[0]))
        out.append({
            "sector": sec,
            "sub_sectors": [
                {"name": ind, "available": n >= min_comps, "comparable_count": n}
                for ind, n in subs],
        })
    out.sort(key=lambda s: -sum(x["comparable_count"] for x in s["sub_sectors"]))
    return out
