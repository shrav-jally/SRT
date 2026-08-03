"""Common types and enums for versioned contracts."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field


class ExtractionStatus(str, Enum):
    """Explicit extraction status for every domain field.
    
    NEVER use null alone to represent missing fields.
    """
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    AMBIGUOUS = "AMBIGUOUS"
    FAILED_VALIDATION = "FAILED_VALIDATION"


class ValidationStatus(str, Enum):
    """Validation status for table reconstruction and numeric alignment."""
    NOT_RUN = "NOT_RUN"
    VALIDATED = "VALIDATED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class BoundingBox(BaseModel):
    """Normalized or absolute coordinate bounding box [x0, y0, x1, y1]."""
    x0: float
    y0: float
    x1: float
    y1: float


class SourceReference(BaseModel):
    """Fine-grained atomic reference to source tokens, pages, tables, and cells."""
    document_id: Optional[str] = None
    page_number: int
    section_id: Optional[str] = None
    table_id: Optional[str] = None
    row_index: Optional[int] = None
    column_index: Optional[int] = None
    cell_id: Optional[str] = None
    token_ids: list[str] = Field(default_factory=list)
    raw_text: Optional[str] = None


class Provenance(BaseModel):
    """Complete provenance and evidence record attached to every emitted domain value."""
    source_refs: list[SourceReference] = Field(default_factory=list)
    confidence: Optional[float] = None
    method: Optional[str] = None
    raw_value_as_printed: Optional[str] = None
    parsed_numeric: Optional[Decimal] = None
    unit: Optional[str] = None
    currency: Optional[str] = None
    note_reference: Optional[str] = None


class ConfidenceMetadata(BaseModel):
    """Model confidence score and method metadata."""
    score: float
    method: Optional[str] = None
    model_name: Optional[str] = None


class ValidationIssue(BaseModel):
    """Structured validation diagnostic issue."""
    issue_id: Optional[str] = None
    issue_type: str
    severity: Literal["info", "warning", "error"] = "warning"
    description: str
    location: Optional[SourceReference] = None
