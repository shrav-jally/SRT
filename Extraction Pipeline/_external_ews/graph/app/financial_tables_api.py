"""FastAPI application for the Enterprise Annual Report Extraction Framework.

Endpoints
---------
- ``POST /api/v1/custom-extract``      — Product 1 (Canonicalizer) + Product 2 (Custom Spec Engine)
- ``GET  /api/v1/download/excel/{id}`` — Download custom spec extraction Excel workbook
- ``GET  /api/v1/download/json/{id}``  — Download custom spec extraction JSON result
- ``POST /extract/full``               — full 9-layer extraction pipeline (taxonomy, tables, validation)
- ``POST /extract``                    — legacy VLM-only financial statement extraction as JSON
- ``POST /extract/excel``              — legacy VLM-only extraction as Excel download
- ``POST /extract/zip``                — legacy VLM-only extraction as ZIP (JSON + Excel)
- ``GET  /``                           — web UI for upload + custom spec extraction + download
- ``GET  /health``                     — health check

Run::

    uvicorn app:app --reload --port 8080
"""

import asyncio
import io
import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Query, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

import sys as _sys
_graph_root = str(Path(__file__).resolve().parent.parent)
_project_root = str(Path(__file__).resolve().parent.parent.parent)
for _p in (_project_root, _graph_root):
    if _p not in _sys.path:
        _sys.path.insert(0, _p)

from sources.annual_report.vlm_extractor import vlm_extract_all
from sources.annual_report.excel_builder import build_excel
from sources.annual_report.extraction_pipeline import run_full_extraction

from canonicalizer import canonicalize_pdf
from extractors.custom_spec import (
    extract_from_custom_spec,
    load_custom_spec,
    export_custom_extraction_to_excel,
)

# Database auto-save
try:
    from db import get_db
except ImportError:
    get_db = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

# ===================================================================
# App setup
# ===================================================================

