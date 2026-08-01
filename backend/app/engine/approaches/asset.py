"""
Asset Approach — Net Asset Value (NAV).

Book equity (net worth) adjusted for revaluation of assets and any surplus /
non-operating items the intake agent surfaces. For a going concern this is
usually a floor; for asset-heavy or loss-making companies it carries more
weight in the triangulation.
"""
from __future__ import annotations

from typing import Optional


def value(target, *, revaluation: float = 0.0,
          surplus_assets: float = 0.0, surplus_liabilities: float = 0.0) -> dict:
    if target.net_worth is None:
        return {"approach": "Asset (NAV)", "status": "skipped",
                "reason": "net worth not available"}
    equity = target.net_worth + revaluation + surplus_assets - surplus_liabilities
    # a symmetric ±10% presentation band around book-derived NAV
    return {
        "approach": "Asset (NAV)", "status": "ok",
        "equity_low": round(equity * 0.90, 2),
        "equity_mid": round(equity, 2),
        "equity_high": round(equity * 1.10, 2),
        "components": {
            "net_worth": target.net_worth, "revaluation": revaluation,
            "surplus_assets": surplus_assets, "surplus_liabilities": surplus_liabilities,
        },
    }
