"""
LangGraph intake agent — the human-in-the-loop interview a valuer conducts
before signing off. For a chosen company it gathers the company-specific inputs
that actually drive value (and that comparables cannot supply): forecast growth,
sustainable margin, discount rate, earnings normalization, surplus assets, and
control — then runs the three-approach triangulated valuation.

Implemented as a LangGraph StateGraph with `interrupt()` human-in-the-loop, one
question per step, persisted via MemorySaver keyed by a thread id so the Q&A can
span separate HTTP requests. Deterministic (no LLM key required); a listed
target's financials are pre-filled from the DB so most answers can be accepted
as defaults.
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from langgraph.checkpoint.memory import MemorySaver

from .. import db
from ..engine import auto_analyst
from ..engine.model import Target, load_target
from ..engine.pipeline_pro import evaluate_pro


class IState(TypedDict, total=False):
    ref: dict            # {"code": int} or {"custom": {...}}
    target: dict         # serialized Target
    q_index: int
    answers: dict
    questions: list
    result: dict


def _questions(t: Target, auto=None) -> list[dict]:
    """Defaults are the AUTO-ANALYST's derived values (from the company's own
    7-year history) so the analyst confirms or corrects, never starts blank."""
    cur_margin = round((t.ebit / t.revenue * 100), 1) if (t.ebit and t.revenue) else (
        round(0.85 * t.ebitda / t.revenue * 100, 1) if (t.ebitda and t.revenue) else 12.0)
    d_growth = round(auto.growth_initial * 100, 1) if auto else 10.0
    d_term = round(auto.growth_terminal * 100, 1) if auto else 5.0
    d_margin = round(auto.ebit_margin * 100, 1) if (auto and auto.ebit_margin is not None) else cur_margin
    d_wacc = round(auto.wacc * 100, 1) if auto else 13.0
    qs = [
        {"key": "growth_initial", "kind": "pct", "default": d_growth,
         "prompt": f"Expected revenue growth next year (%)? Auto-derived from its history: {d_growth}%."},
        {"key": "growth_terminal", "kind": "pct", "default": d_term,
         "prompt": f"Long-term (terminal) growth rate (%)? Suggested {d_term}% (~nominal GDP)."},
        {"key": "ebit_margin", "kind": "pct", "default": d_margin,
         "prompt": f"Sustainable EBIT margin (%)? Normalized over its history ≈ {d_margin}%."},
        {"key": "wacc", "kind": "pct", "default": d_wacc,
         "prompt": f"Discount rate / WACC (%)? Build-up estimate {d_wacc}% (size/leverage/volatility adjusted)."},
        {"key": "ebitda_adjustment", "kind": "cr", "default": 0.0,
         "prompt": "One-time / non-operating EBITDA adjustment (₹ Cr, + or −)? "
                   "e.g. remove exceptional gains, add back excess owner pay. 0 if none."},
        {"key": "surplus_assets", "kind": "cr", "default": 0.0,
         "prompt": "Surplus / non-operating assets to add to value (₹ Cr)? "
                   "e.g. idle land, investments. 0 if none."},
        {"key": "controlling_stake", "kind": "yn", "default": "y",
         "prompt": "Is this a controlling (majority) stake? (y/n)"},
    ]
    if t.effective_net_debt() is None:
        qs.append({"key": "total_debt", "kind": "cr", "default": 0.0,
                   "prompt": "Total borrowings (₹ Cr)? Needed to bridge EV → equity."})
        qs.append({"key": "cash", "kind": "cr", "default": 0.0,
                   "prompt": "Cash & investments (₹ Cr)?"})
    return qs


def _parse(kind: str, raw: Any, default: Any):
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return default
    if kind == "yn":
        return "y" if str(raw).strip().lower().startswith("y") else "n"
    try:
        return float(str(raw).replace("%", "").replace(",", "").strip())
    except ValueError:
        return default


# ---------------------------------------------------------------- nodes
def _build_target(state: IState) -> IState:
    ref = state["ref"]
    with db.connect() as conn:
        if "code" in ref:
            t = load_target(conn, ref["code"])
        else:
            t = Target(**ref["custom"])
        auto = auto_analyst.derive(conn, t) if t else None
    return {"target": t.to_dict() if t else None,
            "questions": _questions(t, auto) if t else [],
            "q_index": 0, "answers": {}}


def _ask(state: IState) -> IState:
    qs, i = state["questions"], state["q_index"]
    q = qs[i]
    raw = interrupt({"question": q["prompt"], "key": q["key"],
                     "kind": q["kind"], "default": q["default"],
                     "step": i + 1, "total": len(qs)})
    answers = dict(state.get("answers", {}))
    answers[q["key"]] = _parse(q["kind"], raw, q["default"])
    return {"answers": answers, "q_index": i + 1}


def _more(state: IState) -> str:
    return "ask" if state["q_index"] < len(state["questions"]) else "compute"


def _compute(state: IState) -> IState:
    td = state["target"]
    a = state["answers"]
    t = Target(
        name=td["name"], sector=td.get("sector"), industry=td.get("industry"),
        revenue=td.get("revenue"), ebitda=td.get("ebitda"), ebit=td.get("ebit"),
        pat=td.get("pat"), net_worth=td.get("net_worth"),
        total_debt=a.get("total_debt", td.get("total_debt")),
        cash=a.get("cash", td.get("cash")), net_debt=td.get("net_debt"),
        market_cap=td.get("market_cap"), code=td.get("code"),
        listed=td.get("listed", False), is_bank=td.get("is_bank", False),
        source=td.get("source", "user"),
    )
    # apply normalization to the EBITDA driver
    if a.get("ebitda_adjustment") and t.ebitda is not None:
        t.ebitda = t.ebitda + a["ebitda_adjustment"]

    overrides = {
        "dcf": {
            "growth_initial": a["growth_initial"] / 100,
            "growth_terminal": a["growth_terminal"] / 100,
            "ebit_margin": a["ebit_margin"] / 100,
            "wacc": a["wacc"] / 100,
            "note": "analyst inputs via intake agent",
        },
        "asset": {"surplus_assets": a.get("surplus_assets", 0.0)},
        "control_premium": 0.0 if a.get("controlling_stake", "y") == "y" else -0.10,
    }
    with db.connect() as conn:
        result = evaluate_pro(conn, t, overrides=overrides)
    result["intake_inputs"] = a
    return {"result": result}


def _graph():
    g = StateGraph(IState)
    g.add_node("build", _build_target)
    g.add_node("ask", _ask)
    g.add_node("compute", _compute)
    g.add_edge(START, "build")
    g.add_edge("build", "ask")
    g.add_conditional_edges("ask", _more, {"ask": "ask", "compute": "compute"})
    g.add_edge("compute", END)
    return g.compile(checkpointer=MemorySaver())


GRAPH = _graph()
