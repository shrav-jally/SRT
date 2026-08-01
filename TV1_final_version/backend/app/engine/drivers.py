"""
Value-driver regression → the "warranted multiple".

A blind peer median mis-prices a target whose fundamentals differ from the peer
average (a higher-growth / higher-margin peer *should* carry a higher multiple).
The professional fix is to regress peer multiples on their value drivers and read
off the multiple warranted by the TARGET's own drivers. This is the quantitative
form of the adjustment a CA makes by judgement.

We regress log(EV/EBITDA) on [EBITDA margin, log size, ROE, leverage] across the
sector pool (Ridge, standardized), then predict the target's multiple and blend
it with the robust peer median. The blend keeps us anchored to observed pricing
while tilting toward the target's fundamentals.
"""
from __future__ import annotations

import math
import statistics as stats
from typing import Optional

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

MIN_OBS = 25
MULT_CAP = 40.0
BLEND = 0.5          # weight on regression vs peer median


def _features(c: dict) -> Optional[list[float]]:
    rev, nw, pat, eb = c.get("revenue"), c.get("net_worth"), c.get("pat"), c.get("ebitda")
    td = c.get("total_debt") or 0.0
    if not (rev and rev > 0 and nw and nw > 0 and eb and eb > 0):
        return None
    roe = (pat / nw) if pat is not None else 0.0
    return [eb / rev, math.log10(rev), max(min(roe, 2.0), -1.0), max(min(td / nw, 5.0), 0.0)]


def warranted_multiple(target, sector_pool: list[dict], peer_median: float) -> dict:
    """Return {multiple, method, r2, n} — the fundamentals-adjusted EV/EBITDA."""
    tf = _features({
        "revenue": target.revenue, "net_worth": target.net_worth,
        "pat": target.pat, "ebitda": target.ebitda, "total_debt": target.total_debt,
    })
    X, y = [], []
    for c in sector_pool:
        if not (c.get("ev_ebitda") and c["ev_ebitda"] > 0):
            continue
        f = _features(c)
        if f is None:
            continue
        X.append(f)
        y.append(math.log(min(c["ev_ebitda"], MULT_CAP)))

    if tf is None or len(X) < MIN_OBS:
        return {"multiple": round(peer_median, 3), "method": "peer median",
                "reason": "insufficient data for regression", "n": len(X)}

    Xa, ya = np.array(X), np.array(y)
    scaler = StandardScaler().fit(Xa)
    model = Ridge(alpha=1.0).fit(scaler.transform(Xa), ya)
    r2 = float(model.score(scaler.transform(Xa), ya))
    pred = float(math.exp(model.predict(scaler.transform([tf]))[0]))

    # keep prediction inside the observed peer range (no extrapolation surprises)
    obs = sorted(min(v, MULT_CAP) for v in [c["ev_ebitda"] for c in sector_pool
                 if c.get("ev_ebitda") and c["ev_ebitda"] > 0])
    lo, hi = obs[len(obs) // 10], obs[max(0, len(obs) - 1 - len(obs) // 10)]
    pred = min(max(pred, lo), hi)

    blended = BLEND * pred + (1 - BLEND) * peer_median
    return {
        "multiple": round(blended, 3), "method": "warranted (regression-adjusted)",
        "regression_multiple": round(pred, 3), "peer_median": round(peer_median, 3),
        "r2": round(r2, 3), "n": len(X),
        "drivers": ["ebitda_margin", "log_size", "roe", "leverage"],
    }
