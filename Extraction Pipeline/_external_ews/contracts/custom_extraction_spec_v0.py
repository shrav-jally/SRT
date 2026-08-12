"""Custom Extraction Spec Contract v0.

Defines user-configurable field specs and structured result schemas
for Product 2 (Generic Schema-Driven Extractor).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

from .common import ExtractionStatus, Provenance, SourceReference, ValidationStatus


class FieldExtractionMode(str, Enum):
    """Supported extraction resolution modes."""
    DIRECT_MAPPING = "DIRECT_MAPPING"
    INFERENCE_BASED = "INFERENCE_BASED"
    DERIVED = "DERIVED"


class FieldValueType(str, Enum):
    """Expected data type for field values."""
    STRING = "string"
    NUMBER = "number"
    CURRENCY_AMOUNT = "currency_amount"
    INTEGER = "integer"
    COUNT = "count"
    DATE = "date"
    TABLE = "table"
    LIST = "list"
    BOOLEAN = "boolean"


class CustomExtractionFieldSpec(BaseModel):
    """Specification for a single user-requested extraction field."""
    field_id: str
    category: str
    subcategory: str
    entity_name: str
    entity_type: str = "metric"
    description: str
    extraction_mode: FieldExtractionMode = FieldExtractionMode.DIRECT_MAPPING
    synonyms: list[str] = Field(default_factory=list)
    expected_section_types: list[str] = Field(default_factory=list)
    expected_value_type: FieldValueType = FieldValueType.STRING
    required: bool = True
    output_cardinality: Literal["single", "multi", "table", "list"] = "single"
    notes: Optional[str] = None


class CustomExtractionSpecDocument(BaseModel):
    """A document containing a list of requested custom field specifications."""
    spec_id: str = "custom_spec_v0"
    spec_name: str = "Custom Extraction Specification"
    version: str = "v0"
    fields: list[CustomExtractionFieldSpec] = Field(default_factory=list)


class CustomExtractionResult(BaseModel):
    """Structured extraction result for a single requested custom field."""
    field_id: str
    category: str
    subcategory: str
    entity_name: str
    entity_type: str
    extraction_mode: FieldExtractionMode
    status: ExtractionStatus = ExtractionStatus.NOT_FOUND
    value_raw: Optional[Any] = None
    value_normalized: Optional[Any] = None
    unit: Optional[str] = None
    currency: Optional[str] = None
    confidence: float = 0.0
    explanation: Optional[str] = None
    provenance: list[SourceReference] = Field(default_factory=list)
    validation_status: ValidationStatus = ValidationStatus.NOT_RUN
    other_candidates: Optional[list[dict[str, Any]]] = Field(default_factory=list)


class CustomExtractionResultDocument(BaseModel):
    """Complete result document containing extracted values for all requested fields."""
    document_id: str
    spec_id: str
    results: list[CustomExtractionResult] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
