"""MSME Valuation Contract v0 — Domain Extractor output model.

Specifies the output format for MSME valuation mapping.
Consumes only FinancialStatementsDocument and CanonicalDocument.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field

from .common import ExtractionStatus, Provenance, ValidationIssue
from .financial_statements_v0 import PeriodValue


class MSMEFieldResult(BaseModel):
    """Extraction result for a single MSME valuation field."""
    field_name: str
    category: str
    required_by_msme: bool = True
    current_period_value: Optional[PeriodValue] = None
    comparative_period_value: Optional[PeriodValue] = None
    status: ExtractionStatus = ExtractionStatus.NOT_FOUND
    is_derived: bool = False
    calculation_formula: Optional[str] = None
    provenance: Optional[Provenance] = None
    candidate_matches: list[dict[str, Any]] = Field(default_factory=list)


class MSMEValuationDocument(BaseModel):
    """Domain output model for MSME valuation (47 target fields)."""
    schema_version: str = "v0"
    document_id: str
    company_name: Optional[str] = None
    financial_year: Optional[str] = None
    reporting_currency: Optional[str] = None
    unit: Optional[str] = None
    fields: dict[str, MSMEFieldResult] = Field(default_factory=dict)
    completion_rate: float = 0.0
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
