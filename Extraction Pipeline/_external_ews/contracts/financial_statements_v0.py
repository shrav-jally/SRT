"""Financial Statements Contract v0 — Domain Extractor output model.

Describes structured Balance Sheet, Profit and Loss, and Cash Flow statements
extracted strictly from a CanonicalDocument v0.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, Field

from .common import ExtractionStatus, Provenance, ValidationIssue


class PeriodValue(BaseModel):
    """Extracted financial value for a single reporting period (e.g. FY25, FY24)."""
    period_label: str
    raw_value: str
    parsed_numeric: Optional[Decimal] = None
    unit: Optional[str] = None
    currency: Optional[str] = None
    status: ExtractionStatus = ExtractionStatus.NOT_FOUND
    provenance: Optional[Provenance] = None


class FinancialLineItem(BaseModel):
    """Line item within a financial statement (e.g., Revenue from operations)."""
    line_item_id: str
    canonical_name: str
    raw_label: str
    note_number: Optional[str] = None
    period_values: dict[str, PeriodValue] = Field(default_factory=dict)
    status: ExtractionStatus = ExtractionStatus.NOT_FOUND
    provenance: Optional[Provenance] = None


class FinancialStatementTable(BaseModel):
    """Domain model for a complete financial statement (BS, P&L, CF)."""
    statement_type: Literal[
        "balance_sheet", "profit_and_loss",
        "cash_flow", "notes", "other"
    ]
    consolidation_type: Literal["standalone", "consolidated"]
    title: str
    reporting_currency: Optional[str] = None
    unit: Optional[str] = None
    period_labels: list[str] = Field(default_factory=list)
    line_items: list[FinancialLineItem] = Field(default_factory=list)
    status: ExtractionStatus = ExtractionStatus.NOT_FOUND
    provenance: Optional[Provenance] = None


class FinancialStatementsDocument(BaseModel):
    """Domain output model for all extracted financial statements."""
    schema_version: str = "v0"
    document_id: str
    company_name: Optional[str] = None
    reporting_year: Optional[str] = None
    standalone_statements: dict[str, FinancialStatementTable] = Field(default_factory=dict)
    consolidated_statements: dict[str, FinancialStatementTable] = Field(default_factory=dict)
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
