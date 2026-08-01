"""
Income Approach — Discounted Cash Flow (FCFF).

This is the method that captures company-specific value (growth, margins, risk)
that comparables cannot. Assumptions are explicit, defaulted, and meant to be
overridden by the LangGraph intake agent with the client's own numbers — which
is exactly how a registered valuer builds a DCF.

FCFF_t = EBIT_t * (1 - tax) * (1 - reinvestment_rate_t)
reinvestment_rate = g / ROIC          (Damodaran: growth must be funded)
TV = FCFF_{N+1} / (WACC - g_terminal)  (Gordon growth)
EV = Σ PV(FCFF_t) + PV(TV)  ;  Equity = EV - net_debt
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DCFAssumptions:
    horizon_years: int = 5
    growth_initial: float = 0.10       # yr-1 revenue growth (agent overrides)
    growth_terminal: float = 0.05      # perpetuity growth (~ nominal GDP)
    ebit_margin: Optional[float] = None  # default = target's current EBIT margin
    tax_rate: float = 0.25             # India headline corporate tax
    wacc: float = 0.13                 # default; agent can build up per company
    roic: float = 0.15                 # to tie reinvestment to growth
    note: str = "default assumptions — override via intake agent"

    def faded_growth(self) -> list[float]:
        """Linearly fade yr-1 growth to terminal growth over the horizon."""
        n = self.horizon_years
        return [
            self.growth_initial
            + (self.growth_terminal - self.growth_initial) * (t - 1) / max(n - 1, 1)
            for t in range(1, n + 1)
        ]


def _dcf_once(revenue0: float, a: DCFAssumptions) -> float:
    if a.wacc <= a.growth_terminal:
        a = DCFAssumptions(**{**a.__dict__, "wacc": a.growth_terminal + 0.03})
    margin = a.ebit_margin
    growths = a.faded_growth()
    rev = revenue0
    pv_sum = 0.0
    ebit_n = 0.0
    for t, g in enumerate(growths, start=1):
        rev *= (1 + g)
        ebit = rev * margin
        ebit_n = ebit
        reinvest = min(g / a.roic, 0.9) if a.roic > 0 else 0.0
        fcff = ebit * (1 - a.tax_rate) * (1 - reinvest)
        pv_sum += fcff / (1 + a.wacc) ** t
    gt = a.growth_terminal
    reinvest_t = min(gt / a.roic, 0.9) if a.roic > 0 else 0.0
    fcff_next = ebit_n * (1 + gt) * (1 - a.tax_rate) * (1 - reinvest_t)
    tv = fcff_next / (a.wacc - gt)
    pv_tv = tv / (1 + a.wacc) ** a.horizon_years
    return pv_sum + pv_tv


def value(target, assumptions: Optional[DCFAssumptions] = None) -> dict:
    a = assumptions or DCFAssumptions()
    if a.ebit_margin is None:
        if target.ebit is not None and target.revenue:
            a.ebit_margin = target.ebit / target.revenue
        elif target.ebitda is not None and target.revenue:
            a.ebit_margin = 0.85 * (target.ebitda / target.revenue)  # EBIT≈0.85·EBITDA
        else:
            return {"approach": "Income (DCF)", "status": "skipped",
                    "reason": "no EBIT/EBITDA margin available"}
    if not target.revenue or target.revenue <= 0:
        return {"approach": "Income (DCF)", "status": "skipped",
                "reason": "revenue required for DCF"}

    ev_mid = _dcf_once(target.revenue, a)
    # sensitivity band: WACC ±1.5pt and terminal growth ∓1pt (jointly, low/high)
    low_a = DCFAssumptions(**{**a.__dict__, "wacc": a.wacc + 0.015, "growth_terminal": max(0.02, a.growth_terminal - 0.01)})
    high_a = DCFAssumptions(**{**a.__dict__, "wacc": max(a.growth_terminal + 0.03, a.wacc - 0.015), "growth_terminal": a.growth_terminal + 0.01})
    ev_low = _dcf_once(target.revenue, low_a)
    ev_high = _dcf_once(target.revenue, high_a)

    nd = target.effective_net_debt()
    out = {
        "approach": "Income (DCF)", "status": "ok",
        "ev_low": round(ev_low, 2), "ev_mid": round(ev_mid, 2), "ev_high": round(ev_high, 2),
        "assumptions": {
            "horizon_years": a.horizon_years, "growth_initial": a.growth_initial,
            "growth_terminal": a.growth_terminal, "ebit_margin": round(a.ebit_margin, 4),
            "tax_rate": a.tax_rate, "wacc": a.wacc, "roic": a.roic, "note": a.note,
        },
    }
    if nd is not None:
        out.update({"equity_low": round(ev_low - nd, 2),
                    "equity_mid": round(ev_mid - nd, 2),
                    "equity_high": round(ev_high - nd, 2)})
    else:
        out["equity_requires"] = ["total_debt", "cash"]
    return out
