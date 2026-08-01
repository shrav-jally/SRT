"""
Comparable-company valuation on REAL published multiples.

Three methods: EV/EBITDA, EV/Revenue, P/E. For each we take the tight peer
set's published multiples, trim outliers (Tukey 1.5*IQR), weight each peer by
its similarity to the target, and pick a quality-positioned central multiple
(a high-margin company prices above the peer median, and vice-versa — a modest,
disclosed tilt). The range is the real peer dispersion (P25-P75), not a
cosmetic fixed band. Equity is bridged only when net debt is known
(NO-ASSUMPTION); P/E needs no bridge and is reported whenever PAT > 0.
"""
from __future__ import annotations

import statistics as stats
from typing import Optional

# How strongly the target's margin percentile tilts the central multiple away
# from the plain peer median (0 = pure median, 1 = full percentile match).
# Empirically tuned to 0: on REAL published multiples the margin->multiple tilt
# adds error rather than removing it (the market already prices quality, and the
# residual relationship is pure noise on Indian small/mid-caps). Leave-one-out
# on 500 companies: pos=0 median err 54.5% vs pos=0.6 60.1%.
POSITION_STRENGTH = 0.0
BAND_HALFWIDTH = 0.20            # percentile half-window for the low/high range

# Winsorize peer multiples before stats: values above these are data-error /
# distressed-earnings artefacts (e.g. a P/E of 300 on a near-zero PAT) that
# would drag a median off. Peers above the cap are clipped, not dropped.
MULTIPLE_CAPS = {"ev_ebitda": 40.0, "ev_revenue": 15.0, "pe": 80.0}


# ------------------------------------------------------------ weighted stats
def _weighted_percentile(pairs: list[tuple[float, float]], pct: float) -> float:
    """pairs = [(value, weight)]. Linear interpolation on cumulative-weight
    midpoints; equals the plain percentile when weights are equal."""
    pairs = sorted((v, w) for v, w in pairs if w > 0)
    if not pairs:
        raise ValueError("no values")
    if len(pairs) == 1:
        return pairs[0][0]
    total = sum(w for _, w in pairs)
    cum, mids = 0.0, []
    for v, w in pairs:
        mids.append((cum + w / 2) / total)
        cum += w
    target = pct
    if target <= mids[0]:
        return pairs[0][0]
    if target >= mids[-1]:
        return pairs[-1][0]
    for i in range(1, len(pairs)):
        if mids[i] >= target:
            (v0, m0), (v1, m1) = (pairs[i - 1][0], mids[i - 1]), (pairs[i][0], mids[i])
            f = (target - m0) / (m1 - m0) if m1 > m0 else 0
            return v0 + f * (v1 - v0)
    return pairs[-1][0]


def _tukey_keep(values: list[float]) -> list[bool]:
    if len(values) < 4:
        return [True] * len(values)
    q1, q3 = stats.quantiles(values, n=4)[0], stats.quantiles(values, n=4)[2]
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return [lo <= v <= hi for v in values]


def _percentile_rank(value: float, population: list[float]) -> float:
    if not population:
        return 0.5
    below = sum(1 for p in population if p < value)
    return below / len(population)


# ------------------------------------------------------------ one method
def _method(name: str, key: str, driver: Optional[float], peers: list[dict],
            margin_pct: float, is_equity_multiple: bool) -> Optional[dict]:
    if driver is None or driver <= 0:
        return {"method": name, "status": "skipped",
                "reason": "driver missing or non-positive"}
    cap = MULTIPLE_CAPS.get(key)
    raw = [(min(p[key], cap) if cap else p[key], p["score"])
           for p in peers if p.get(key) and p[key] > 0]
    if len(raw) < 3:
        return {"method": name, "status": "skipped",
                "reason": f"only {len(raw)} peers publish this multiple (need 3)"}

    values = [v for v, _ in raw]
    keep = _tukey_keep(values)
    kept = [raw[i] for i in range(len(raw)) if keep[i]]
    n_dropped = len(raw) - len(kept)

    # quality-positioned central percentile
    central_pct = 0.5 + POSITION_STRENGTH * (margin_pct - 0.5)
    central_pct = min(0.75, max(0.25, central_pct))
    lo_pct = max(0.10, central_pct - BAND_HALFWIDTH)
    hi_pct = min(0.90, central_pct + BAND_HALFWIDTH)

    m_low = _weighted_percentile(kept, lo_pct)
    m_mid = _weighted_percentile(kept, central_pct)
    m_high = _weighted_percentile(kept, hi_pct)

    vals_only = sorted(v for v, _ in kept)
    cv = (stats.pstdev(vals_only) / stats.mean(vals_only)) if len(vals_only) > 1 and stats.mean(vals_only) else 0.0

    out = {
        "method": name, "status": "ok", "multiple_key": key,
        "target_driver": round(driver, 2), "n_peers": len(raw),
        "n_outliers_dropped": n_dropped,
        "multiple_low": round(m_low, 3), "multiple_mid": round(m_mid, 3),
        "multiple_high": round(m_high, 3),
        "peer_multiple_median": round(stats.median(vals_only), 3),
        "dispersion_cv": round(cv, 3),
        "central_percentile": round(central_pct, 3),
    }

    if is_equity_multiple:            # P/E -> equity directly, no bridge
        out.update({
            "equity_low": round(m_low * driver, 2),
            "equity_mid": round(m_mid * driver, 2),
            "equity_high": round(m_high * driver, 2),
            "basis": "equity",
        })
    else:                              # EV multiple -> EV, bridge later
        out.update({
            "ev_low": round(m_low * driver, 2),
            "ev_mid": round(m_mid * driver, 2),
            "ev_high": round(m_high * driver, 2),
            "basis": "enterprise",
        })
    return out


