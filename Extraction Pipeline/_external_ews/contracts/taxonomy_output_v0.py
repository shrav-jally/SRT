"""Taxonomy Output Contract v0 — Domain Extractor output model.

Specifies structured taxonomy tree output mapped from CanonicalDocument.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class TaxonomyNode(BaseModel):
    """A node in the document taxonomy tree."""
    category_id: str
    name: str
    path: str
    description: Optional[str] = None
    confidence: Optional[float] = None
    page_spans: list[list[int]] = Field(default_factory=list)  # list of [start_page, end_page]


class TaxonomyDocument(BaseModel):
    """Domain output model for document taxonomy representation."""
    schema_version: str = "v0"
    document_id: str
    taxonomy_tree: list[TaxonomyNode] = Field(default_factory=list)
    unmapped_pages: list[int] = Field(default_factory=list)
