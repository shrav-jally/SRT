"""
Company model + resolver. A single `Target` shape flows through the whole
engine, whether it comes from the comps DB (a listed company we already hold)
or from user/VLM-supplied financials for a private company.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

from .. import db


@dataclass
class Target:
    name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    # drivers (₹ Crore)
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    ebit: Optional[float] = None
    pat: Optional[float] = None
    net_worth: Optional[float] = None
    # bridge inputs (may be unknown -> equity withheld)
    total_debt: Optional[float] = None
    cash: Optional[float] = None
    net_debt: Optional[float] = None
    # context
    market_cap: Optional[float] = None     # only for listed self cross-check
    code: Optional[int] = None
    listed: bool = False
    is_bank: bool = False
    source: str = "user"                   # "db" | "user" | "vlm"

    @property
    def ebitda_margin(self) -> Optional[float]:
        return self.ebitda / self.revenue if (self.ebitda is not None and self.revenue) else None

    @property
    def pat_margin(self) -> Optional[float]:
        return self.pat / self.revenue if (self.pat is not None and self.revenue) else None

    def effective_net_debt(self) -> Optional[float]:
        """NO-ASSUMPTION rule: net debt only when derivable, never assumed 0."""
        if self.net_debt is not None:
            return self.net_debt
        if self.total_debt is not None and self.cash is not None:
            return self.total_debt - self.cash
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ebitda_margin"] = self.ebitda_margin
        d["pat_margin"] = self.pat_margin
        d["net_debt_effective"] = self.effective_net_debt()
        return d


def from_row(row: dict) -> Target:
    return Target(
        name=row["name"], sector=row.get("sector"), industry=row.get("industry"),
        revenue=row.get("revenue"), ebitda=row.get("ebitda"), ebit=row.get("ebit"),
        pat=row.get("pat"), net_worth=row.get("net_worth"),
        total_debt=row.get("total_debt"), cash=row.get("cash"),
        net_debt=row.get("net_debt"), market_cap=row.get("market_cap"),
        code=row.get("code"), listed=bool(row.get("market_cap")),
        is_bank=bool(row.get("is_bank")), source="db",
    )


def resolve(conn, query: str) -> list[dict]:
    """Confidence-ranked name/code search over the whole stored universe."""
    q = (query or "").strip()
    if not q:
        return []
    if q.isdigit():
        rows = db.query(conn, "SELECT * FROM companies WHERE code = ?", (int(q),))
        if rows:
            return rows
    like = f"%{q.lower()}%"
    rows = db.query(
        conn,
        """SELECT * FROM companies
           WHERE lower(name) LIKE ?
           ORDER BY valuation_grade DESC,
                    CASE WHEN lower(name)=? THEN 0
                         WHEN lower(name) LIKE ? THEN 1 ELSE 2 END,
                    length(name)
           LIMIT 25""",
        (like, q.lower(), f"{q.lower()}%"),
    )
    return rows


def load_target(conn, code: int) -> Optional[Target]:
    row = db.query_one(conn, "SELECT * FROM companies WHERE code = ?", (code,))
    return from_row(row) if row else None
