"""Pydantic output schemas for the Annual Report Extraction Framework.

Defines the canonical data models used across all layers:
  - PageData: raw ingested page information
  - TaxonomyMapping: category/subcategory mapping result
  - MasterSection: consolidated section from the section consolidator
  - VLMTargetItem: VLM extraction target with priority
  - DetectedTable / TableInventoryItem: table detection results
  - TextExtractionResult / TableExtractionResult: extraction outputs
  - ValidationIssue / CompletenessReport: validation output
  - SectionRegistry / TaxonomySummary / QualityReport: canonical output
  - DocumentRegistry: top-level canonical output combining all
  - FullExtractionResult: legacy top-level result (backward compat)
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ===================================================================
# Page-level models
# ===================================================================

class PageData(BaseModel):
    """Single page extracted from a PDF."""
    page_number: int
    raw_text: str = ""
    detected_heading: str = ""
    section_name: str = ""
    confidence: float = 0.0


# ===================================================================
# Taxonomy and Section models
# ===================================================================

class TaxonomyMapping(BaseModel):
    """A mapping of content to a taxonomy category/subcategory (page-level)."""
    section_type: str = ""
    section_subtype: str = ""
    category: str
    subcategory: str
    source_pages: list[int] = Field(default_factory=list)
    extracted_text: str = ""
    extraction_method: str = "text"  # "text" | "vlm"
    confidence: float = 0.0

class MasterSection(BaseModel):
    """A contiguous block of pages representing a single section."""
    section_id: str
    section_name: str
    section_type: str = ""
    section_subtype: str = ""
    category: str
    subcategory: str = ""       # Leaf-level taxonomy subcategory
    start_page: int
    end_page: int
    content_type: str  # "table", "text", "mixed"
    extraction_strategy: str  # "vlm", "pdf_text", "hybrid"
    confidence: float = 0.0
    section_status: str = "confirmed"  # "confirmed", "inferred", "low_confidence"
    boundary_source: str = "classifier" # "toc", "heading", "classifier"
    source: str = "taxonomy"    # "toc" | "taxonomy" | "merged"
    toc_entry: Optional[str] = None  # Original TOC description if available
    page_count: int = 0         # end_page - start_page + 1

# ===================================================================
# VLM Target models
# ===================================================================

class VLMTargetItem(BaseModel):
    """A single VLM extraction target derived from the section registry."""
    section_id: str
    section_name: str
    priority: str  # "high" | "medium" | "low"
    table_category: str  # "financial_statement" | "kpi_table" | etc.
    page_range: list[int] = Field(default_factory=list)  # [start, end]
    extraction_prompt: str = ""
    estimated_pages: int = 0
    content_type: str = "text"
    section_type: str = ""
    section_subtype: str = ""
    category: str = ""
    confidence: float = 0.0
    table_type: str = ""


# ===================================================================
# Table detection models
# ===================================================================

class DetectedTable(BaseModel):
    """A detected table on a page (internal use)."""
    table_type: str
    page_number: int
    detection_confidence: float = 0.0
    needs_vlm: bool = False
    numeric_density: float = 0.0
    column_count: int = 0

class TableInventoryItem(BaseModel):
    """Formalized inventory item for a detected table."""
    table_id: str
    table_name: str
    table_category: str = "other"          # NEW: TableCategory value
    page_no: int
    complexity_score: float = 0.0
    needs_vlm: bool = False
    parent_section_id: Optional[str] = None  # NEW: Link to section registry


# ===================================================================
# Extraction output models
# ===================================================================

class TextExtractionResult(BaseModel):
    """Extracted text chunk mapped to taxonomy."""
    section_type: str = ""
    section_subtype: str = ""
    category: str
    subcategory: str
    extracted_text: str
    source_pages: list[int] = Field(default_factory=list)
    extraction_method: str = "text"
    confidence: float = 0.0
    needs_review: bool = False


class TableExtractionResult(BaseModel):
    """Extracted structured table."""
    table_name: str
    source_page: int
    extraction_method: str = "pdfplumber"  # "pdfplumber" | "vlm"
    table_json: Any = None  # dict or list representing the table
    confidence: float = 0.0
    needs_review: bool = False


# ===================================================================
# Validation models
# ===================================================================

class ValidationIssue(BaseModel):
    """A single validation issue found during the completeness check."""
    issue_type: str  # "missing_section" | "duplicate_mapping" | "incomplete_table" | "low_confidence"
    severity: str = "warning"  # "info" | "warning" | "error"
    description: str = ""
    category: str = ""
    subcategory: str = ""
    page: Optional[int] = None


class CompletenessReport(BaseModel):
    """Full completeness/validation report."""
    total_pages: int = 0
    pages_classified: int = 0
    categories_found: int = 0
    categories_expected: int = 17
    tables_detected: int = 0
    tables_extracted: int = 0
    issues: list[ValidationIssue] = Field(default_factory=list)
    coverage_pct: float = 0.0
    overall_confidence: float = 0.0


# ===================================================================
# Canonical Output Models (Phase 4)
# ===================================================================

class SectionRegistry(BaseModel):
    """Hierarchical section registry — the primary output of section consolidation."""
    total_sections: int = 0
    toc_sections: int = 0               # Sections derived from TOC
    taxonomy_sections: int = 0          # Sections derived from taxonomy only
    merged_sections: int = 0            # Sections that merged TOC + taxonomy
    hierarchy: dict[str, Any] = Field(default_factory=dict)  # category → children
    flat: list[MasterSection] = Field(default_factory=list)  # Flat list for backward compat


class TableInventorySummary(BaseModel):
    """Classified table inventory summary."""
    total_tables: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)  # table_category → count
    vlm_required: int = 0
    all_items: list[TableInventoryItem] = Field(default_factory=list)


class TaxonomySummary(BaseModel):
    """Summarised taxonomy — replaces raw 335 per-page mappings as primary output."""
    categories_found: list[str] = Field(default_factory=list)
    coverage_pct: float = 0.0
    total_page_mappings: int = 0        # Raw count (still available but not primary)
    page_mappings: list[TaxonomyMapping] = Field(default_factory=list)


class QualityReport(BaseModel):
    """Extraction quality metrics — composite score and component breakdown."""
    section_consolidation_ratio: float = 0.0  # e.g., 335 → 72 = 0.215
    toc_coverage_pct: float = 0.0             # % of sections anchored by TOC
    taxonomy_coverage_pct: float = 0.0        # % of pages classified
    table_false_positive_rate: float = 0.0    # Estimated FP rate
    vlm_target_count: int = 0
    high_priority_vlm_targets: int = 0
    medium_priority_vlm_targets: int = 0
    issues: list[ValidationIssue] = Field(default_factory=list)
    overall_score: float = 0.0                # 0-10 composite score


class DocumentRegistry(BaseModel):
    """Canonical output schema for the extraction pipeline.

    This is the structured, production-ready output that replaces the
    flat dict previously returned by the pipeline. All downstream
    consumers should use this schema.
    """
    metadata: dict[str, Any] = Field(default_factory=dict)
    section_registry: SectionRegistry = Field(default_factory=SectionRegistry)
    table_inventory: TableInventorySummary = Field(default_factory=TableInventorySummary)
    taxonomy: TaxonomySummary = Field(default_factory=TaxonomySummary)
    extractions: dict[str, Any] = Field(default_factory=dict)  # text + table extractions
    quality_report: QualityReport = Field(default_factory=QualityReport)
    vlm_targets: list[VLMTargetItem] = Field(default_factory=list)
    structured_intelligence: dict[str, Any] = Field(default_factory=dict)

    # Legacy compatibility — financial statements in the old format
    standalone: dict[str, Any] = Field(default_factory=dict)
    consolidated: dict[str, Any] = Field(default_factory=dict)


# ===================================================================
# Top-level result (legacy — kept for backward compatibility)
# ===================================================================

class FullExtractionResult(BaseModel):
    """Complete extraction result from the full pipeline (legacy format)."""
    metadata: dict[str, Any] = Field(default_factory=dict)
    master_sections: list[MasterSection] = Field(default_factory=list)
    table_inventory: list[TableInventoryItem] = Field(default_factory=list)
    taxonomy_mappings: list[TaxonomyMapping] = Field(default_factory=list)
    text_extractions: list[TextExtractionResult] = Field(default_factory=list)
    table_extractions: list[TableExtractionResult] = Field(default_factory=list)
    validation_report: Optional[CompletenessReport] = None
    structured_intelligence: dict[str, Any] = Field(default_factory=dict)

    # Legacy compatibility — financial statements in the old format
    standalone: dict[str, Any] = Field(default_factory=dict)
    consolidated: dict[str, Any] = Field(default_factory=dict)
