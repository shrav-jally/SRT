"""Unit tests for Custom Extraction Spec Engine (Product 2)."""

import json
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from contracts import (
    CanonicalDocument,
    CanonicalSection,
    CustomExtractionFieldSpec,
    CustomExtractionResultDocument,
    CustomExtractionSpecDocument,
    ExtractionStatus,
    FieldExtractionMode,
    FieldValueType,
    SourceMetadata,
    DocumentMetadata,
)
from extractors.custom_spec import extract_from_custom_spec, load_custom_spec


def test_custom_spec_model_and_execution():
    # 1. Create a sample CanonicalDocument
    doc = CanonicalDocument(
        document_id="doc_test_spec_001",
        source_metadata=SourceMetadata(file_name="test.pdf", page_count=5),
        document_metadata=DocumentMetadata(company_name="Acme Steel Ltd", financial_year="2024-25"),
        sections=[
            CanonicalSection(
                section_id="sec_001",
                title_raw="Board of Directors",
                title_normalized="board_of_directors",
                section_type="governance",
                subcategory="board_of_directors",
                start_page=2,
                end_page=3,
            )
        ],
        processing_metadata={
            "raw_extractions": {
                "Company Information": {
                    "Company Profile": "Acme Steel Ltd is a leading steel manufacturing company incorporated in 1995."
                },
                "Management & Governance": {
                    "Board of Directors": [
                        {"name": "Raj Kumar", "designation": "Chairman", "din": "00012345"},
                        {"name": "Priya Sharma", "designation": "Executive Director"},
                    ]
                },
            },
            "raw_evidence_map": {
                "Board of Directors": {
                    "source_page": 2,
                    "source_section": "Board of Directors",
                    "confidence": 0.95,
                    "source_text_snippet": "DIN: 00012345 | Raj Kumar | Chairman",
                }
            },
        },
    )

    # 2. Create CustomExtractionSpecDocument
    spec = CustomExtractionSpecDocument(
        spec_id="spec_test_001",
        fields=[
            CustomExtractionFieldSpec(
                field_id="company_name",
                category="Financial Data",
                subcategory="Company Profile",
                entity_name="Company Legal Name",
                entity_type="text_fact",
                description="Legal name of company",
                extraction_mode=FieldExtractionMode.DIRECT_MAPPING,
                synonyms=["company profile", "acme steel"],
            ),
            CustomExtractionFieldSpec(
                field_id="board_members",
                category="Management & Governance",
                subcategory="Board of Directors",
                entity_name="Board of Directors",
                entity_type="list",
                description="List of board members",
                extraction_mode=FieldExtractionMode.DIRECT_MAPPING,
                synonyms=["directors"],
            ),
            CustomExtractionFieldSpec(
                field_id="future_outlook",
                category="Management & Governance",
                subcategory="Board of Directors",
                entity_name="Future Strategy",
                entity_type="string",
                description="Future strategic guidance",
                extraction_mode=FieldExtractionMode.INFERENCE_BASED,
                expected_section_types=["governance"],
            ),
        ],
    )

    # 3. Execute extraction
    result_doc = extract_from_custom_spec(doc, spec)

    assert result_doc.document_id == "doc_test_spec_001"
    assert len(result_doc.results) == 3

    # Check direct mapping result 1
    res1 = next(r for r in result_doc.results if r.field_id == "company_name")
    assert res1.status == ExtractionStatus.FOUND
    assert "Acme Steel" in str(res1.value_raw)

    # Check direct mapping result 2
    res2 = next(r for r in result_doc.results if r.field_id == "board_members")
    assert res2.status == ExtractionStatus.FOUND
    assert res2.provenance[0].page_number == 2

    # Check summary
    assert result_doc.summary["total_fields_requested"] == 3
    assert result_doc.summary["fields_found"] >= 2


if __name__ == "__main__":
    test_custom_spec_model_and_execution()
    print("CUSTOM SPEC UNIT TESTS PASSED!")