app = FastAPI(
    title="Enterprise Document Understanding Framework",
    description=(
        "Two-layer enterprise document understanding architecture for Indian annual reports (IFRS/Ind AS). "
        "Product 1 (Canonicalizer) parses raw PDF into CanonicalDocument v0 JSON. "
        "Product 2 (Custom Spec Engine) resolves user-defined schema specifications with provenance and status flags."
    ),
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===================================================================
# Helpers
# ===================================================================

async def _save_upload(tmp_dir: Path, upload: UploadFile) -> Path:
    """Persist an uploaded file to tmp_dir and return the path."""
    dest = tmp_dir / (upload.filename or "report.pdf")
    with open(dest, "wb") as f:
        content = await upload.read()
        f.write(content)
    return dest


def _auto_save_to_db(result: dict[str, Any]) -> None:
    """Persist extraction result to the local database if available."""
    if not get_db:
        return
    try:
        db = get_db()
        entry = db.save(result)
        logger.info(
            "Auto-saved to db: company=%s fy=%s id=%s",
            entry.get("company"), entry.get("financial_year"), entry.get("id"),
        )
    except Exception:
        logger.warning("Auto-save to db failed", exc_info=True)


# ===================================================================
# Product 1 + Product 2 Custom Extraction Spec Endpoints
# ===================================================================

@app.get("/api/v1/spec/{spec_id}", summary="Get Custom Extraction Spec JSON")
async def get_custom_spec(spec_id: str) -> JSONResponse:
    """Return the JSON content of the requested extraction spec."""
    # Only allow fetching json files from current directory
    if not spec_id.endswith(".json") or "/" in spec_id or "\\" in spec_id:
        return JSONResponse(content={"error": "Invalid spec ID"}, status_code=400)
        
    spec_path = Path(spec_id)
    if not spec_path.exists():
        return JSONResponse(content={"error": "Spec not found"}, status_code=404)
        
    with open(spec_path, "r", encoding="utf-8") as f:
        spec_data = json.load(f)
        
    return JSONResponse(content=spec_data)

@app.post("/api/v1/custom-extract", summary="Run Product 1 Canonicalizer + Product 2 Custom Spec Engine")
async def custom_extract(
    file: UploadFile = File(...),
    spec_id: str = Form("sample_custom_spec.json", description="Spec filename"),
    spec_json: str = Form(None, description="Custom Spec JSON String"),
) -> JSONResponse:
    """Ingest PDF -> Product 1 Canonicalizer -> Product 2 Custom Extraction Engine -> JSON + Excel."""
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        pdf_path = await _save_upload(tmp_dir, file)

        # Product 1: Canonicalize PDF (or load from cache)
        doc_id = pdf_path.stem
        cached_canonical_path = Path("output") / doc_id / "canonical_document.v0.json"
        
        if cached_canonical_path.exists():
            logger.info(f"Loading cached CanonicalDocument v0 for {doc_id}")
            from canonicalizer import load_canonical_document
            canonical_doc = load_canonical_document(cached_canonical_path)
        else:
            canonical_doc = await asyncio.to_thread(
                canonicalize_pdf,
                pdf_path=pdf_path,
                use_llm_taxonomy=False
            )

        # Product 2: Load spec & extract
        if spec_json:
            from contracts import CustomExtractionSpecDocument
            spec_doc = CustomExtractionSpecDocument.model_validate_json(spec_json)
        else:
            spec_file = Path(spec_id) if Path(spec_id).exists() else Path("sample_custom_spec.json")
            spec_doc = load_custom_spec(spec_file)

        result_doc = await asyncio.to_thread(
            extract_from_custom_spec,
            canonical_doc=canonical_doc,
            spec=spec_doc
        )

        # Save output artifacts to disk
        doc_dir = Path("output") / canonical_doc.document_id
        doc_dir.mkdir(parents=True, exist_ok=True)

        excel_path = doc_dir / "custom_extraction_result.xlsx"
        export_custom_extraction_to_excel(result_doc, output_path=excel_path)

        json_path = doc_dir / "custom_extraction_result.json"
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(result_doc.model_dump_json(indent=2))

        return JSONResponse(content={
            "document_id": canonical_doc.document_id,
            "canonical_summary": {
                "pages": len(canonical_doc.pages),
                "sections": len(canonical_doc.sections),
                "tables": len(canonical_doc.tables),
            },
            "summary": result_doc.summary,
            "results": [r.model_dump() for r in result_doc.results],
            "excel_download_url": f"/api/v1/download/excel/{canonical_doc.document_id}",
            "json_download_url": f"/api/v1/download/json/{canonical_doc.document_id}",
        })


@app.get("/api/v1/download/excel/{document_id}", summary="Download Custom Spec Excel Result")
async def download_custom_excel(document_id: str):
    file_path = Path("output") / document_id / "custom_extraction_result.xlsx"
    if not file_path.exists():
        return JSONResponse(status_code=404, content={"error": "Excel output file not found"})
    return FileResponse(
        path=file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{document_id}_custom_extraction.xlsx",
    )



@app.get("/api/v1/canonical-document/{document_id}", summary="Get Full Canonical Document JSON")
@app.get("/output/{document_id}/canonical_document.v0.json", summary="Get Full Canonical Document JSON Static Endpoint")
async def get_canonical_document(document_id: str):
    import json
    from pathlib import Path
    
    # URL decode document_id if needed
    import urllib.parse
    doc_id_decoded = urllib.parse.unquote(document_id)
    
    file_path = Path("output") / doc_id_decoded / "canonical_document.v0.json"
    if not file_path.exists():
        file_path = Path("output") / document_id / "canonical_document.v0.json"
        if not file_path.exists():
            file_path = Path("canonical_document.v0.json")
            if not file_path.exists():
                return JSONResponse(status_code=404, content={"error": f"Canonical Document for {document_id} not found"})
    
    try:
        return FileResponse(path=file_path, media_type="application/json", filename=f"{doc_id_decoded}_canonical.json")
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/v1/canonical-summary/{document_id}", summary="Get Lightweight Business-Friendly Canonical Summary")
async def get_canonical_summary(document_id: str):
    import json
    from pathlib import Path
    import urllib.parse
    
    doc_id_decoded = urllib.parse.unquote(document_id)
    
    file_path = Path("output") / doc_id_decoded / "canonical_document.v0.json"
    if not file_path.exists():
        file_path = Path("output") / document_id / "canonical_document.v0.json"
        if not file_path.exists():
            file_path = Path("canonical_document.v0.json")
            if not file_path.exists():
                return JSONResponse(status_code=404, content={"error": f"Canonical Document for '{document_id}' not found"})
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            d = json.load(f)
        
        # Build clean 2D grids for tables without coordinates
        clean_tables = []
        for tbl in d.get("tables", []):
            cells = tbl.get("cells", [])
            if not cells:
                continue
            max_row = max(c.get("row_index", 0) for c in cells)
            max_col = max(c.get("column_index", 0) for c in cells)
            grid = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]
            for cell in cells:
                grid[cell.get("row_index", 0)][cell.get("column_index", 0)] = (cell.get("raw_text") or "").replace("\n", " ").strip()
                
            clean_tables.append({
                "table_id": tbl.get("table_id"),
                "pages": tbl.get("page_numbers", []),
                "dimensions": f"{max_row + 1} x {max_col + 1}",
                "grid_sample": grid[:10]  # First 10 rows for clean display
            })

        summary = {
            "document_id": d.get("document_id"),
            "metadata": d.get("document_metadata", {}),
            "summary_stats": {
                "total_pages": len(d.get("pages", [])),
                "total_sections": len(d.get("sections", [])),
                "total_tables": len(d.get("tables", []))
            },
            "sections": [
                {
                    "section_id": sec.get("section_id"),
                    "title": sec.get("title_raw") or sec.get("title_normalized"),
                    "category": sec.get("section_type"),
                    "pages": f"Page {sec.get('start_page', 1)} - {sec.get('end_page', 1)}"
                }
                for sec in d.get("sections", [])
            ],
            "tables": clean_tables
        }
        return JSONResponse(content=summary)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/v1/download/json/{document_id}", summary="Download Custom Spec JSON Result")