# ------------------------------------------------------------ orchestration
def value(target, peers: list[dict]) -> dict:
    """Full valuation across the three methods + headline + confidence."""
    # target margin percentile within the peer set (drives positioning)
    peer_margins = [p["ebitda_margin"] for p in peers if p.get("ebitda_margin") is not None]
    margin_pct = _percentile_rank(target.ebitda_margin, peer_margins) if (target.ebitda_margin is not None and peer_margins) else 0.5

    net_debt = target.effective_net_debt()
    methods = [
        _method("EV/EBITDA", "ev_ebitda", target.ebitda, peers, margin_pct, False),
        _method("EV/Revenue", "ev_revenue", target.revenue, peers, margin_pct, False),
        _method("P/E", "pe", target.pat, peers, margin_pct, True),
    ]

    # bridge EV methods to equity where net debt is known
    for m in methods:
        if m.get("status") == "ok" and m["basis"] == "enterprise":
            if net_debt is not None:
                for lvl in ("low", "mid", "high"):
                    m[f"equity_{lvl}"] = round(m[f"ev_{lvl}"] - net_debt, 2)
            else:
                m["equity_requires"] = ["total_debt", "cash"]

    ok = [m for m in methods if m.get("status") == "ok"]
    headline = None
    for pref in ("EV/EBITDA", "EV/Revenue", "P/E"):
        cand = next((m for m in ok if m["method"] == pref), None)
        if cand and ("equity_mid" in cand):
            headline = cand
            break
    if headline is None and ok:
        headline = ok[0]

    # Triangulated estimate: median of the per-method equity mids. Averaging
    # independent methods cancels part of each one's idiosyncratic noise and is
    # more robust than any single headline method.
    method_equities = [m["equity_mid"] for m in ok if m.get("equity_mid")]
    blended_equity = round(stats.median(method_equities), 2) if method_equities else None

    conf = _confidence(target, peers, ok)

    cross = None
    if target.listed and target.market_cap and headline and headline.get("equity_mid"):
        delta = headline["equity_mid"] / target.market_cap - 1
        cross = {
            "own_market_cap": round(target.market_cap, 2),
            "implied_equity_mid": headline["equity_mid"],
            "delta_pct": round(100 * delta, 1),
            "within_25pct": abs(delta) <= 0.25,
        }

    return {
        "methods": methods,
        "headline_method": headline["method"] if headline else None,
        "blended_equity_mid": blended_equity,
        "equity_low": headline.get("equity_low") if headline else None,
        "equity_mid": headline.get("equity_mid") if headline else None,
        "equity_high": headline.get("equity_high") if headline else None,
        "ev_low": headline.get("ev_low") if headline else None,
        "ev_mid": headline.get("ev_mid") if headline else None,
        "ev_high": headline.get("ev_high") if headline else None,
        "net_debt": net_debt,
        "equity_requires": None if net_debt is not None else ["total_debt", "cash"],
        "quality_percentile": round(margin_pct, 3),
        "market_cross_check": cross,
        "confidence": conf,
    }


def _confidence(target, peers: list[dict], ok_methods: list[dict]) -> dict:
    n = len(peers)
    # dispersion of the headline-ish multiples
    cvs = [m["dispersion_cv"] for m in ok_methods if "dispersion_cv" in m]
    cv = min(cvs) if cvs else 1.0
    tightness = max(0.0, 1.0 - cv / 0.45)

    # method agreement (spread of equity mids)
    mids = [m["equity_mid"] for m in ok_methods if m.get("equity_mid")]
    if len(mids) >= 2 and min(mids) > 0:
        agree = max(0.0, 1.0 - (max(mids) / min(mids) - 1) / 0.80)
    else:
        agree = 0.5

    score = (0.35 * min(n, 8) / 8 + 0.35 * tightness + 0.20 * agree
             + 0.10 * (1 if len(ok_methods) >= 2 else 0))
    label = "HIGH" if score >= 0.70 else "MEDIUM" if score >= 0.45 else "LOW"
    disp = "tight" if cv <= 0.30 else "moderate" if cv <= 0.55 else "wide"
    return {
        "score": round(score, 3), "label": label, "n_peers": n,
        "dispersion": disp, "dispersion_cv": round(cv, 3),
        "method_agreement": round(agree, 3),
    }
