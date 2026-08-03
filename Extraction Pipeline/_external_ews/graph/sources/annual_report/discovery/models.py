"""Data models for the financial statement page discovery pipeline.

Defines the core dataclasses used across all discovery stages:
  - ``DocumentInfo``  — PDF-level classification and metadata
  - ``PageInfo``      — per-page parsed information
  - ``Candidate``     — a candidate page for a specific statement type
  - ``ScoreBreakdown``— detailed confidence score components
  - ``StatementPages``— final resolved pages for one financial statement
  - ``DiscoveryResult``— the complete output of the discovery pipeline
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# ===================================================================
# Enums
# ===================================================================

class DocumentType(str, Enum):
    """Classification of the PDF document type."""
    TEXT = "text"             # Fully searchable, digitally created
    SCANNED = "scanned"      # Image-only pages requiring OCR
    HYBRID = "hybrid"        # Mix of text and scanned pages
    UNKNOWN = "unknown"


class StatementType(str, Enum):
    """The six financial statement types we target."""
    STANDALONE_BALANCE_SHEET = "standalone_balance_sheet"
    STANDALONE_PROFIT_AND_LOSS = "standalone_profit_and_loss"
    STANDALONE_CASH_FLOW = "standalone_cash_flow"
    CONSOLIDATED_BALANCE_SHEET = "consolidated_balance_sheet"
    CONSOLIDATED_PROFIT_AND_LOSS = "consolidated_profit_and_loss"
    CONSOLIDATED_CASH_FLOW = "consolidated_cash_flow"


class PageType(str, Enum):
    """Broad classification of a single page's content."""
    TEXT = "text"
    IMAGE = "image"
    MIXED = "mixed"
    BLANK = "blank"


# Helper sets
STANDALONE_TYPES = frozenset({
    StatementType.STANDALONE_BALANCE_SHEET,
    StatementType.STANDALONE_PROFIT_AND_LOSS,
    StatementType.STANDALONE_CASH_FLOW,
})
CONSOLIDATED_TYPES = frozenset({
    StatementType.CONSOLIDATED_BALANCE_SHEET,
    StatementType.CONSOLIDATED_PROFIT_AND_LOSS,
    StatementType.CONSOLIDATED_CASH_FLOW,
})
ALL_STATEMENT_TYPES = frozenset(StatementType)

# Logical order for sequence validation
STATEMENT_ORDER = [
    StatementType.STANDALONE_BALANCE_SHEET,
    StatementType.STANDALONE_PROFIT_AND_LOSS,
    StatementType.STANDALONE_CASH_FLOW,
    StatementType.CONSOLIDATED_BALANCE_SHEET,
    StatementType.CONSOLIDATED_PROFIT_AND_LOSS,
    StatementType.CONSOLIDATED_CASH_FLOW,
]


# ===================================================================
# Stage 0 — Document Classification
# ===================================================================

@dataclass
class DocumentInfo:
    """PDF-level metadata and classification (Stage 0 output)."""
    file_path: Path
    file_name: str
    page_count: int
    document_type: DocumentType = DocumentType.UNKNOWN
    ocr_required: bool = False
    total_chars: int = 0
    low_text_pages: int = 0
    low_text_page_numbers: list[int] = field(default_factory=list)
    confidence: float = 0.0
    financial_year: str | None = None


# ===================================================================
# Stage 1 — Unified PDF Parser
# ===================================================================

@dataclass
class FontInfo:
    """Aggregated font statistics for a page."""
    dominant_font: str = ""
    dominant_size: float = 0.0
    font_count: int = 0
    has_bold: bool = False
    largest_size: float = 0.0


