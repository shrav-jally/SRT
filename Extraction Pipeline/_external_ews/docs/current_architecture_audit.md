# Current Architecture Audit — `ews` Repository

**Date**: July 2026  
**Branch**: `qwen-onprem`  
**Purpose**: Architectural assessment of the existing repository prior to implementing the Enterprise Two-Layer Document Understanding Architecture (Product 1: Canonicalizer, Product 2: Domain Extractors).

---

## 1. Current Request & Data Pipeline Flow

```
PDF File
  │
  ├─► Web UI (app.py / financial_tables_api.py) / CLI (graph/run_pipeline.py)
  │
  ├─► Layer 1: PDF Ingestion (pdf_ingestion.py)
  │     ├── pdfplumber: extract raw text & table presence per page
  │     └── fitz (PyMuPDF): extract document metadata & page count
  │
  ├─► Layer 2: Master Data Layer (master_data.py)
  │     └── SQLite in-memory store (:memory:) holding pages, headings, tables
  │
  ├─► Layer 3: Section Registry & TOC Parsing (toc_parser.py & section_consolidator.py)
  │     ├── TOC Parser: extracts page numbers and section titles
  │     └── Section Consolidator: creates MasterSection blocks (start_page..end_page)
  │
  ├─► Layer 3.5 & 3.6: Taxonomy Classification & Hierarchy (taxonomy.py)
  │     └── Classifies sections into 17 taxonomy categories (LLM or regex)
  │
  ├─► Layer 4 & 4.5: Table Inventory & VLM Targets (table_detector.py & vlm_targets.py)
  │     ├── Table Detector: detects grids, numeric density, column counts
  │     └── VLM Target Generator: computes high/medium/low priority VLM targets
  │
  ├─► Layer 5 & 6: Content & Subcategory Extraction (content_extractor.py)
  │     ├── Priority routing (source_routing.py)
  │     ├── Regex pre-extractors (Board, KMP, Committees, Subsidiaries, Dividend, Auditor)
  │     └── LLM text extraction for narrative subcategories
  │
  ├─► Layer 7: Financial Statement Engine & VLM Router (vlm_extractor.py)
  │     ├── Legacy VLM statement extraction (BS, P&L, Cash Flow via Qwen3-VL on-prem)
  │     └── Generic VLM router for non-financial tables (Shareholding, Segments, SOCE)
  │
  ├─► Layer 8, 9 & 9.5: Output Schema & Validation (schemas.py & validation_engine.py)
  │     ├── Completeness & coverage calculation
  │     └── Assembly into DocumentRegistry Pydantic model
  │
  └─► Export & Storage (excel_builder.py, workbook_population.py, db/store.py)
        ├── Dynamic multi-sheet Excel generation (.xlsx)
        └── Flat-file JSON + Excel database index persistence
```

---

## 2. Current PDF Discovery Flow

PDF statement discovery is located in `graph/sources/annual_report/discovery/`:
- **`parser.py`**: Reads PDF text layer using PyMuPDF (`fitz`) and `pdfplumber`.
- **`candidates.py`**: Scans page text for key phrase markers ("Balance Sheet", "Statement of Profit and Loss", "Cash Flow Statement", "Notes forming part of").
- **`scoring.py`**: Computes score confidence for each candidate page.
- **`classifier.py`**: Determines Standalone vs Consolidated classification.
- **`vlm_classifier.py`**: Fallback VLM page classifier for scanned or corrupted PDFs where text extraction yields empty/garbage strings.

---

## 3. Current VLM Call Sites

1. **`graph/sources/annual_report/vlm_extractor.py`**:
   - `_call_vlm_with_images()`: Sends base64-encoded PNG page images to the Qwen3-VL endpoint via `llm_config.py`.
   - `vlm_extract_statement()`: Renders PDF pages to images using PyMuPDF (`fitz`), calls Qwen3-VL, and parses structured JSON for Balance Sheet, P&L, and Cash Flow.
   - `extract_generic_table()`: Renders PDF table pages and calls Qwen3-VL for non-core financial tables.
2. **`graph/sources/annual_report/discovery/vlm_classifier.py`**:
   - `vlm_classify_page()`: Sends single page thumbnail image to Qwen3-VL to classify unreadable pages.

---

## 4. Current JSON Schemas

Defined in `graph/sources/annual_report/schemas.py` and `content_extractor.py`:

