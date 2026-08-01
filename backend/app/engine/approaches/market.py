"""
Market Approach — Comparable Company Method with a fundamentals-adjusted
(warranted) multiple. EV/EBITDA is priced off the warranted multiple; EV/Revenue
and P/E are provided as supporting cross-checks at the peer median.
"""
from __future__ import annotations

import statistics as stats
from typing import Optional

from .. import drivers

MULT_CAP = {"ev_ebitda": 40.0, "ev_revenue": 15.0, "pe": 80.0}

# Weight of the LLM analyst's positioned multiple vs the quantitative
# (warranted/median) multiple. Validated on 15 real names: error falls
# monotonically with LLM weight (58.6% @0 -> 43.8% @1.0), so the LLM's
# positioning carries full weight when available; the quantitative multiple
# remains the automatic fallback. Override with env LLM_BLEND.
import os
LLM_BLEND = float(os.environ.get("LLM_BLEND", "1.0"))


def _median_mult(peers: list[dict], key: str) -> Optional[float]:
    vs = [min(p[key], MULT_CAP[key]) for p in peers if p.get(key) and p[key] > 0]
    return stats.median(vs) if len(vs) >= 3 else None


def _percentile(sorted_vals: list[float], pct: float) -> float:
    import math
    k = (len(sorted_vals) - 1) * pct
    f = math.floor(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _peer_stats(peers: list[dict], key: str) -> dict:
    vs = sorted(min(p[key], MULT_CAP[key]) for p in peers
                if p.get(key) and p[key] > 0)
    if not vs:
        return {"n": 0}
    return {"n": len(vs), "min": round(vs[0], 2), "max": round(vs[-1], 2),
            "median": round(stats.median(vs), 2),
            "values": [round(v, 2) for v in vs]}


def _calculations(target, peers, nd, headline, med_rev, med_pe) -> list[dict]:
    """Every ratio's full arithmetic, so the report can show the working."""
    out = []
    if headline:
        m = headline["multiple"]
        out.append({
            "ratio": "EV/EBITDA", "applies": True,
            "peer_stats": _peer_stats(peers, "ev_ebitda"),
            "multiple_used": m,
            "multiple_source": (headline.get("multiple_basis") or {}).get("method", "peer median"),
            "driver_label": "EBITDA", "driver_value": round(target.ebitda, 2),
            "enterprise_value": headline["ev_mid"],
            "net_debt": nd, "equity_value": headline.get("equity_mid"),
            "formula": f"EV = {m} x EBITDA {target.ebitda:,.0f} = {headline['ev_mid']:,.0f}"
                       + (f"; equity = EV - net debt {nd:,.0f} = {headline['equity_mid']:,.0f}"
                          if nd is not None and headline.get("equity_mid") is not None
                          else "; equity withheld (net debt unknown)"),
        })
    else:
        out.append({"ratio": "EV/EBITDA", "applies": False,
                    "reason": "EBITDA missing/non-positive or fewer than 3 peers publish it"})

    if med_rev and target.revenue and target.revenue > 0:
        ev = med_rev * target.revenue
        eq = ev - nd if nd is not None else None
        out.append({
            "ratio": "EV/Revenue", "applies": True,
            "peer_stats": _peer_stats(peers, "ev_revenue"),
            "multiple_used": round(med_rev, 3), "multiple_source": "peer median",
            "driver_label": "Revenue", "driver_value": round(target.revenue, 2),
            "enterprise_value": round(ev, 2), "net_debt": nd,
            "equity_value": round(eq, 2) if eq is not None else None,
            "formula": f"EV = {med_rev:.2f} x revenue {target.revenue:,.0f} = {ev:,.0f}"
                       + (f"; equity = EV - net debt {nd:,.0f} = {eq:,.0f}"
                          if eq is not None else "; equity withheld"),
        })
    else:
        out.append({"ratio": "EV/Revenue", "applies": False,
                    "reason": "revenue missing or fewer than 3 peers publish EV/Revenue"})

    if med_pe and target.pat and target.pat > 0:
        eq = med_pe * target.pat
        out.append({
            "ratio": "P/E", "applies": True,
            "peer_stats": _peer_stats(peers, "pe"),
            "multiple_used": round(med_pe, 3), "multiple_source": "peer median",
            "driver_label": "PAT", "driver_value": round(target.pat, 2),
            "enterprise_value": None, "net_debt": None,
            "equity_value": round(eq, 2),
            "formula": f"equity = {med_pe:.2f} x PAT {target.pat:,.0f} = {eq:,.0f} "
                       f"(equity multiple — no net-debt bridge)",
        })
    else:
        out.append({"ratio": "P/E", "applies": False,
                    "reason": "PAT missing/non-positive or fewer than 3 peers publish P/E"})
    return out


def value(target, peers: list[dict], sector_pool: list[dict],
          llm_position: dict | None = None, drift: float = 1.0) -> dict:
    nd = target.effective_net_debt()
    supporting = []

    # --- EV/EBITDA priced off the warranted (regression-adjusted) multiple,
    #     positioned within the peer range by the LLM analyst when available ---
    med_ebitda = _median_mult(peers, "ev_ebitda")
    headline = None
    if med_ebitda and target.ebitda and target.ebitda > 0:
        w = drivers.warranted_multiple(target, sector_pool, med_ebitda)
        mult = w["multiple"]
        if llm_position:
            vs = sorted(min(p["ev_ebitda"], MULT_CAP["ev_ebitda"])
                        for p in peers if p.get("ev_ebitda") and p["ev_ebitda"] > 0)
            llm_mult = _percentile(vs, llm_position["percentile"])
            # blend quantitative (warranted) with qualitative (LLM positioning)
            mult = round((1 - LLM_BLEND) * mult + LLM_BLEND * llm_mult, 3)
            w = {**w, "llm_percentile": llm_position["percentile"],
                 "llm_multiple": round(llm_mult, 3),
                 "llm_rationale": llm_position["rationale"],
                 "llm_confidence": llm_position["confidence"],
                 "method": w["method"] + " + LLM positioning"}
        # Peer multiples come from the stored fiscal-year snapshot. `drift`
        # re-levels them to today's market (measured live), so the conclusion
        # reflects current pricing rather than the snapshot date.
        if drift and drift != 1.0:
            mult = round(mult * drift, 3)
            w = {**w, "market_drift_applied": round(drift, 4)}
        ev = mult * target.ebitda
        headline = {
            "multiple_kind": "EV/EBITDA", "multiple": mult,
            "multiple_basis": w, "ev_mid": round(ev, 2),
            "equity_mid": round(ev - nd, 2) if nd is not None else None,
        }

    # --- supporting: EV/Revenue and P/E at peer median ---
    med_rev = _median_mult(peers, "ev_revenue")
    if med_rev and target.revenue and target.revenue > 0:
        ev = med_rev * target.revenue
        supporting.append({"multiple_kind": "EV/Revenue", "multiple": round(med_rev, 3),
                           "ev_mid": round(ev, 2),
                           "equity_mid": round(ev - nd, 2) if nd is not None else None})
    med_pe = _median_mult(peers, "pe")
    if med_pe and target.pat and target.pat > 0:
        supporting.append({"multiple_kind": "P/E", "multiple": round(med_pe, 3),
                           "equity_mid": round(med_pe * target.pat, 2)})

    # --- full arithmetic per ratio, for the report/audit section ---
    calculations = _calculations(target, peers, nd, headline, med_rev, med_pe)

    if headline is None and not supporting:
        return {"approach": "Market (CCM)", "status": "skipped",
                "reason": "no usable peer multiple / driver"}

    # equity range from the spread of all method equity mids
    eqs = [m["equity_mid"] for m in ([headline] + supporting)
           if m and m.get("equity_mid")]
    eq_mid = headline["equity_mid"] if (headline and headline.get("equity_mid")) else (eqs[0] if eqs else None)
    if eqs:
        lo, hi = min(eqs), max(eqs)
        # ensure a band even with one method: ±15%
        if lo == hi:
            lo, hi = lo * 0.85, hi * 1.15
    else:
        lo = hi = None

    return {
        "approach": "Market (CCM)", "status": "ok",
        "headline": headline, "supporting": supporting,
        "calculations": calculations,
        "n_peers": len(peers),
        "equity_low": round(lo, 2) if lo is not None else None,
        "equity_mid": eq_mid,
        "equity_high": round(hi, 2) if hi is not None else None,
        "ev_mid": headline["ev_mid"] if headline else None,
        "equity_requires": None if nd is not None else ["total_debt", "cash"],
    }