async def download_custom_json(document_id: str):
    file_path = Path("output") / document_id / "custom_extraction_result.json"
    if not file_path.exists():
        return JSONResponse(status_code=404, content={"error": "JSON output file not found"})
    return FileResponse(
        path=file_path,
        media_type="application/json",
        filename=f"{document_id}_custom_extraction.json",
    )


# ===================================================================
# Legacy & Full Pipeline Endpoints
# ===================================================================

@app.post("/extract", summary="Extract all financial statements as JSON")
async def extract_all(
    file: UploadFile = File(...),
    dpi: int = Query(150, description="Image resolution in DPI for VLM"),
) -> JSONResponse:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        pdf_path = await _save_upload(tmp_dir, file)
        result = await asyncio.to_thread(vlm_extract_all, pdf_path=pdf_path, dpi=dpi)
        asyncio.create_task(asyncio.to_thread(_auto_save_to_db, result))
        return JSONResponse(content=result)


@app.post("/extract/excel", summary="Extract all financial statements as Excel")
async def extract_excel(
    file: UploadFile = File(...),
    dpi: int = Query(150, description="Image resolution in DPI for VLM"),
) -> StreamingResponse:
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        pdf_path = await _save_upload(tmp_dir, file)
        result = await asyncio.to_thread(vlm_extract_all, pdf_path=pdf_path, dpi=dpi)
        asyncio.create_task(asyncio.to_thread(_auto_save_to_db, result))
        excel_bytes = build_excel(result)
        out_name = f"{pdf_path.stem}_vlm_output.xlsx"
        return StreamingResponse(
            io.BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{out_name}"'}
        )