@dataclass
class PageInfo:
    """Comprehensive per-page information (Stage 1 output).

    Combines data from pdfplumber + PyMuPDF into a single object
    that downstream stages can query without re-opening the PDF.
    """
    page_number: int
    raw_text: str = ""
    char_count: int = 0
    word_count: int = 0
    line_count: int = 0
    page_width: float = 0.0
    page_height: float = 0.0
    rotation: int = 0
    page_type: PageType = PageType.TEXT
    is_corrupted: bool = False


    # Derived metrics
    numeric_density: float = 0.0   # ratio of numeric tokens to total tokens
    amount_count: int = 0          # count of Indian-format amount patterns
    date_count: int = 0            # count of date patterns on the page
    table_density: float = 0.0     # heuristic: amount_count / max(word_count,1)

    # Font analysis
    fonts: FontInfo = field(default_factory=FontInfo)

    # Heading candidates (first N non-trivial lines)
    heading_candidates: list[str] = field(default_factory=list)

    # Image info (from PyMuPDF)
    image_count: int = 0
    is_landscape: bool = False


# ===================================================================
# Stage 3/4 — Candidate Generation & Scoring
# ===================================================================

@dataclass
class ScoreBreakdown:
    """Detailed breakdown of confidence score components."""
    heading_score: float = 0.0      # Does a heading match a statement name?
    keyword_score: float = 0.0      # Financial terminology density
    numeric_density_score: float = 0.0  # How number-heavy is the page?
    table_structure_score: float = 0.0  # Does it look like a table?
    toc_score: float = 0.0         # Was it referenced by the TOC?
    bookmark_score: float = 0.0    # Was it referenced by a PDF bookmark?
    section_heading_score: float = 0.0  # Does it have section headings (ASSETS, etc)?
    date_header_score: float = 0.0  # Does it have a date header row?
    continuation_score: float = 0.0 # Is it a continuation of a prev page?
    vlm_score: float = 0.0         # Did the VLM identify this page?

    @property
    def total(self) -> float:
        """Weighted total confidence score (0.0 – 1.0)."""
        weights = {
            "vlm_score": 0.75,
            "heading_score": 0.25,
            "keyword_score": 0.10,
            "numeric_density_score": 0.05,
            "table_structure_score": 0.10,
            "toc_score": 0.15,
            "bookmark_score": 0.15,
            "section_heading_score": 0.10,
            "date_header_score": 0.05,
            "continuation_score": 0.05,
        }
        total = sum(
            getattr(self, attr) * weight
            for attr, weight in weights.items()
        )
        return min(total, 1.0)


@dataclass
class Candidate:
    """A candidate page for a specific financial statement type."""
    statement_type: StatementType
    page_number: int
    score: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    source: str = ""        # e.g. "toc", "heading", "bookmark", "content"
    matched_features: list[str] = field(default_factory=list)
    reasoning: str = ""

    @property
    def confidence(self) -> float:
        return self.score.total


# ===================================================================
# Stage 7 — Sequence Validation / Final Output
# ===================================================================

@dataclass
class StatementPages:
    """Final resolved pages for one financial statement."""
    statement_type: StatementType
    pages: list[int] = field(default_factory=list)
    confidence: float = 0.0
    source: str = ""
    reasoning: str = ""
    is_multi_page: bool = False


@dataclass
class DiscoveryResult:
    """Complete output of the discovery pipeline.

    This is the contract between discovery and the VLM extraction stage.
    The VLM extractor reads ``statements`` to know which pages to render
    and send to the vision model.
    """
    document: DocumentInfo | None = None
    pages: list[PageInfo] = field(default_factory=list)
    statements: dict[str, StatementPages] = field(default_factory=dict)
    # Raw candidates before filtering (useful for debugging)
    all_candidates: list[Candidate] = field(default_factory=list)

    def get_pages_for(self, statement_type: str | StatementType) -> list[int]:
        """Return the resolved page numbers for a statement type."""
        key = statement_type.value if isinstance(statement_type, StatementType) else statement_type
        sp = self.statements.get(key)
        return sp.pages if sp else []

    def to_page_hints(self) -> dict[str, list[int]]:
        """Convert to the ``page_hints`` format used by the VLM extractor.

        Returns a dict like::

            {
                "standalone_balance_sheet": [54, 55],
                "consolidated_profit_and_loss": [120],
                ...
            }
        """
        return {
            key: sp.pages
            for key, sp in self.statements.items()
            if sp.pages
        }
