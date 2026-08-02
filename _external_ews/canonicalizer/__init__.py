"""Canonicalizer Package — Product 1 Engine.

Adapts PDF ingestion, section registry, taxonomy, and table inventory into a lossless CanonicalDocument v0.
"""

from .service import canonicalize_pdf
from .persistence import save_canonical_document, load_canonical_document

__all__ = ["canonicalize_pdf", "save_canonical_document", "load_canonical_document"]