@app.get("/health", summary="Health Check")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "engine": "two_layer_custom_extraction_architecture",
        "version": "3.0.0",
        "layers": "Product 1 (Canonicalizer) → Product 2 (Custom Spec Engine) → Provenance & Excel",
    }


# ===================================================================
# Modern Interactive Web UI
# ===================================================================

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def web_ui():
    """Modern Interactive UI for Enterprise Document Understanding & Custom Spec Extraction."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>EWS | Enterprise Custom Extraction Engine</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            :root {
                --primary: #6366F1;
                --primary-hover: #4F46E5;
                --accent: #10B981;
                --bg-dark: #0F172A;
                --card-bg: rgba(30, 41, 59, 0.85);
                --border-color: rgba(255, 255, 255, 0.1);
                --text-main: #F8FAFC;
                --text-muted: #94A3B8;
            }
            body {
                margin: 0; padding: 24px;
                font-family: 'Inter', sans-serif;
                background: linear-gradient(135deg, #0F172A 0%, #1E1B4B 100%);
                color: var(--text-main);
                min-height: 100vh;
            }
            .header {
                text-align: center;
                margin-bottom: 32px;
            }
            .badge {
                display: inline-block;
                padding: 4px 12px;
                border-radius: 9999px;
                font-size: 12px;
                font-weight: 600;
                background: rgba(99, 102, 241, 0.15);
                color: #818CF8;
                border: 1px solid rgba(99, 102, 241, 0.3);
                margin-bottom: 8px;
            }
            h1 {
                margin: 0 0 8px 0;
                font-size: 32px;
                font-weight: 700;
                background: linear-gradient(to right, #818CF8, #C084FC);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            .sub-header { color: var(--text-muted); font-size: 15px; margin: 0; }
            
            .main-grid {
                display: grid;
                grid-template-columns: 360px 1fr;
                gap: 24px;
                max-width: 1400px;
                margin: 0 auto;
            }
            
            .card {
                background: var(--card-bg);
                backdrop-filter: blur(12px);
                border: 1px solid var(--border-color);
                border-radius: 20px;
                padding: 24px;
                box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.4);
            }
            
            .file-upload {
                border: 2px dashed var(--border-color);
                border-radius: 16px;
                padding: 32px 16px;
                text-align: center;
                cursor: pointer;
                transition: all 0.3s ease;
                margin-bottom: 16px;
            }
            .file-upload:hover {
                border-color: var(--primary);
                background: rgba(99, 102, 241, 0.05);
            }
            .file-upload input { display: none; }
            .btn {
                background: var(--primary);
                color: white;
                border: none;
                padding: 14px 20px;
                border-radius: 12px;
                font-size: 15px;
                font-weight: 600;
                width: 100%;
                cursor: pointer;
                transition: all 0.2s ease;
            }
            .btn:hover { background: var(--primary-hover); transform: translateY(-1px); }
            
            /* Results Panel */
            .stats-bar {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 12px;
                margin-bottom: 20px;
            }
            .stat-card {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid var(--border-color);
                border-radius: 12px;
                padding: 16px;
                text-align: center;
            }
            .stat-val { font-size: 22px; font-weight: 700; color: #818CF8; }
            .stat-lbl { font-size: 11px; color: var(--text-muted); text-transform: uppercase; margin-top: 4px; }

            .results-table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 12px;
                font-size: 13px;
            }
            .results-table th {
                background: rgba(255, 255, 255, 0.05);
                color: var(--text-muted);
                text-align: left;
                padding: 10px 12px;
                border-bottom: 1px solid var(--border-color);
            }
            .results-table td {
                padding: 12px;
                border-bottom: 1px solid rgba(255,255,255,0.05);
                vertical-align: top;
            }
            .status-tag {
                padding: 3px 8px;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 700;
                display: inline-block;
            }
            .status-FOUND { background: rgba(16, 185, 129, 0.2); color: #34D399; }
            .status-NOT_FOUND { background: rgba(239, 68, 68, 0.2); color: #F87171; }
            .status-AMBIGUOUS { background: rgba(245, 158, 11, 0.2); color: #FBBF24; }

            .action-bar {
                display: flex;
                gap: 12px;
                margin-top: 20px;
            }
            .btn-secondary {
                background: rgba(255,255,255,0.1);
                color: white;
                border: 1px solid var(--border-color);
                padding: 10px 16px;
                border-radius: 10px;
                cursor: pointer;
                font-weight: 600;
                text-decoration: none;
                font-size: 13px;
            }
            .btn-secondary:hover { background: rgba(255,255,255,0.2); }
            
            /* Modal Styles */
            .modal-overlay {
                display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                background: rgba(15, 23, 42, 0.7); backdrop-filter: blur(8px);
                z-index: 1000; align-items: center; justify-content: center;
            }
            .modal-content {
                background: rgba(30, 41, 59, 0.95);
                border: 1px solid var(--border-color);
                border-radius: 20px;
                width: 90%; max-width: 800px; max-height: 85vh;
                overflow-y: auto; padding: 32px;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
                transform: translateY(20px); opacity: 0;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }
            .modal-overlay.show { display: flex; }
            .modal-overlay.show .modal-content { transform: translateY(0); opacity: 1; }
            .modal-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
            .modal-close { background: transparent; border: none; color: var(--text-muted); font-size: 24px; cursor: pointer; }
            .modal-close:hover { color: white; }
            .spec-field-card {
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.05);
                border-radius: 12px; padding: 16px; margin-bottom: 12px;
            }
            .spec-field-card h4 { margin: 0 0 8px 0; color: #818CF8; }
            .synonym-tag {
                display: inline-block; padding: 2px 8px; border-radius: 4px;
                background: rgba(16, 185, 129, 0.1); color: #34D399; font-size: 11px; margin: 2px 4px 2px 0;
            }
            pre.formatted-json {
                background: rgba(0,0,0,0.2); padding: 12px; border-radius: 8px;
                font-family: monospace; font-size: 12px; overflow-x: auto;
                border: 1px solid rgba(255,255,255,0.05); white-space: pre-wrap; margin: 0;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <span class="badge">PRODUCT 1 (CANONICALIZER) + PRODUCT 2 (SPEC ENGINE)</span>
            <h1>Enterprise Document Understanding Architecture</h1>
            <p class="sub-header">Schema-Driven Extraction over Canonical Document Representation v0</p>
        </div>

        <div class="main-grid">
            <!-- Sidebar / Upload -->
            <div class="card">
                <h3 style="margin-top:0;">Upload & Extract</h3>
                <div class="file-upload" onclick="document.getElementById('pdfInput').click()">
                    <div style="font-size:32px; margin-bottom:8px;">📄</div>
                    <div id="fileName" style="font-weight:500;">Click or Drop PDF Annual Report</div>
                    <div style="font-size:12px; color:var(--text-muted); margin-top:4px;">100–400 Page IFRS/Ind AS Annual Reports</div>
                    <input type="file" id="pdfInput" accept=".pdf" onchange="document.getElementById('fileName').innerText = this.files[0].name">
                </div>

                <div style="margin-bottom:16px;">
                    <label style="font-size:12px; color:var(--text-muted);">Extraction Specification Spec</label>
                    <select id="specSelect" style="width:100%; padding:10px; border-radius:8px; background:rgba(255,255,255,0.05); color:white; border:1px solid var(--border-color); margin-top:4px;">
                        <option value="sample_custom_spec.json">Enterprise Demo Spec (10 Core Fields)</option>
                        <option value="financial_statements_spec.json">Financial Statements Only (BS, P&L, CF)</option>
                        <option value="msme_financial_metrics_spec.json">Detailed Financial Metrics (27 Items)</option>
                        <option value="comprehensive_sections_spec.json">Comprehensive Narrative Sections (13 Items)</option>
                    </select>
                </div>
                <div style="margin-bottom:24px; text-align: right;">
                    <button type="button" class="btn-secondary" style="padding: 6px 12px; font-size: 12px; border-radius: 6px;" onclick="viewSpecDetails()">👁️ View Spec Details</button>
                </div>

                <button class="btn" id="runBtn" onclick="runExtraction()">Execute Custom Spec Extraction</button>
                <button type="button" class="btn-secondary" style="width:100%; margin-top:12px;" onclick="inspectCanonical()" id="inspectBtn" disabled>👁️ Inspect Canonical Document</button>

                <div id="statusBox" style="margin-top:16px; font-size:13px; color:var(--text-muted); display:none;">
                    Processing PDF through Product 1 & Product 2...
                </div>
            </div>

            <!-- Main Results Display -->
            <div class="card" id="resultsPanel" style="display:none;">
                <div class="stats-bar">
                    <div class="stat-card">
                        <div class="stat-val" id="statFound">-</div>
                        <div class="stat-lbl">Fields Found</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-val" id="statRate">-</div>
                        <div class="stat-lbl">Completion Rate</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-val" id="statPages">-</div>
                        <div class="stat-lbl">Canonical Pages</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-val" id="statTables">-</div>
                        <div class="stat-lbl">Canonical Tables</div>
                    </div>
                </div>

                <h3 style="margin: 0 0 12px 0;">Custom Extraction Results</h3>
                <table class="results-table">
                    <thead>
                        <tr>
                            <th>Category</th>
                            <th>Entity Name</th>
                            <th>Mode</th>
                            <th>Status</th>
                            <th>Confidence</th>
                            <th>Extracted Value / Provenance</th>
                        </tr>
                    </thead>
                    <tbody id="resultsBody"></tbody>
                </table>

                <div class="action-bar">
                    <a id="excelBtn" class="btn-secondary" href="#" target="_blank">📥 Download Excel (.xlsx)</a>
                    <a id="jsonBtn" class="btn-secondary" href="#" target="_blank">📄 Download JSON (.json)</a>
                </div>
            </div>
        </div>

        <!-- Spec Viewer Modal -->
        <div id="specModal" class="modal-overlay">
            <div class="modal-content">
                <div class="modal-header">
                    <div>
                        <span class="badge" id="modalSpecId">spec_id</span>
                        <h2 style="margin: 8px 0 4px 0;" id="modalSpecName">Spec Name</h2>
                        <div style="color:var(--text-muted); font-size: 14px;" id="modalSpecDesc">Description</div>
                    </div>
                    <button class="modal-close" onclick="closeSpecModal()">&times;</button>
                </div>
                <div id="modalFieldsList"></div>
            </div>
        </div>

        <script>
            function formatValueRaw(val) {
                if (!val || val === '-') return '<b>-</b>';
                try {
                    let parsed = val;
                    if (typeof val === 'string') {
                        let fixedStr = val.replace(/'/g, '"').replace(/None/g, 'null');
                        try { parsed = JSON.parse(fixedStr); } catch(e) { parsed = val; }
                    }
                    if (typeof parsed === 'object' && parsed !== null) {
                        return `<pre class="formatted-json">${JSON.stringify(parsed, null, 2)}</pre>`;
                    }
                } catch(e) {}
                return `<b>${val}</b>`;
            }

            async function viewSpecDetails() {
                const specVal = document.getElementById('specSelect').value;
                try {
                    const resp = await fetch('/api/v1/spec/' + encodeURIComponent(specVal));
                    if (!resp.ok) throw new Error("Spec not found");
                    const data = await resp.json();
                    
                    document.getElementById('modalSpecId').innerText = data.version ? `Version ${data.version}` : data.spec_id;
                    document.getElementById('modalSpecName').innerText = data.spec_name || specVal;
                    document.getElementById('modalSpecDesc').innerText = data.description || "Extraction Spec Configuration";
                    
                    const fieldsHtml = data.fields.map(f => `
                        <div class="spec-field-card">
                            <div style="display:flex; justify-content:space-between;">
                                <h4>${f.entity_name}</h4>
                                <span style="font-size:11px; color:var(--text-muted);">${f.extraction_mode}</span>
                            </div>
                            <div style="font-size:12px; margin-bottom:8px; color:var(--text-muted);">${f.description || ''}</div>
                            <div>
                                <span style="font-size:11px; color:#94A3B8; margin-right:4px;">Synonyms:</span>
                                ${(f.synonyms || []).map(s => `<span class="synonym-tag">${s}</span>`).join('')}
                            </div>
                        </div>
                    `).join('');
                    document.getElementById('modalFieldsList').innerHTML = fieldsHtml;
                    
                    const modal = document.getElementById('specModal');
                    modal.style.display = 'flex';
                    setTimeout(() => modal.classList.add('show'), 10);
                } catch (err) {
                    alert("Could not load spec details: " + err.message);
                }
            }

            function closeSpecModal() {
                const modal = document.getElementById('specModal');
                modal.classList.remove('show');
                setTimeout(() => modal.style.display = 'none', 300);
            }

            
        let currentDocumentId = null;
        
        async function inspectCanonical() {
            if (!currentDocumentId) return;
            const modal = document.getElementById('canonicalModal');
            modal.classList.add('show');
            const content = document.getElementById('canonicalContent');
            content.innerHTML = "<p>Fetching canonical structure (ignoring 30MB token registry)...</p>";
            
            try {
                const response = await fetch(`/api/v1/canonical-summary/${currentDocumentId}`);
                if (!response.ok) throw new Error("Canonical document not found on server");
                const data = await response.json();
                
                let html = "<div style='display:flex; gap:20px;'>";
                
                // Sections Column
                html += "<div style='flex:1; max-height:60vh; overflow-y:auto; border:1px solid #334155; padding:16px; border-radius:12px;'>";
                html += "<h3 style='margin-top:0; color:#38bdf8;'>Canonical Sections</h3>";
                data.sections.forEach(sec => {
                    html += `<div style='margin-bottom:8px; padding-bottom:8px; border-bottom:1px solid #1e293b;'>
                        <div style='font-weight:bold; font-size:13px;'>${sec.title_raw || 'Untitled'}</div>
                        <div style='font-size:11px; color:#94a3b8;'>Type: ${sec.section_type || 'Unknown'} | Page: ${sec.start_page}</div>
                    </div>`;
                });
                html += "</div>";
                
                // Tables Column
                html += "<div style='flex:1; max-height:60vh; overflow-y:auto; border:1px solid #334155; padding:16px; border-radius:12px;'>";
                html += "<h3 style='margin-top:0; color:#a78bfa;'>Structured Tables</h3>";
                data.tables.forEach(tbl => {
                    html += `<div style='margin-bottom:16px; padding:12px; background:rgba(255,255,255,0.02); border:1px solid #1e293b; border-radius:8px;'>
                        <div style='font-weight:bold; font-size:12px; margin-bottom:8px; color:#e2e8f0;'>Table ID: ${tbl.table_id} (Page: ${tbl.page_numbers.join(', ')})</div>`;
                    
                    const rows = {};
                    tbl.rows.forEach(cell => {
                        if (!rows[cell.row_index]) rows[cell.row_index] = [];
                        rows[cell.row_index].push(cell);
                    });
                    
                    Object.keys(rows).sort((a,b) => parseInt(a) - parseInt(b)).forEach(rIdx => {
                        const rowCells = rows[rIdx].sort((a,b) => a.column_index - b.column_index);
                        html += `<div style='display:flex; border-bottom:1px solid #1e293b; font-size:11px;'>`;
                        rowCells.forEach(c => {
                            html += `<div style='flex:1; padding:4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;' title='${c.raw_text}'>${c.raw_text || ''}</div>`;
                        });
                        html += `</div>`;
                    });
                    html += "</div>";
                });
                html += "</div>";
                
                html += "</div>";
                content.innerHTML = html;
            } catch (err) {
                content.innerHTML = `<p style="color:#ef4444;">Error: ${err.message}</p>`;
            }
        }
    

        async function runExtraction() {
                const fileInput = document.getElementById('pdfInput');
                if (!fileInput.files.length) {
                    alert("Please select a PDF file first.");
                    return;
                }

                const runBtn = document.getElementById('runBtn');
                const statusBox = document.getElementById('statusBox');
                const resultsPanel = document.getElementById('resultsPanel');

                runBtn.disabled = true;
                runBtn.innerText = "Extracting...";
                statusBox.style.display = "block";

                const specVal = document.getElementById('specSelect').value;
                const formData = new FormData();
                formData.append('file', fileInput.files[0]);

                try {
                    const resp = await fetch('/api/v1/custom-extract?spec_id=' + encodeURIComponent(specVal), {
                        method: 'POST',
                        body: formData
                    });
                    const text = await resp.text();
                    let data;
                    try {
                        data = JSON.parse(text);
                    } catch(e) {
                        throw new Error(text || "Extraction failed");
                    }

                    if (!resp.ok) throw new Error(data.error || "Extraction failed");

                    currentDocumentId = data.document_id;
                    const btn = document.getElementById("inspectBtn");
                    if (btn) btn.disabled = false;

                    // Update Stats
                    document.getElementById('statFound').innerText = data.summary.fields_found + " / " + data.summary.total_fields_requested;
                    document.getElementById('statRate').innerText = data.summary.completion_rate_pct + "%";
                    document.getElementById('statPages').innerText = data.canonical_summary.pages;
                    document.getElementById('statTables').innerText = data.canonical_summary.tables;

                    // Update Table Rows
                    const tbody = document.getElementById('resultsBody');
                    tbody.innerHTML = '';

                    data.results.forEach(res => {
                        const tr = document.createElement('tr');
                        const confPct = Math.round(res.confidence * 100);
                        const prov = res.provenance && res.provenance.length ? res.provenance[0] : {};
                        const provText = prov.page_number ? ` (Page ${prov.page_number}${prov.section_id ? ', Section: ' + prov.section_id : ''})` : '';

                        tr.innerHTML = `
                            <td><b>${res.category}</b><br><span style="color:var(--text-muted); font-size:11px;">${res.subcategory}</span></td>
                            <td>${res.entity_name}</td>
                            <td><span style="font-size:11px; color:var(--text-muted);">${res.extraction_mode}</span></td>
                            <td><span class="status-tag status-${res.status}">${res.status}</span></td>
                            <td>${confPct}%</td>
                            <td>
                                <div>${formatValueRaw(res.value_raw)}</div>
                                <div style="font-size:11px; color:var(--text-muted); margin-top:6px; border-top: 1px solid rgba(255,255,255,0.05); padding-top:6px;">
                                    ${res.explanation || ''}${provText}
                                </div>
                            </td>
                        `;
                        tbody.appendChild(tr);
                    });

                    // Update Download Links
                    document.getElementById('excelBtn').href = data.excel_download_url;
                    document.getElementById('jsonBtn').href = data.json_download_url;

                    resultsPanel.style.display = "block";
                    statusBox.innerText = "Extraction complete!";
                } catch (err) {
                    alert("Error: " + err.message);
                    statusBox.innerText = "Extraction failed.";
                } finally {
                    runBtn.disabled = false;
                    runBtn.innerText = "Execute Custom Spec Extraction";
                }
            }
        </script>
    
    <div id="canonicalModal" class="modal-overlay">
        <div class="modal-content" style="max-width:900px;">
            <div class="modal-header">
                <h2 style="margin:0;">Canonical Document Inspector</h2>
                <button class="modal-close" onclick="document.getElementById('canonicalModal').classList.remove('show')">&times;</button>
            </div>
            <div id="canonicalContent">Loading canonical document structure...</div>
        </div>
    </div>
    
    </body>
    </html>
    """
