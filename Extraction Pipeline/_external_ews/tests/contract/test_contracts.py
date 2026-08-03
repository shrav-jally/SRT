"""Contract tests for versioned Pydantic contracts (Phase 1)."""

import json
import sys
from decimal import Decimal
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from contracts import (
    BoundingBox,
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
    ExtractionStatus,
    FinancialLineItem,
    FinancialStatementTable,
    FinancialStatementsDocument,
    MSMEFieldResult,
    MSMEValuationDocument,
    PeriodValue,
    Provenance,
    SourceMetadata,
    SourceReference,
    TaxonomyDocument,
    TaxonomyNode,
    ValidationIssue,
    ValidationStatus,
)
from contracts.export_schemas import export_json_schemas


def test_canonical_document_creation_and_serialization():
    # 1. Create tokens
    tok1 = CanonicalToken(
        token_id="p1_t001",
        page_number=1,
        text="Balance",
        bbox=BoundingBox(x0=100.0, y0=50.0, x1=150.0, y1=65.0),
        reading_order_index=0,
        font_name="Helvetica-Bold",
        font_size=14.0,
        is_bold=True,
    )
    tok2 = CanonicalToken(
        token_id="p1_t002",
        page_number=1,
        text="Sheet",
        bbox=BoundingBox(x0=155.0, y0=50.0, x1=200.0, y1=65.0),
        reading_order_index=1,
        font_name="Helvetica-Bold",
        font_size=14.0,
        is_bold=True,
    )

    # 2. Create cells and table
    cell1 = CanonicalCell(
        cell_id="cell_r0_c0",
        row_index=0,
        column_index=0,
        bbox=BoundingBox(x0=100.0, y0=100.0, x1=250.0, y1=120.0),
        token_ids=["p1_t001", "p1_t002"],
        raw_text="Balance Sheet",
        role="header",
    )
    table1 = CanonicalTable(
        table_id="tbl_p1_01",
        page_numbers=[1],
        bbox=BoundingBox(x0=100.0, y0=100.0, x1=500.0, y1=300.0),
        detection_method="grid_detector",
        token_ids=["p1_t001", "p1_t002"],
        rows=[CanonicalRow(row_index=0, row_id="row_0", cell_ids=["cell_r0_c0"], is_header=True, role="header")],
        columns=[CanonicalColumn(column_index=0, column_id="col_0", header_text="Particulars", role="label")],
        cells=[cell1],
        validation_status=ValidationStatus.VALIDATED,
    )

    # 3. Create section
    sec1 = CanonicalSection(
        section_id="sec_001",
        title_raw="Balance Sheet",
        title_normalized="balance_sheet",
        section_type="financial_statements",
        start_page=1,
        end_page=1,
        table_ids=["tbl_p1_01"],
    )

    # 4. Construct document
    doc = CanonicalDocument(
        document_id="doc_test_001",
        source_metadata=SourceMetadata(file_name="sample_report.pdf", page_count=10),
        document_metadata=DocumentMetadata(company_name="Acme Corp", fy_end="31 March 2025"),
        pages=[CanonicalPage(page_number=1, width=595.0, height=842.0, token_ids=["p1_t001", "p1_t002"], table_ids=["tbl_p1_01"])],
        token_registry={"p1_t001": tok1, "p1_t002": tok2},
        tables=[table1],
        sections=[sec1],
        indexes=CanonicalIndexes(
            sections_by_type={"financial_statements": ["sec_001"]},
            tables_by_page={1: ["tbl_p1_01"]},
        ),
    )

    # Serialize & Deserialize
    doc_json_str = doc.model_dump_json(indent=2)
    reconstituted = CanonicalDocument.model_validate_json(doc_json_str)

    assert reconstituted.schema_version == "v0"
    assert reconstituted.document_id == "doc_test_001"
    assert len(reconstituted.pages) == 1
    assert reconstituted.token_registry["p1_t001"].text == "Balance"
    assert reconstituted.tables[0].validation_status == ValidationStatus.VALIDATED


