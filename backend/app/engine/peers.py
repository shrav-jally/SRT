"""
Peer discovery — V1's selection rigor applied to REAL published multiples.

Strategy: prefer the tightest set (same sub-sector / industry). Only widen to
the whole sector if the sub-sector cannot field enough comps. Every candidate
is scored on sub-sector match, size proximity and margin proximity, ranked, and
the top 5-10 are returned with human-readable reasons and differences.
"""
from __future__ import annotations

import math
from typing import Optional

from .. import db
from .model import Target

# similarity weights (sum to 1.0) — industry & size dominate for tight comps
W_INDUSTRY = 0.50
W_SIZE = 0.30
W_MARGIN = 0.20

DEFAULT_MAX_PEERS = 8
MIN_PEERS = 5


def _log10(x: Optional[float]) -> Optional[float]:
    return math.log10(x) if (x and x > 0) else None


def _size_sim(rt: Optional[float], rp: Optional[float]) -> float:
    a, b = _log10(rt), _log10(rp)
    if a is None or b is None:
        return 0.5
    return 1.0 / (1.0 + abs(a - b))


def _margin_sim(mt: Optional[float], mp: Optional[float]) -> float:
    if mt is None or mp is None:
        return 0.5
    return max(0.0, 1.0 - 3.0 * abs(mt - mp))


def _score(target: Target, cand: dict) -> tuple[float, float]:
    same_ind = bool(target.industry and cand.get("industry") == target.industry)
    industry_sim = 1.0 if same_ind else 0.5
    size_sim = _size_sim(target.revenue, cand.get("revenue"))
    cand_margin = (cand.get("ebitda") / cand["revenue"]) if (cand.get("ebitda") is not None and cand.get("revenue")) else None
    margin_sim = _margin_sim(target.ebitda_margin, cand_margin)
    score = W_INDUSTRY * industry_sim + W_SIZE * size_sim + W_MARGIN * margin_sim
    return round(score, 4), industry_sim


def _reasons(target: Target, cand: dict, industry_sim: float) -> tuple[list, list]:
    because, diffs = [], []
    if industry_sim == 1.0:
        because.append(f"same sub-sector ({cand.get('industry')})")
    else:
        because.append(f"same sector ({cand.get('sector')})")
        if cand.get("industry") != target.industry:
            diffs.append(f"different sub-sector ({cand.get('industry')})")
    rt, rp = target.revenue, cand.get("revenue")
    if rt and rp:
        ratio = rp / rt
        if 0.4 <= ratio <= 2.5:
            because.append("comparable size")
        else:
            diffs.append(f"{'larger' if ratio > 1 else 'smaller'} ({rp:,.0f} vs {rt:,.0f} Cr)")
    return because, diffs


def discover(
    conn,
    target: Target,
    *,
    max_peers: int = DEFAULT_MAX_PEERS,
    filters: Optional[dict] = None,
) -> dict:
    """Return {peers, pool, tier, rejected_summary}. peers is ranked, top-N."""
    filters = filters or {}
    if not target.sector:
        return {"peers": [], "pool": 0, "tier": None,
                "note": "target has no sector; cannot select peers"}

    rows = db.query(
        conn,
        "SELECT * FROM companies WHERE valuation_grade=1 AND sector=? AND code IS NOT ?",
        (target.sector, target.code),
    )

    # threshold screen (optional user controls), applied without dropping to zero
    min_rev = filters.get("min_revenue")
    max_rev = filters.get("max_revenue")
    min_margin = filters.get("min_ebitda_margin")

    def passes(c) -> bool:
        r = c.get("revenue")
        if min_rev is not None and (r is None or r < min_rev):
            return False
        if max_rev is not None and (r is None or r > max_rev):
            return False
        if min_margin is not None:
            m = (c.get("ebitda") / c["revenue"]) if (c.get("ebitda") is not None and c.get("revenue")) else None
            if m is None or m < min_margin:
                return False
        return True

    screened = [c for c in rows if passes(c)]

    # Tier 1: same sub-sector. Widen to whole sector only if too thin.
    tight = [c for c in screened if target.industry and c.get("industry") == target.industry]
    if len([c for c in tight]) >= MIN_PEERS:
        pool, tier = tight, "sub-sector"
    else:
        pool, tier = screened, "sector"

    scored = []
    for c in pool:
        score, ind_sim = _score(target, c)
        because, diffs = _reasons(target, c, ind_sim)
        scored.append({
            "code": c["code"], "name": c["name"], "sector": c["sector"],
            "industry": c["industry"], "revenue": c.get("revenue"),
            "ebitda": c.get("ebitda"), "pat": c.get("pat"),
            "net_worth": c.get("net_worth"), "total_debt": c.get("total_debt"),
            "enterprise_value": c.get("enterprise_value"),
            "ebitda_margin": (c.get("ebitda") / c["revenue"]) if (c.get("ebitda") is not None and c.get("revenue")) else None,
            "pat_margin": (c.get("pat") / c["revenue"]) if (c.get("pat") is not None and c.get("revenue")) else None,
            "pe": c.get("pe"), "ev_ebitda": c.get("ev_ebitda"),
            "ev_revenue": c.get("ev_revenue"), "mktcap_sales": c.get("mktcap_sales"),
            "market_cap": c.get("market_cap"), "year_end": c.get("year_end"),
            "score": score, "selected_because": because, "differences": diffs,
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    peers = scored[:max_peers]

    return {
        "peers": peers,
        "pool": len(pool),
        "sector_pool": len(rows),
        "tier": tier,
        "max_peers": max_peers,
    }
