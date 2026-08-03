# EWS Financial Data Extraction (VLM)

This project provides an automated, end-to-end pipeline for extracting complex financial tables (Balance Sheet, Profit & Loss, Cash Flow) from Indian Annual Report PDFs. It uses a **Vision Language Model (VLM)** powered by Deloitte's On-Premise Qwen3-VL to robustly process scanned, noisy, or natively digital PDFs.

## ?? Architecture & Workflow

The pipeline is designed to handle extremely long and noisy PDFs gracefully:

1. **Upload & Ingestion (FastAPI)**: 
   - Users upload an Annual Report PDF via a sleek, modern web UI.
   - The file is ingested and routed to the extraction pipeline.

2. **Heuristic Discovery & Parsing (PyMuPDF)**:
   - The document's text layer is parsed to find the Table of Contents (TOC).
   - Pages are scanned for keywords indicating financial statements.

3. **VLM Classification Fallback**:
   - For heavily scanned or "corrupted" PDFs where the text layer is missing or garbled, the pipeline routes the page images to a specialized VLM classifier.
   - The classifier identifies which pages contain the Standalone or Consolidated Balance Sheet, P&L, and Cash Flow.

4. **VLM Tabular Extraction (LangChain)**:
   - Identified pages are converted to base64 images and sent to the core Vision Language Model (Qwen3-VL).
   - The model follows strict prompt instructions to extract the tabular data into structured, hierarchical JSON (sections, line items, note numbers, current/previous periods).
   - **Resilience**: The extraction layer features a highly robust retry mechanism that validates the LLM's output. If the model hallucinates or outputs malformed JSON, the pipeline automatically catches the error and retries the prompt.

5. **Excel Reconstruction (OpenPyXL)**:
   - The structured JSON is passed to the Excel Builder, which dynamically reconstructs the financial tables into a professional, multi-sheet Excel workbook.
   - Both the JSON and the Excel workbook are dynamically bundled into a single ZIP file and streamed back to the user.

---

## 🚀 Recent Enhancements (Phases 2-4 & Sprint 3)

During our most recent pair-programming sessions, we fundamentally upgraded the extraction architecture to an enterprise-grade "Master Data" model, and hardened the extraction logic:

- **Section Registry (Phase 2)**: Replaced raw taxonomy mappings with a `Master Sections` layer that dynamically aggregates contiguous pages of the same category into structural blocks.
- **Table Inventory (Phase 3)**: Formalized table detection to log all potential tables (and whether they require VLM processing) into a centralized `table_inventory`.
- **Generic VLM Router (Phase 4)**: The extraction pipeline now seamlessly routes all complex non-financial tables (e.g., Shareholding Pattern, Segment Info, SOCE) to a dynamic, generic VLM extraction engine, while preserving the highly-optimized legacy VLM engine exclusively for the core 3 financial statements.
- **Universal Excel Generator**: Completely overhauled `excel_builder.py` to ensure the generated Excel workbook is an exact 1:1 reflection of the Master Data JSON. The exporter dynamically creates a dedicated Excel sheet for every Category, and prints out beautiful, cleanly wrapped text blocks and formatted table grids for every Subcategory.
- **Schema Bleeding & Flattening Fixes (Sprint 3)**: Hardened extraction routing (`content_extractor.py`) to use strict explicit target mapping, completely solving the "Schema Bleeding" issue where overlapping text heuristics caused data extraction to overwrite adjacent targets. Additionally, overhauled `workbook_population.py` to index the hierarchical JSON using exact lookups, fixing the "Flattening Collisions".
- **Pydantic Resilience (Sprint 3)**: Re-wrote canonical schemas to use `Optional` types, preventing catastrophic validation failures when the LLM returns `null` for missing parameters.
- **RAG & Semantic Chunking (Sprint 3)**: Eliminated naive token truncation (which caused massive data loss in the MD&A section). We introduced `rag_chunker.py`, utilizing `sentence-transformers` and `LangChain` to dynamically chunk and query long sections, keeping the most semantically relevant text within the model's context window.

---

## ??? Setup & Installation

1. **Create a virtual environment (Recommended)**:
   `ash
   python -m venv .venv
   .\.venv\Scripts\activate
   `

2. **Install core dependencies**:
   `ash
   pip install -r requirements.txt
   `

3. **Configuration**:
   The VLM configuration (API Keys, Base URLs, Model names) is managed in graph/sources/annual_report/llm_config.py. By default, it is configured for the Deloitte on-premise Qwen VLM. 

## ?? Usage

1. **Start the backend server**:
   Run the following command from the root of the project:
   `ash
   uvicorn app:app --port 8080 --reload
   `

2. **Access the application**:
   Open http://127.0.0.1:8080 in your browser. Upload an Annual Report PDF, wait for the extraction pipeline to complete, and download your ZIP bundle!