def test_financial_statements_contract():
    line_item = FinancialLineItem(
        line_item_id="li_rev_ops",
        canonical_name="revenue_from_operations",
        raw_label="Revenue from operations",
        note_number="2.18",
        period_values={
            "FY2025": PeriodValue(
                period_label="31 March 2025",
                raw_value="1,234.56",
                parsed_numeric=Decimal("1234.56"),
                unit="Crore",
                currency="INR",
                status=ExtractionStatus.FOUND,
                provenance=Provenance(
                    source_refs=[SourceReference(page_number=75, table_id="tbl_p75_01", row_index=3, column_index=1, raw_text="1,234.56")],
                    confidence=0.98,
                    method="geometry_grid",
                    raw_value_as_printed="1,234.56",
                ),
            )
        },
        status=ExtractionStatus.FOUND,
    )

    stmt = FinancialStatementTable(
        statement_type="profit_and_loss",
        consolidation_type="consolidated",
        title="Consolidated Statement of Profit and Loss",
        reporting_currency="INR",
        unit="Crore",
        period_labels=["31 March 2025"],
        line_items=[line_item],
        status=ExtractionStatus.FOUND,
    )

    doc = FinancialStatementsDocument(
        document_id="doc_fin_001",
        company_name="Acme Corp",
        reporting_year="FY2025",
        consolidated_statements={"profit_and_loss": stmt},
    )

    doc_json = doc.model_dump_json()
    restored = FinancialStatementsDocument.model_validate_json(doc_json)

    assert restored.document_id == "doc_fin_001"
    item = restored.consolidated_statements["profit_and_loss"].line_items[0]
    assert item.canonical_name == "revenue_from_operations"
    val = item.period_values["FY2025"]
    assert val.status == ExtractionStatus.FOUND
    assert val.parsed_numeric == Decimal("1234.56")
    assert val.provenance.source_refs[0].page_number == 75


def test_msme_valuation_contract():
    rev_field = MSMEFieldResult(
        field_name="revenue_from_operations",
        category="Profitability",
        required_by_msme=True,
        current_period_value=PeriodValue(
            period_label="31 March 2025",
            raw_value="5,000.00",
            parsed_numeric=Decimal("5000.00"),
            unit="Lakh",
            currency="INR",
            status=ExtractionStatus.FOUND,
        ),
        status=ExtractionStatus.FOUND,
    )

    ebitda_field = MSMEFieldResult(
        field_name="ebitda",
        category="Profitability",
        required_by_msme=False,
        is_derived=True,
        calculation_formula="profit_before_tax + finance_costs + depreciation",
        current_period_value=PeriodValue(
            period_label="31 March 2025",
            raw_value="1,200.00",
            parsed_numeric=Decimal("1200.00"),
            unit="Lakh",
            currency="INR",
            status=ExtractionStatus.FOUND,
        ),
        status=ExtractionStatus.FOUND,
    )

    doc = MSMEValuationDocument(
        document_id="doc_msme_001",
        company_name="Acme MSME Ltd",
        financial_year="2024-25",
        fields={
            "revenue_from_operations": rev_field,
            "ebitda": ebitda_field,
        },
        completion_rate=1.0,
    )

    doc_json = doc.model_dump_json()
    restored = MSMEValuationDocument.model_validate_json(doc_json)

    assert restored.fields["revenue_from_operations"].status == ExtractionStatus.FOUND
    assert restored.fields["ebitda"].is_derived is True
    assert restored.fields["ebitda"].calculation_formula == "profit_before_tax + finance_costs + depreciation"


def test_json_schema_exports():
    exported = export_json_schemas()
    assert len(exported) >= 4
    for name, path in exported.items():
        assert path.exists()
        with open(path, "r", encoding="utf-8") as f:
            schema_data = json.load(f)
            assert "title" in schema_data or "properties" in schema_data


if __name__ == "__main__":
    test_canonical_document_creation_and_serialization()
    test_financial_statements_contract()
    test_msme_valuation_contract()
    test_json_schema_exports()
    print("ALL CONTRACT TESTS PASSED!")
