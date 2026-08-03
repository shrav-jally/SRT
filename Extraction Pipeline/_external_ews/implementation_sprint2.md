# Sprint 2 Implementation Plan: 47-Parameter Extraction

## Objective
Extend the successfully deployed 16-parameter Workbook Population layer into the comprehensive 47-parameter extraction framework as requested for the final demo.

## Current State
- **Sprint 1 Complete:** We successfully extract and map 15/16 high-level narrative categories (Company Profile, MD&A, Shareholding, etc.) into the Excel workbook with Confidence and Page Reference columns.
- **Robust Routing:** The NLP pipeline handles poorly parsed headings, taxonomy classification errors, and alias mismatches flawlessly.

## Scope of Sprint 2
The goal of Sprint 2 is to inject the deep financial parsing layer alongside the narrative parsing. 
We will expand the extraction targets to 47 specific parameters, heavily leveraging the VLM table-extraction pipeline for the Financial Statements (Balance Sheet, P&L, Cash Flow).

### 1. Taxonomy Expansion
- Define the remaining 31 target fields in the `MAPPING_RULES` engine.
- Categorize targets into:
  - **Narrative Fields:** CSR Spend, ESG Ratings, Auditor Names, Key Risks.
  - **Financial Fields:** Revenue, EBITDA, PAT, EPS, Total Debt, Cash Reserves, Net Worth.

### 2. Specialized Financial Extractors
- Expand `content_extractor.py` to route financial requests through a new `_extract_financials` function.
- Process the output of the existing `vlm_extractor` which captures the tabular financial statements.
- Extract YoY (Year-over-Year) metrics to populate historical trend columns.

### 3. Excel Matrix Scaling
- Scale `excel_builder.py` to accommodate the 47-row matrix.
- Introduce conditional formatting (e.g., Red/Green highlighting for YoY Revenue decline/growth).
- Ensure the `Status` column properly flags `FOUND`, `NOT APPLICABLE`, or `NOT DISCLOSED` across all 47 rows.

## Next Steps
Upon review, we will begin expanding `workbook_population.py` mapping rules and wire up the VLM table-extraction results.
