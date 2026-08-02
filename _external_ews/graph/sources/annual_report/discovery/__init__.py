"""Discovery sub-package for financial statement page identification.

This package replaces the legacy word-position-clustering page
identification with a robust, multi-stage pipeline:

  Stage 0  — Document Classification  (``classifier.py``)
  Stage 1  — Unified PDF Parsing      (``parser.py``)
  Stage 3  — Candidate Page Generation (``candidates.py``)
  Stage 4  — Confidence Scoring        (``scoring.py``)
  Stage 7  — Sequence Validation       (``validation.py``)
  Stage 9  — Screenshot Extraction     (``extraction.py``)
  Pipeline — Orchestrator              (``pipeline.py``)

Stages 2 (OCR), 5/8 (Layout Analysis), and 6 (Embeddings) are ON HOLD.
Stage 10 (VLM) is the existing ``vlm_extractor.py`` — untouched.
"""

from .models import (
    DocumentType,
    StatementType,
    PageType,
    DocumentInfo,
    PageInfo,
    Candidate,
    ScoreBreakdown,
    StatementPages,
    DiscoveryResult,
)
from .pipeline import run_discovery

__all__ = [
    "DocumentType",
    "StatementType",
    "PageType",
    "DocumentInfo",
    "PageInfo",
    "Candidate",
    "ScoreBreakdown",
    "StatementPages",
    "DiscoveryResult",
    "run_discovery",
]
