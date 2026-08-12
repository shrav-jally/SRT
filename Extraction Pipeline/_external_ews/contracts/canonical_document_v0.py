"""CanonicalDocument Contract v0 — Product 1 output specification.

This model forms the lossless intermediate document representation emitted by Product 1 (Canonicalizer).
Domain Extractors (Product 2) consume this document only and MUST NEVER access raw PDF files.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

from .common import BoundingBox, ValidationIssue, ValidationStatus


class SourceMetadata(BaseModel):
    """File ingestion provenance and raw document properties."""
    file_name: str
    file_hash: Optional[str] = None
    file_size_bytes: int = 0
    page_count: int = 0
    creation_date: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    producer: Optional[str] = None


class DocumentMetadata(BaseModel):
    """High-level document metadata inferred from canonical tokens and sections."""
    company_name: Optional[str] = None
    reporting_period: Optional[str] = None
    fy_end: Optional[str] = None
    currency: Optional[str] = None
    unit_denomination: Optional[str] = None
    consolidation_type: Optional[Literal["standalone", "consolidated", "both", "unknown"]] = "unknown"
    auditor_name: Optional[str] = None
    auditor_opinion: Optional[str] = None


class CanonicalToken(BaseModel):
    """Atomic text token extracted from PDF primitive text layer."""
    token_id: str
    page_number: int
    text: str
    bbox: BoundingBox
    reading_order_index: Optional[int] = None
    font_name: Optional[str] = None
    font_size: Optional[float] = None
    is_bold: Optional[bool] = None
    is_italic: Optional[bool] = None
    color: Optional[str] = None


class CanonicalBlock(BaseModel):
    """Layout block grouping primitive tokens (heading, paragraph, table, list, etc.)."""
    block_id: str
    page_number: int
    block_type: Literal[
        "heading", "paragraph", "table",
        "figure", "list", "footnote", "other"
    ]
    bbox: BoundingBox
    token_ids: list[str] = Field(default_factory=list)
    table_id: Optional[str] = None
    section_id: Optional[str] = None
    reading_order_index: int = 0
    confidence: Optional[float] = None


class CanonicalCell(BaseModel):
    """Grid cell within a CanonicalTable."""
    cell_id: str
    row_index: int
    column_index: int
    bbox: BoundingBox
    token_ids: list[str] = Field(default_factory=list)
    raw_text: str = ""
    numeric_token_ids: list[str] = Field(default_factory=list)
    parsed_numeric: Optional[Decimal] = None
    rowspan: int = 1
    colspan: int = 1
    role: Literal[
        "header", "data", "subtotal", "total", "note", "unknown"
    ] = "unknown"


class CanonicalRow(BaseModel):
    """Row structure within a CanonicalTable."""
    row_index: int
    row_id: str
    cell_ids: list[str] = Field(default_factory=list)
    is_header: bool = False
    role: Literal["header", "data", "subtotal", "total", "note", "unknown"] = "unknown"


class CanonicalColumn(BaseModel):
    """Column structure within a CanonicalTable."""
    column_index: int
    column_id: str
    header_text: str = ""
    role: Literal["label", "numeric", "note", "unknown"] = "unknown"


class CanonicalTable(BaseModel):
    """Structured table extracted from bounding box regions."""
    table_id: str
    page_numbers: list[int] = Field(default_factory=list)
    bbox: BoundingBox
    source_block_id: Optional[str] = None
    is_borderless: Optional[bool] = None
    detection_method: str
    structure_method: Optional[str] = None
    token_ids: list[str] = Field(default_factory=list)
    rows: list[CanonicalRow] = Field(default_factory=list)
    columns: list[CanonicalColumn] = Field(default_factory=list)
    cells: list[CanonicalCell] = Field(default_factory=list)
    validation_status: ValidationStatus = ValidationStatus.NOT_RUN
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    confidence: Optional[float] = None


class CanonicalSection(BaseModel):
    """Logical document section boundary."""
    section_id: str
    title_raw: str
    title_normalized: str
    section_type: str = "other"
    subcategory: str = ""
    parent_section_id: Optional[str] = None
    child_section_ids: list[str] = Field(default_factory=list)
    start_page: int
    end_page: int
    block_ids: list[str] = Field(default_factory=list)
    table_ids: list[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    taxonomy_path: Optional[str] = None


class CanonicalPage(BaseModel):
    """Page-level container and token index."""
    page_number: int
    width: float
    height: float
    rotation: int = 0
    token_ids: list[str] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)
    section_ids: list[str] = Field(default_factory=list)
    table_ids: list[str] = Field(default_factory=list)


class TableValidation(BaseModel):
    """Numeric token reconciliation for reconstructed tables."""
    table_id: str
    status: ValidationStatus
    expected_numeric_tokens: list[str] = Field(default_factory=list)
    extracted_numeric_tokens: list[str] = Field(default_factory=list)
    missing_tokens: list[str] = Field(default_factory=list)
    extra_tokens: list[str] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)


class CanonicalIndexes(BaseModel):
    """Lookups and inverted indexes for Product 2 domain extractors."""
    sections_by_type: dict[str, list[str]] = Field(default_factory=dict)
    table_ids_by_section_id: dict[str, list[str]] = Field(default_factory=dict)
    blocks_by_page: dict[int, list[str]] = Field(default_factory=dict)
    token_ids_by_page: dict[int, list[str]] = Field(default_factory=dict)
    tables_by_page: dict[int, list[str]] = Field(default_factory=dict)
    normalized_title_to_section_ids: dict[str, list[str]] = Field(default_factory=dict)
    note_number_to_section_ids: dict[str, list[str]] = Field(default_factory=dict)


class CanonicalDocument(BaseModel):
    """Canonical document contract v0.
    
    The sole input format for all Product 2 domain extractors.
    """
    schema_version: str = "v0"
    document_id: str
    source_metadata: SourceMetadata
    document_metadata: DocumentMetadata
    pages: list[CanonicalPage] = Field(default_factory=list)
    token_registry: dict[str, CanonicalToken] = Field(default_factory=dict)
    blocks: list[CanonicalBlock] = Field(default_factory=list)
    tables: list[CanonicalTable] = Field(default_factory=list)
    sections: list[CanonicalSection] = Field(default_factory=list)
    indexes: CanonicalIndexes = Field(default_factory=CanonicalIndexes)
    processing_metadata: dict[str, Any] = Field(default_factory=dict)
    errors_and_warnings: list[ValidationIssue] = Field(default_factory=list)
