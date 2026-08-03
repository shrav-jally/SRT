"""
Live market cross-check — fetches the CURRENT market cap / P/E for a listed
company from screener.in, so the valuation can be checked against today's
traded price rather than the database's fiscal-year snapshot.

This is a cross-check, not a valuation input: it tells the user how the
concluded range compares with what the market is paying right now, and how
stale the stored snapshot is. Purely additive — every failure path returns None
and the engine behaves exactly as before.

Polite by construction: one request per company on demand (never bulk), an
in-process cache, a short timeout, and a normal browser User-Agent. Disable
entirely with LIVE_MARKET=0.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from typing import Optional

BASE = "https://www.screener.in"
TIMEOUT = 12
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

_cache: dict[str, Optional[dict]] = {}


def enabled() -> bool:
    return os.environ.get("LIVE_MARKET", "1") not in ("0", "false", "False")


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as f:
        return f.read().decode("utf-8", "ignore")


def _num(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _field(html: str, label: str) -> Optional[float]:
    """Pull a value out of screener's ratio list by its label."""
    m = re.search(label + r'[\s\S]{0,300}?<span class="number">([\d,.]+)</span>',
                  html)
    return _num(m.group(1)) if m else None


def lookup(name: str) -> Optional[dict]:
    """Resolve a company on screener.in and return its current market data."""
    if not enabled() or not name:
        return None
    key = name.strip().lower()
    if key in _cache:
        return _cache[key]
    result = None
    try:
        hits = json.loads(
            _get(f"{BASE}/api/company/search/?q={urllib.parse.quote(name)}"))
        if hits:
            hit = hits[0]
            url = BASE + hit["url"]
            html = _get(url)
            result = {
                "source": "screener.in",
                "matched_name": hit.get("name"),
                "url": url,
                "market_cap_cr": _field(html, "Market Cap"),
                "pe": _field(html, "Stock P/E"),
                "book_value_cr": None,
            }
            if result["market_cap_cr"] is None:
                result = None
    except Exception:
        result = None
    _cache[key] = result
    return result


DRIFT_FILE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "..", "data", "market_drift.json")
DRIFT_MAX_AGE_DAYS = 7


def load_drift() -> Optional[dict]:
    """Cached market-drift factor: how far the stored snapshot sits below
    today's market. None when absent/stale -> engine applies no adjustment."""
    try:
        with open(DRIFT_FILE, encoding="utf-8") as f:
            d = json.load(f)
        from datetime import datetime, timezone
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(d["computed_at"])).days
        d["age_days"] = age
        d["stale"] = age > DRIFT_MAX_AGE_DAYS
        return d
    except Exception:
        return None


def compute_drift(conn, sample: int = 30) -> dict:
    """Measure median(live / stored market cap) over a sample of listed
    companies. >1 means the stored snapshot understates today's market."""
    import random
    import statistics as stats
    from datetime import datetime, timezone
    from .. import db as _db

    rows = _db.query(conn, """SELECT name, market_cap FROM companies
                     WHERE valuation_grade=1 AND market_cap>0 AND name IS NOT NULL""")
    random.Random(7).shuffle(rows)
    ratios = []
    for r in rows:
        if len(ratios) >= sample:
            break
        live = lookup(r["name"])
        if live and live.get("market_cap_cr"):
            ratio = live["market_cap_cr"] / r["market_cap"]
            if 0.2 < ratio < 5:            # ignore mismatched resolutions
                ratios.append(ratio)
    out = {
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n": len(ratios),
        "drift_factor": round(stats.median(ratios), 4) if ratios else 1.0,
        "source": "screener.in",
    }
    os.makedirs(os.path.dirname(DRIFT_FILE), exist_ok=True)
    with open(DRIFT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    return out


def compare(target, concluded_mid: Optional[float]) -> Optional[dict]:
    """Add the live figure plus deltas vs the concluded value and the stored snapshot."""
    live = lookup(target.name)
    if not live:
        return None
    live_mc = live["market_cap_cr"]
    out = dict(live)
    if concluded_mid and concluded_mid > 0 and live_mc:
        out["vs_conclusion_pct"] = round(100 * (concluded_mid / live_mc - 1), 1)
    if target.market_cap and live_mc:
        out["stored_market_cap_cr"] = round(target.market_cap, 2)
        out["snapshot_staleness_pct"] = round(
            100 * (target.market_cap / live_mc - 1), 1)
    return out


if __name__ == "__main__":
    # Refresh the market-drift factor:  python -m app.engine.live_market
    from .. import db as _db
    with _db.connect() as _c:
        print(compute_drift(_c))