- **Primary Models**:
  - `DocumentRegistry`: Master output model containing metadata, section registry, table inventory, taxonomy summary, extractions, and quality report.
  - `MasterSection`: Consolidated section block (`section_id`, `start_page`, `end_page`, `category`, `subcategory`, `extraction_strategy`, `boundary_source`).
  - `TableInventoryItem`: Table metadata (`table_id`, `table_name`, `table_category`, `page_no`, `needs_vlm`, `complexity_score`).
  - `VLMTargetItem`: VLM task target (`priority`, `table_category`, `page_range`, `extraction_prompt`).
  - `BoardMember`, `KMPEntry`, `CommitteeEntry`, `SubsidiaryEntry`, `DividendEntry`, `AuditorEntry`: Domain entity models with evidence tracking.
  - `ExtractionEvidence` & `EvidenceBackedResult`: Provenance wrapper holding `extraction_method`, `source_text_snippet`, `source_page`, `confidence`, `source_section`.

---

## 5. Current Table Inventory Format

Maintained in `TableInventorySummary` containing `TableInventoryItem` objects:
```json
{
  "table_id": "tbl_p75_01",
  "table_name": "Consolidated Balance Sheet",
  "table_category": "financial_statement",
  "page_no": 75,
  "complexity_score": 0.85,
  "needs_vlm": true,
  "parent_section_id": "sec_012"
}
```

---

## 6. Current Section Registry Format

Maintained in `SectionRegistry` containing `MasterSection` objects:
```json
{
  "section_id": "sec_012",
  "section_name": "Consolidated Financial Statements",
  "section_type": "Financials",
  "category": "Financial Statements",
  "subcategory": "Consolidated Balance Sheet",
  "start_page": 75,
  "end_page": 77,
  "content_type": "table",
  "extraction_strategy": "vlm",
  "boundary_source": "toc",
  "source": "toc"
}
```

---

## 7. Current Excel Generation Flow

Handled by `excel_builder.py` and `workbook_population.py`:
- `build_excel(result)` creates an OpenPyXL workbook with:
  1. `Metadata`: File name, page count, timestamp, processing stats.
  2. `Priority 2` (Intelligence Report): 27 structured narrative rows with evidence columns (Method, Snippet, Page).
  3. `Valuation Counterpart` (Sheet2): 50 MSME / Valuation fields with current/previous values, status (`FOUND`, `NOT DISCLOSED`), trace source, trace method, intel links.
  4. `Master Sections`: Table listing all consolidated sections.
  5. Per-Category Worksheets: Dynamic sheets for each taxonomy category.
  6. `Uncategorized`: Residual data.

---

## 8. Direct PDF Dependencies to move to Product 1

To enforce the **STRICT RULE** (Product 2 extractors must never parse, open, crop, render, or access the original PDF), the following direct PDF dependencies must be confined strictly to Product 1 (`canonicalizer/`):

| Module | Direct PDF Operations | Target Location in New Architecture |
|---|---|---|
| `pdf_ingestion.py` | `pdfplumber.open()`, `page.extract_text()`, `page.extract_tables()`, `fitz.open()` | `canonicalizer/primitives.py` |
| `vlm_extractor.py` | `fitz.open()`, `doc[page].get_pixmap()` page rendering | `canonicalizer/primitives.py` / VLM structure helper in Product 1 |
| `toc_parser.py` | `pdfplumber.open()`, `page.extract_words()` | `canonicalizer/sections.py` |
| `table_detector.py` | `pdfplumber.open()`, grid line detection | `canonicalizer/table_inventory_adapter.py` |
| `discovery/parser.py` | `fitz.open()`, text extraction | Product 1 discovery step |

---

## 9. Reusable Modules

The following components are robust, well-tested, and should be preserved/reused:
- **`graph/sources/annual_report/schemas.py`**: Foundation for `contracts/`.
- **`graph/sources/annual_report/toc_parser.py`**: TOC anchor extraction logic.
- **`graph/sources/annual_report/section_consolidator.py`**: Section boundary building algorithm.
- **`graph/sources/annual_report/source_routing.py`**: Domain source priority mapping rules.
- **`graph/sources/annual_report/llm_config.py` & `llm_utils.py`**: VLM / LLM API client abstraction.
- **`excel_builder.py` & `workbook_population.py`**: Excel reporting formatting.
- **`db/store.py`**: Document indexing and local disk persistence.

---

## 10. Risky, Duplicated, or Obsolete Code

1. **Direct PDF Leaks in Extraction**: `vlm_extractor.py` and `content_extractor.py` currently open the PDF directly or expect page images rendered directly from PDF paths.
2. **Text Truncation**: Hardcoded string truncations (`text[:20000]`, `text[:50000]`) in `extraction_pipeline.py` and `content_extractor.py` risk silent data loss for long narrative notes.
3. **Table Detection False Positives**: `table_detector.py` relies on keyword matching per page without full grid bounding box checks, causing false positive table classifications.
4. **Duplicate Discovery Logic**: `graph/sources/annual_report/discovery/` duplicates some of the keyword and page scanning done in `pdf_ingestion.py` and `table_detector.py`.
