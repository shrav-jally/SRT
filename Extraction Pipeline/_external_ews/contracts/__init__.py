"""Enterprise Annual Report Extraction Framework — Versioned Contracts v0.

This package defines the strict Pydantic v2 schemas and common types for:
1. Product 1: CanonicalDocument v0 (Intermediate Representation)
2. Product 2: Domain Extraction Contracts (Financial Statements v0, MSME Valuation v0, Taxonomy Output v0)
"""

from .common import (
    BoundingBox,
    ConfidenceMetadata,
    ExtractionStatus,
    Provenance,
    SourceReference,
    ValidationIssue,
    ValidationStatus,
)
from .canonical_document_v0 import (
    CanonicalBlock,
    CanonicalCell,
    CanonicalColumn,
    CanonicalDocument,
    CanonicalIndexes,
    CanonicalPage,
    CanonicalRow,
    CanonicalSection,
    CanonicalTable,
    CanonicalToken,
    DocumentMetadata,
    SourceMetadata,
    TableValidation,
)
from .financial_statements_v0 import (
    FinancialLineItem,
    FinancialStatementTable,
    FinancialStatementsDocument,
    PeriodValue,
)
from .msme_valuation_v0 import (
    MSMEFieldResult,
    MSMEValuationDocument,
)
from .taxonomy_output_v0 import (
    TaxonomyDocument,
    TaxonomyNode,
)
from .custom_extraction_spec_v0 import (
    CustomExtractionFieldSpec,
    CustomExtractionResult,
    CustomExtractionResultDocument,
    CustomExtractionSpecDocument,
    FieldExtractionMode,
    FieldValueType,
)

__all__ = [
    # Common
    "ExtractionStatus",
    "ValidationStatus",
    "BoundingBox",
    "SourceReference",
    "Provenance",
    "ConfidenceMetadata",
    "ValidationIssue",
    # Canonical Document
    "SourceMetadata",
    "DocumentMetadata",
    "CanonicalToken",
    "CanonicalBlock",
    "CanonicalCell",
    "CanonicalRow",
    "CanonicalColumn",
    "CanonicalTable",
    "CanonicalSection",
    "CanonicalPage",
    "TableValidation",
    "CanonicalIndexes",
    "CanonicalDocument",
    # Financial Statements
    "PeriodValue",
    "FinancialLineItem",
    "FinancialStatementTable",
    "FinancialStatementsDocument",
    # MSME Valuation
    "MSMEFieldResult",
    "MSMEValuationDocument",
    # Taxonomy
    "TaxonomyNode",
    "TaxonomyDocument",
    # Custom Spec
    "FieldExtractionMode",
    "FieldValueType",
    "CustomExtractionFieldSpec",
    "CustomExtractionSpecDocument",
    "CustomExtractionResult",
    "CustomExtractionResultDocument",
]
