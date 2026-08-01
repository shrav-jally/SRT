"""
Auto-analyst: derive company-specific DCF assumptions from the company's own
7-year history — automatically reproducing the judgment steps a CA performs
before a manual valuation:

  growth       historical revenue CAGR, damped toward the sector median
               (mean reversion), clamped to a defensible band
  EBIT margin  NORMALIZED across the cycle (median of historical margins),
               not the possibly-exceptional latest year
  WACC         build-up method: risk-free + equity risk premium, plus size,
               leverage and earnings-volatility premia
  ROIC         EBIT(1-t) / capital employed (ties reinvestment to growth)

Every derived number carries its provenance so the report can show WHY.
"""
from __future__ import annotations

import statistics as stats
from typing import Optional

from .. import db
from .approaches.income import DCFAssumptions

RISK_FREE = 0.071          # India 10y G-sec, mid-2026
ERP = 0.060                # equity risk premium
DAMP = 0.60                # weight on own history vs sector median growth
GROWTH_BAND = (-0.05, 0.30)
WACC_BAND = (0.10, 0.18)


def _history(conn, code: int) -> list[dict]:
    return db.query(
        conn,
        "SELECT * FROM history WHERE code=? ORDER BY years_back",
        (code,),
    )


def _cagr(newest: float, oldest: float, years: int) -> Optional[float]:
    if newest and oldest and newest > 0 and oldest > 0 and years > 0:
        return (newest / oldest) ** (1.0 / years) - 1.0
    return None


def _revenue_cagr(hist: list[dict]) -> Optional[float]:
    pts = [(h["years_back"], h["sales"]) for h in hist if h.get("sales")]
    if len(pts) < 2:
        return None
    newest = pts[0]
    # longest window up to 5 years back for a smoothed CAGR
    candidates = [p for p in pts if 2 <= p[0] <= 5]
    if not candidates:
        return None
    oldest = candidates[-1]
    return _cagr(newest[1], oldest[1], oldest[0] - newest[0])


def _margins(hist: list[dict]) -> list[float]:
    out = []
    for h in hist:
        s, e = h.get("sales"), h.get("ebitda")
        if s and s > 0 and e is not None:
            out.append(e / s)
    return out


def sector_growth_median(conn, sector: str) -> Optional[float]:
    """Median historical revenue CAGR across the sector's grade companies."""
    rows = db.query(
        conn,
        """SELECT h0.code, h0.sales AS s0, hk.years_back AS k, hk.sales AS sk
           FROM history h0
           JOIN history hk ON hk.code = h0.code AND hk.years_back =
               (SELECT MAX(years_back) FROM history hx
                WHERE hx.code = h0.code AND hx.years_back <= 5 AND hx.sales > 0)
           JOIN companies c ON c.code = h0.code
           WHERE h0.years_back = 0 AND h0.sales > 0
             AND c.valuation_grade = 1 AND c.sector = ?""",
        (sector,),
    )
    cagrs = []
    for r in rows:
        g = _cagr(r["s0"], r["sk"], r["k"])
        if g is not None and -0.5 < g < 1.0:
            cagrs.append(g)
    return stats.median(cagrs) if len(cagrs) >= 5 else None


def derive(conn, target, *, sector_growth: Optional[float] = None) -> DCFAssumptions:
    """Build DCFAssumptions from the target's own history (auto-analyst mode)."""
    hist = _history(conn, target.code) if target.code else []
    provenance: list[str] = []

    # ---- growth: damped historical CAGR ----
    own_g = _revenue_cagr(hist)
    if sector_growth is None and target.sector:
        sector_growth = sector_growth_median(conn, target.sector)
    if own_g is not None and sector_growth is not None:
        g = DAMP * own_g + (1 - DAMP) * sector_growth
        provenance.append(
            f"growth {g:.1%} = {DAMP:.0%}·own CAGR {own_g:.1%} + {1-DAMP:.0%}·sector median {sector_growth:.1%}")
    elif own_g is not None:
        g = 0.7 * own_g + 0.3 * 0.05
        provenance.append(f"growth from own CAGR {own_g:.1%} damped toward 5%")
    elif sector_growth is not None:
        g = sector_growth
        provenance.append(f"growth = sector median {sector_growth:.1%} (no own history)")
    else:
        g = 0.08
        provenance.append("growth default 8% (no history available)")
    g = min(max(g, GROWTH_BAND[0]), GROWTH_BAND[1])

    # ---- normalized margin across the cycle ----
    margins = _margins(hist)
    if len(margins) >= 3:
        norm_ebitda_margin = stats.median(margins)
        provenance.append(
            f"EBITDA margin normalized to {norm_ebitda_margin:.1%} (median of {len(margins)} yrs)")
    elif target.ebitda is not None and target.revenue:
        norm_ebitda_margin = target.ebitda / target.revenue
        provenance.append("margin = latest year (insufficient history)")
    else:
        norm_ebitda_margin = None

    ebit_margin = None
    if norm_ebitda_margin is not None:
        ratio = 0.85
        if target.ebit is not None and target.ebitda and target.ebitda > 0:
            ratio = min(max(target.ebit / target.ebitda, 0.4), 1.0)
        ebit_margin = norm_ebitda_margin * ratio

    # ---- WACC build-up ----
    wacc = RISK_FREE + ERP
    rev = target.revenue or 0
    if rev < 100:
        wacc += 0.030; provenance.append("WACC +3.0% size premium (rev < ₹100 Cr)")
    elif rev < 500:
        wacc += 0.015; provenance.append("WACC +1.5% size premium (rev < ₹500 Cr)")
    elif rev < 2000:
        wacc += 0.005
    de = None
    if target.total_debt is not None and target.net_worth and target.net_worth > 0:
        de = target.total_debt / target.net_worth
        if de > 3:
            wacc += 0.020; provenance.append("WACC +2.0% high leverage (D/E > 3)")
        elif de > 1.5:
            wacc += 0.010; provenance.append("WACC +1.0% elevated leverage (D/E > 1.5)")
    if len(margins) >= 4:
        m_mean = stats.mean(margins)
        if m_mean and abs(m_mean) > 1e-9:
            vol = stats.pstdev(margins) / abs(m_mean)
            if vol > 0.40:
                wacc += 0.010
                provenance.append("WACC +1.0% earnings volatility (margin CV > 0.4)")
    wacc = min(max(wacc, WACC_BAND[0]), WACC_BAND[1])

    # ---- ROIC ----
    roic = 0.15
    if (target.ebit is not None and target.ebit > 0
            and getattr(target, "net_worth", None)):
        ce_rows = [h.get("capital_employed") for h in hist[:1]]
        ce = ce_rows[0] if ce_rows and ce_rows[0] else None
        if ce and ce > 0:
            roic = min(max(target.ebit * 0.75 / ce, 0.06), 0.40)

    return DCFAssumptions(
        growth_initial=round(g, 4),
        growth_terminal=min(0.05, max(0.03, round(g / 2, 4))),
        ebit_margin=round(ebit_margin, 4) if ebit_margin is not None else None,
        wacc=round(wacc, 4),
        roic=round(roic, 4),
        note="auto-analyst: " + "; ".join(provenance),
    )
