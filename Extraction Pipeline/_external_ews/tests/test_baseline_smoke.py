"""Smoke test for baseline PDF extraction pipeline.

Runs the current baseline extraction pipeline against the committed sample PDF fixture
'cfac411d-76f4-45b4-9c7c-fdcf7508e7fc.pdf' to ensure PDF parsing, SQLite master data,
section consolidation, taxonomy classification, and table detection complete cleanly.
"""

import sys
import os
from pathlib import Path

# Add project root and graph to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GRAPH_DIR = PROJECT_ROOT / "graph"

for p in (str(PROJECT_ROOT), str(GRAPH_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from sources.annual_report.extraction_pipeline import run_full_extraction


def test_baseline_extraction_smoke():
    sample_pdf = PROJECT_ROOT / "cfac411d-76f4-45b4-9c7c-fdcf7508e7fc.pdf"
    assert sample_pdf.exists(), f"Sample PDF fixture not found at {sample_pdf}"

    print(f"\nRunning baseline extraction smoke test on {sample_pdf.name}...")
    result = run_full_extraction(
        pdf_path=sample_pdf,
        use_llm_taxonomy=False,  # Keyword/heuristic taxonomy for fast smoke test
    )

    assert result is not None, "Extraction returned None"
    assert "metadata" in result, "Missing metadata in extraction result"
    assert result["metadata"].get("page_count", 0) > 0, "Page count should be > 0"
    assert "master_sections" in result, "Missing master_sections in extraction result"
    assert len(result["master_sections"]) > 0, "Master sections should not be empty"
    assert "table_inventory" in result, "Missing table_inventory"
    assert "document_registry" in result, "Missing document_registry"
    assert "quality_report" in result, "Missing quality_report"

    print(f"Smoke test passed! Pages: {result['metadata']['page_count']}, "
          f"Master sections: {len(result['master_sections'])}, "
          f"Tables detected: {len(result['table_inventory'])}")


if __name__ == "__main__":
    test_baseline_extraction_smoke()
