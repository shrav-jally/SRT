"""Generate a sample CanonicalDocument v0 JSON representation for demonstration."""

import json
import sys
from decimal import Decimal
from pathlib import Path

# Add project root to sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

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
    SourceMetadata,
    ValidationStatus,
)


def build_sample_canonical_document() -> CanonicalDocument:
    # Source metadata
    src_meta = SourceMetadata(
        file_name="reliance_annual_report_2024-25.pdf",
        file_hash="sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        file_size_bytes=15420100,
        page_count=384,
        creation_date="2025-05-15T10:30:00Z",
        title="Reliance Industries Limited Annual Report 2024-25",
        author="Reliance Industries Limited",
        producer="Adobe PDF Library 15.0",
    )

    # Document metadata
    doc_meta = DocumentMetadata(
        company_name="Reliance Industries Limited",
        reporting_period="2024-2025",
        fy_end="31 March 2025",
        currency="INR",
        unit_denomination="Crore",
        consolidation_type="consolidated",
        auditor_name="SRBC & CO LLP",
        auditor_opinion="Unqualified",
    )

    # Tokens on page 105 (Balance Sheet page)
    tokens = [
        CanonicalToken(
            token_id="p105_t001",
            page_number=105,
            text="ASSETS",
            bbox=BoundingBox(x0=54.0, y0=72.0, x1=110.0, y1=84.0),
            reading_order_index=0,
            font_name="Inter-Bold",
            font_size=12.0,
            is_bold=True,
        ),
        CanonicalToken(
            token_id="p105_t002",
            page_number=105,
            text="Property,",
            bbox=BoundingBox(x0=54.0, y0=90.0, x1=108.0, y1=100.0),
            reading_order_index=1,
            font_name="Inter-Regular",
            font_size=10.0,
        ),
        CanonicalToken(
            token_id="p105_t003",
            page_number=105,
            text="plant",
            bbox=BoundingBox(x0=112.0, y0=90.0, x1=138.0, y1=100.0),
            reading_order_index=2,
            font_name="Inter-Regular",
            font_size=10.0,
        ),
        CanonicalToken(
            token_id="p105_t004",
            page_number=105,
            text="and",
            bbox=BoundingBox(x0=142.0, y0=90.0, x1=160.0, y1=100.0),
            reading_order_index=3,
            font_name="Inter-Regular",
            font_size=10.0,
        ),
        CanonicalToken(
            token_id="p105_t005",
            page_number=105,
            text="equipment",
            bbox=BoundingBox(x0=164.0, y0=90.0, x1=220.0, y1=100.0),
            reading_order_index=4,
            font_name="Inter-Regular",
            font_size=10.0,
        ),
        CanonicalToken(
            token_id="p105_t006",
            page_number=105,
            text="7,32,150.00",
            bbox=BoundingBox(x0=380.0, y0=90.0, x1=450.0, y1=100.0),
            reading_order_index=5,
            font_name="Inter-Regular",
            font_size=10.0,
        ),
        CanonicalToken(
            token_id="p105_t007",
            page_number=105,
            text="6,89,420.00",
            bbox=BoundingBox(x0=470.0, y0=90.0, x1=540.0, y1=100.0),
            reading_order_index=6,
            font_name="Inter-Regular",
            font_size=10.0,
        ),
    ]

    # Map tokens into dictionary
    token_reg = {t.token_id: t for t in tokens}

    # Canonical cells
    c_label = CanonicalCell(
        cell_id="cell_p105_r1_c0",
        row_index=1,
        column_index=0,
        bbox=BoundingBox(x0=54.0, y0=90.0, x1=220.0, y1=100.0),
        token_ids=["p105_t002", "p105_t003", "p105_t004", "p105_t005"],
        raw_text="Property, plant and equipment",
        role="data",
    )
    c_cur = CanonicalCell(
        cell_id="cell_p105_r1_c1",
        row_index=1,
        column_index=1,
        bbox=BoundingBox(x0=380.0, y0=90.0, x1=450.0, y1=100.0),
        token_ids=["p105_t006"],
        raw_text="7,32,150.00",
        numeric_token_ids=["p105_t006"],
        parsed_numeric=Decimal("732150.00"),
        role="data",
    )
    c_prev = CanonicalCell(
        cell_id="cell_p105_r1_c2",
        row_index=1,
        column_index=2,
        bbox=BoundingBox(x0=470.0, y0=90.0, x1=540.0, y1=100.0),
        token_ids=["p105_t007"],
        raw_text="6,89,420.00",
        numeric_token_ids=["p105_t007"],
        parsed_numeric=Decimal("689420.00"),
        role="data",
    )

    # Table
    table = CanonicalTable(
        table_id="tbl_p105_01",
        page_numbers=[105],
        bbox=BoundingBox(x0=54.0, y0=70.0, x1=540.0, y1=600.0),
        detection_method="pdfplumber_grid_detector",
        structure_method="geometry_grid",
        token_ids=[t.token_id for t in tokens],
        rows=[
            CanonicalRow(row_index=0, row_id="r0", cell_ids=[], is_header=True, role="header"),
            CanonicalRow(row_index=1, row_id="r1", cell_ids=["cell_p105_r1_c0", "cell_p105_r1_c1", "cell_p105_r1_c2"], is_header=False, role="data"),
        ],
        columns=[
            CanonicalColumn(column_index=0, column_id="c0", header_text="Particulars", role="label"),
            CanonicalColumn(column_index=1, column_id="c1", header_text="As at 31 March 2025", role="numeric"),
            CanonicalColumn(column_index=2, column_id="c2", header_text="As at 31 March 2024", role="numeric"),
        ],
        cells=[c_label, c_cur, c_prev],
        validation_status=ValidationStatus.VALIDATED,
        confidence=0.99,
    )

    # Blocks
    block = CanonicalBlock(
        block_id="blk_p105_01",
        page_number=105,
        block_type="table",
        bbox=BoundingBox(x0=54.0, y0=70.0, x1=540.0, y1=600.0),
        token_ids=[t.token_id for t in tokens],
        table_id="tbl_p105_01",
        section_id="sec_bs_001",
        reading_order_index=0,
        confidence=0.98,
    )

    # Section
    section = CanonicalSection(
        section_id="sec_bs_001",
        title_raw="Consolidated Balance Sheet as at 31 March 2025",
        title_normalized="consolidated_balance_sheet",
        section_type="financial_statements",
        subcategory="balance_sheet",
        start_page=105,
        end_page=105,
        block_ids=["blk_p105_01"],
        table_ids=["tbl_p105_01"],
        confidence=0.99,
        taxonomy_path="Financial Statements > Consolidated > Balance Sheet",
    )

    # Page
    page = CanonicalPage(
        page_number=105,
        width=595.0,
        height=842.0,
        rotation=0,
        token_ids=[t.token_id for t in tokens],
        block_ids=["blk_p105_01"],
        section_ids=["sec_bs_001"],
        table_ids=["tbl_p105_01"],
    )

    # Indexes
    indexes = CanonicalIndexes(
        sections_by_type={"financial_statements": ["sec_bs_001"]},
        table_ids_by_section_id={"sec_bs_001": ["tbl_p105_01"]},
        blocks_by_page={105: ["blk_p105_01"]},
        token_ids_by_page={105: [t.token_id for t in tokens]},
        tables_by_page={105: ["tbl_p105_01"]},
        normalized_title_to_section_ids={"consolidated_balance_sheet": ["sec_bs_001"]},
    )

    return CanonicalDocument(
        document_id="doc_ril_fy25_001",
        source_metadata=src_meta,
        document_metadata=doc_meta,
        pages=[page],
        token_registry=token_reg,
        blocks=[block],
        tables=[table],
        sections=[section],
        indexes=indexes,
        processing_metadata={"canonicalizer_version": "v0.1.0", "engine": "pdfplumber+fitz"},
    )


if __name__ == "__main__":
    doc = build_sample_canonical_document()
    print(doc.model_dump_json(indent=2))
