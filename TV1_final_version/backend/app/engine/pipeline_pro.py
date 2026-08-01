"""
Professional (CA-grade) valuation pipeline: run all three approaches and
triangulate, the way a registered valuer does. The intake agent supplies the
company-specific inputs (DCF assumptions, normalization, surplus assets,
control) via the `overrides` argument.
"""
from __future__ import annotations

import os
from typing import Optional

from .. import db
from . import auto_analyst
from . import live_market
from . import llm_analyst
from . import peers as peers_mod
from . import triangulate
from .approaches import market
from .approaches import asset
from .approaches import income
from .approaches.income import DCFAssumptions
from .model import Target, load_target, resolve

# Weight given to the LLM's INDEPENDENT value estimate when blending it into the
# conclusion, keyed to the LLM's self-reported knowledge of the company.
# Measured: the LLM's own estimates are materially worse than the engine's
# (unanchored recall of Indian market caps errs ~73% median; blending raised
# error monotonically 58.6% -> 62.7% on the validation set). So the default
# weight is ZERO — the check is reported as a disclosed second opinion, not
# mixed into the number. Raise via env if you want it blended, e.g.
# LLM_CHECK_WEIGHT_HIGH=0.4.
LLM_CHECK_WEIGHT = {
    "high": float(os.environ.get("LLM_CHECK_WEIGHT_HIGH", "0.0")),
    "medium": float(os.environ.get("LLM_CHECK_WEIGHT_MEDIUM", "0.0")),
    "low": 0.0,
}

CAVEATS = [
    "Indicative valuation by an automated tool aligned to ICAI Valuation "
    "Standards / IBBI methodology — not a certified registered-valuer opinion.",
    "Three approaches (Income/DCF, Market/CCM, Asset/NAV) are triangulated; "
    "market multiples are real published Capitaline figures used as-is.",
    "The DCF reflects the assumptions shown; supply the company's own forecast, "
    "normalized earnings and WACC via the intake step for a defensible result.",
    "Comparable multiples on heterogeneous Indian companies are dispersed; the "
    "conclusion is a reasoned range, not a single certified number.",
]


def _sector_pool(conn, target: Target) -> list[dict]:
    if not target.sector:
        return []
    return db.query(
        conn,
        "SELECT * FROM companies WHERE valuation_grade=1 AND sector=? AND code IS NOT ?",
        (target.sector, target.code),
    )


def evaluate_pro(conn, target: Target, *, max_peers: int = 8,
                 overrides: Optional[dict] = None) -> dict:
    overrides = overrides or {}

    disc = peers_mod.discover(conn, target, max_peers=max_peers)
    peers = disc["peers"]
    pool = _sector_pool(conn, target)

    # ---- assumptions: auto-analyst derives them from the company's own
    # 7-year history; the intake agent's answers override field-by-field ----
    auto = auto_analyst.derive(conn, target)
    dcf_in = overrides.get("dcf", {})
    dcf = DCFAssumptions(
        horizon_years=dcf_in.get("horizon_years", auto.horizon_years),
        growth_initial=dcf_in.get("growth_initial", auto.growth_initial),
        growth_terminal=dcf_in.get("growth_terminal", auto.growth_terminal),
        ebit_margin=dcf_in.get("ebit_margin", auto.ebit_margin),
        tax_rate=dcf_in.get("tax_rate", auto.tax_rate),
        wacc=dcf_in.get("wacc", auto.wacc),
        roic=dcf_in.get("roic", auto.roic),
        note=dcf_in.get("note", auto.note),
    )
    aadj = overrides.get("asset", {})
    control_premium = overrides.get("control_premium", 0.0)

    approaches = []
    if len(peers) >= 3:
        # qualitative positioning by the LLM analyst (skipped without a key)
        llm_pos = None
        if overrides.get("use_llm", True) and llm_analyst.available():
            llm_pos = llm_analyst.position(target, peers)
        drift_info = live_market.load_drift() if overrides.get("use_drift", True) else None
        drift = 1.0
        if drift_info and not drift_info.get("stale"):
            drift = float(drift_info.get("drift_factor", 1.0))
        approaches.append(market.value(target, peers, pool,
                                       llm_position=llm_pos, drift=drift))
    else:
        approaches.append({"approach": "Market (CCM)", "status": "skipped",
                           "reason": f"only {len(peers)} comparables in {target.sector}"})
    approaches.append(income.value(target, dcf))
    approaches.append(asset.value(
        target,
        revaluation=aadj.get("revaluation", 0.0),
        surplus_assets=aadj.get("surplus_assets", 0.0),
        surplus_liabilities=aadj.get("surplus_liabilities", 0.0),
    ))

    conclusion = triangulate.conclude(target, approaches, control_premium=control_premium)

    # ---- LLM output check: independent estimate + verdict, blended by weight
    # keyed to the LLM's self-reported knowledge of the company ----
    llm_check = None
    if (overrides.get("use_llm", True) and llm_analyst.available()
            and conclusion.get("status") == "ok" and conclusion.get("equity_mid")):
        llm_check = llm_analyst.check(
            target, conclusion["equity_low"], conclusion["equity_mid"],
            conclusion["equity_high"])
        if llm_check:
            w = LLM_CHECK_WEIGHT.get(llm_check["confidence"], 0.0)
            llm_check["weight_applied"] = w
            llm_check["engine_equity_mid"] = conclusion["equity_mid"]
            if w > 0:
                blended = w * llm_check["estimate_cr"] + (1 - w) * conclusion["equity_mid"]
                scale = blended / conclusion["equity_mid"]
                for k in ("equity_low", "equity_mid", "equity_high"):
                    conclusion[k] = round(conclusion[k] * scale, 2)
                conclusion.setdefault("adjustments", []).append(
                    f"LLM check blended at weight {w:.0%} "
                    f"({llm_check['confidence']} confidence)")

    cross = None
    if target.listed and target.market_cap and conclusion.get("equity_mid"):
        delta = conclusion["equity_mid"] / target.market_cap - 1
        cross = {"own_market_cap": round(target.market_cap, 2),
                 "conclusion_equity_mid": conclusion["equity_mid"],
                 "delta_pct": round(100 * delta, 1),
                 "within_25pct": abs(delta) <= 0.25}

    # ---- live market cross-check (current traded value from screener.in) ----
    live = None
    if overrides.get("use_live", True) and target.listed:
        live = live_market.compare(target, conclusion.get("equity_mid"))

    return {
        "status": "ok",
        "target": target.to_dict(),
        "live_market": live,
        "peer_discovery": {k: v for k, v in disc.items() if k != "peers"},
        "peers": peers,
        "approaches": approaches,
        "conclusion": conclusion,
        "llm_check": llm_check,
        "market_cross_check": cross,
        "caveats": CAVEATS,
    }


def evaluate_pro_by_code(conn, code: int, **kw) -> dict:
    target = load_target(conn, code)
    if not target:
        return {"status": "no_match", "message": f"code {code} not found"}
    return evaluate_pro(conn, target, **kw)


def evaluate_pro_by_name(conn, name: str, **kw) -> dict:
    hits = resolve(conn, name)
    if not hits:
        return {"status": "no_match", "message": f"no company matches '{name}'"}
    return evaluate_pro_by_code(conn, hits[0]["code"], **kw)
