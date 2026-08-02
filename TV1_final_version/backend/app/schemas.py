"""Pydantic request/response shapes for the API layer."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PeerFilters(BaseModel):
    min_revenue: Optional[float] = None
    max_revenue: Optional[float] = None
    min_ebitda_margin: Optional[float] = None


class ValueByCodeRequest(BaseModel):
    code: int
    max_peers: int = Field(8, ge=3, le=15)
    filters: Optional[PeerFilters] = None
    # one-shot analyst overrides, e.g. {"dcf": {"growth_initial": 0.18,
    # "wacc": 0.115}, "asset": {"surplus_assets": 20}, "use_llm": true}
    overrides: Optional[dict] = None


class CustomTarget(BaseModel):
    """A private company priced off the listed universe (manual or VLM input)."""
    name: str
    sector: str
    industry: Optional[str] = None
    revenue: Optional[float] = None
    ebitda: Optional[float] = None
    ebit: Optional[float] = None
    pat: Optional[float] = None
    net_worth: Optional[float] = None
    total_debt: Optional[float] = None
    cash: Optional[float] = None
    source: str = "user"


class ValueCustomRequest(BaseModel):
    target: CustomTarget
    max_peers: int = Field(8, ge=3, le=15)
    filters: Optional[PeerFilters] = None
    overrides: Optional[dict] = None
