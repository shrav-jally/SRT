"""Company search, detail, taxonomy, and valuation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..engine import pipeline, pipeline_pro
from ..engine.model import Target, resolve
from ..schemas import ValueByCodeRequest, ValueCustomRequest

router = APIRouter(prefix="/api", tags=["companies"])


@router.get("/health")
def health():
    with db.connect() as conn:
        meta = {r["k"]: r["v"] for r in db.query(conn, "SELECT k, v FROM meta")}
    return {"status": "ok", "db": "postgres" if db.IS_POSTGRES else "sqlite", "meta": meta}


@router.get("/search")
def search(q: str = Query(..., min_length=1), limit: int = 15):
    with db.connect() as conn:
        hits = resolve(conn, q)[:limit]
    return [{
        "code": h["code"], "name": h["name"], "sector": h.get("sector"),
        "industry": h.get("industry"), "revenue": h.get("revenue"),
        "valuation_grade": bool(h.get("valuation_grade")),
    } for h in hits]


@router.get("/sectors")
def sectors():
    with db.connect() as conn:
        rows = db.query(
            conn,
            """SELECT sector, industry, COUNT(*) n FROM companies
               WHERE valuation_grade=1 AND sector IS NOT NULL
               GROUP BY sector, industry ORDER BY sector, n DESC""",
        )
    tree: dict[str, list] = {}
    for r in rows:
        tree.setdefault(r["sector"], []).append({"industry": r["industry"], "n": r["n"]})
    return [{"sector": s, "n": sum(i["n"] for i in inds), "industries": inds}
            for s, inds in sorted(tree.items())]


@router.get("/company/{code}")
def company(code: int):
    with db.connect() as conn:
        row = db.query_one(conn, "SELECT * FROM companies WHERE code = ?", (code,))
    if not row:
        raise HTTPException(404, f"company {code} not found")
    return row


@router.post("/value")
def value_by_code(req: ValueByCodeRequest):
    f = req.filters.model_dump(exclude_none=True) if req.filters else None
    with db.connect() as conn:
        res = pipeline.evaluate_by_code(conn, req.code, max_peers=req.max_peers, filters=f)
    if res["status"] == "no_match":
        raise HTTPException(404, res["message"])
    return res


@router.post("/value/pro")
def value_pro(req: ValueByCodeRequest):
    """Three-approach triangulated valuation. Auto-analyst derives assumptions;
    pass `overrides` for one-shot analyst adjustments."""
    with db.connect() as conn:
        res = pipeline_pro.evaluate_pro_by_code(
            conn, req.code, max_peers=req.max_peers, overrides=req.overrides)
    if res["status"] == "no_match":
        raise HTTPException(404, res["message"])
    return res


def _custom_target(t) -> Target:
    return Target(
        name=t.name, sector=t.sector, industry=t.industry, revenue=t.revenue,
        ebitda=t.ebitda, ebit=t.ebit, pat=t.pat, net_worth=t.net_worth,
        total_debt=t.total_debt, cash=t.cash, source=t.source,
    )


@router.post("/value/custom")
def value_custom(req: ValueCustomRequest):
    f = req.filters.model_dump(exclude_none=True) if req.filters else None
    with db.connect() as conn:
        res = pipeline.evaluate(conn, _custom_target(req.target), max_peers=req.max_peers, filters=f)
    return res


@router.post("/value/pro/custom")
def value_pro_custom(req: ValueCustomRequest):
    """Three-approach triangulated valuation for a private/custom company."""
    with db.connect() as conn:
        res = pipeline_pro.evaluate_pro(
            conn, _custom_target(req.target), max_peers=req.max_peers,
            overrides=req.overrides)
    return res


# Aliases matching the static frontend's fetch paths (same-origin serving).
@router.post("/value-pro")
def value_pro_alias(req: ValueByCodeRequest):
    return value_pro(req)


@router.post("/value-pro-custom")
def value_pro_custom_alias(req: ValueCustomRequest):
    return value_pro_custom(req)
