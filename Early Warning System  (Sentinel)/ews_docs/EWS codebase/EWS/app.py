#!/usr/bin/env python3
"""
EWS Annual Report Extraction - FastAPI Application

A REST API that accepts multiple PDF annual reports, extracts financial data
using the ews_agent pipeline, and returns populated Excel templates.

Endpoints:
    POST /extract          - Upload one or more PDFs with years, start extraction
    GET  /status/{job_id}  - Check processing status
    GET  /download/{job_id} - Download result Excel files (ZIP if multiple)
    GET  /download/{job_id}/{filename} - Download a single result file
    GET  /health           - Health check
    GET  /jobs             - List all jobs
    DELETE /jobs/{job_id}  - Delete a job and its output files

Usage:
    uvicorn app:app --host 0.0.0.0 --port 8000 --reload

Example (curl):
    # Single PDF
    curl -X POST http://localhost:8000/extract \
      -F "files=@Annual-Report-2022-2023.pdf" \
      -F "years=2023"

    # Multiple PDFs with different years
    curl -X POST http://localhost:8000/extract \
      -F "files=@report1.pdf" \
      -F "files=@report2.pdf" \
      -F "years=2023" \
      -F "years=2024"

    # Check status
    curl http://localhost:8000/status/abc123

    # Download results
    curl -O http://localhost:8000/download/abc123
"""

import io
import logging
import os
import shutil
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ============================================================================
# CONFIGURATION
# ============================================================================

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Entities for extraction.xlsx")
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_output")
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB per file
ALLOWED_EXTENSIONS = {".pdf"}

# Ensure directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================================
# JOB TRACKING
# ============================================================================

class JobStatus:
    """In-memory job tracking."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class StepLog:
    """A single step log entry."""
    def __init__(self, step: str, status: str = "pending", progress: float = 0.0, message: str = ""):
        self.step = step
        self.status = status  # "pending", "active", "completed", "failed"
        self.progress = progress  # 0-100
        self.message = message
        self.timestamp = datetime.now()

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }


class Job:
    """Represents an extraction job."""
    def __init__(self, job_id: str, file_count: int):
        self.job_id = job_id
        self.status = JobStatus.PENDING
        self.created_at = datetime.now()
        self.completed_at: Optional[datetime] = None
        self.file_count = file_count
        self.results: list[dict] = []
        self.output_files: list[str] = []
        self.error: str = ""
        # Step tracking for real-time progress
        self.steps: list[StepLog] = []
        self.current_file: str = ""  # Currently processing filename
        self.overall_progress: float = 0.0  # 0-100

    def update_step(self, step: str, status: str = "active", progress: float = 0.0, message: str = ""):
        """Update or add a step log entry."""
        # Find existing step or create new one
        existing = next((s for s in self.steps if s.step == step), None)
        if existing:
            existing.status = status
            existing.progress = progress
            existing.message = message
            existing.timestamp = datetime.now()
        else:
            self.steps.append(StepLog(step, status, progress, message))

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "file_count": self.file_count,
            "results": self.results,
            "output_files": [os.path.basename(f) for f in self.output_files],
            "error": self.error,
            "current_file": self.current_file,
            "overall_progress": self.overall_progress,
            "steps": [s.to_dict() for s in self.steps],
        }


# In-memory job store (for production, use Redis or a database)
jobs: dict[str, Job] = {}

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="EWS Annual Report Extraction API",
    description="Extract financial data from annual report PDFs into Excel templates",
    version="1.0.0",
)

# CORS middleware — allows browser requests from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("ews_api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ============================================================================
# BACKGROUND PROCESSING (synchronous — runs in thread pool via BackgroundTasks)
# ============================================================================

def run_extraction_job(job: Job, pdf_configs: list[dict], use_llm: bool = False):
    """
    Run the extraction pipeline for each PDF in the job (synchronous).

    This is called by FastAPI's BackgroundTasks after the response is sent.
    It runs in a separate thread, so it doesn't block the event loop.

    Uses SmartExtractionAgent which auto-detects financial statement pages,
    extracts tables deterministically, and maps to the Excel template.

    Args:
        job: The Job object to track progress.
        pdf_configs: List of dicts with keys: pdf_path, year, original_filename.
        use_llm: Whether to enable LLM for page identification fallback.
    """
    job.status = JobStatus.PROCESSING

    # Initialize step tracking
    step_names = [
        "Finding financial statement pages",
        "Detecting financial year",
        "Filtering standalone pages",
        "Extracting Balance Sheet",
        "Extracting P&L Statement",
        "Extracting Cash Flow Statement",
        "Mapping Balance Sheet data",
        "Mapping P&L data",
        "Mapping Cash Flow data",
        "Writing to Excel template",
        "Computing completeness",
    ]
    for step_name in step_names:
        job.update_step(step_name, status="pending", progress=0)

    for i, config in enumerate(pdf_configs):
        pdf_path = config["pdf_path"]
        year = config["year"]
        original_filename = config["original_filename"]

        # Update current file being processed
        job.current_file = original_filename
        file_base_progress = (i / len(pdf_configs)) * 100
        file_progress_weight = 100 / len(pdf_configs)

        try:
            result = _run_single_extraction(
                pdf_path,
                year,
                original_filename,
                use_llm,
                job=job,
                file_base_progress=file_base_progress,
                file_progress_weight=file_progress_weight,
            )

            job.results.append(result)

            if result["success"]:
                job.output_files.append(result["output_path"])
            else:
                logger.warning(
                    f"Job {job.job_id}: Extraction failed for {original_filename}: {result.get('error', 'Unknown')}"
                )

        except Exception as e:
            logger.error(f"Job {job.job_id}: Exception processing {original_filename}: {e}", exc_info=True)
            job.results.append({
                "filename": original_filename,
                "year": year,
                "success": False,
                "error": str(e),
            })

    # Mark all remaining steps as completed
    for step in job.steps:
        if step.status != "completed":
            step.status = "completed"
            step.progress = 100

    # Update job status
    all_success = all(r.get("success", False) for r in job.results)
    job.status = JobStatus.COMPLETED if all_success else JobStatus.FAILED
    job.overall_progress = 100
    job.completed_at = datetime.now()

    # Clean up uploaded PDFs
    for config in pdf_configs:
        try:
            if os.path.exists(config["pdf_path"]):
                os.remove(config["pdf_path"])
        except OSError:
            pass


def _run_single_extraction(
    pdf_path: str,
    year: int | None,
    original_filename: str,
    use_llm: bool = False,
    job: Optional[Job] = None,
    file_base_progress: float = 0.0,
    file_progress_weight: float = 100.0,
) -> dict:
    """
    Run the SmartExtractionAgent pipeline for a single PDF (synchronous).

    The agent auto-detects:
        - Which pages contain BS/P&L/CF statements
        - The financial year
        - Standalone vs Consolidated statements (prefers standalone)
        - Table structure and row mapping

    Args:
        pdf_path: Path to the PDF file.
        year: Financial year (None = auto-detect).
        original_filename: Original filename for output naming.
        use_llm: Whether to enable LLM fallback.
        job: Optional Job object for step tracking.
        file_base_progress: Base progress % for this file (multi-file jobs).
        file_progress_weight: Progress weight for this file (multi-file jobs).

    Returns a dict with extraction results.
    """
    from ews_agent.smart_agent import SmartExtractionAgent

    # Generate output path
    pdf_stem = Path(original_filename).stem
    year_str = str(year) if year else "auto"
    output_filename = f"{pdf_stem}_{year_str}_extracted.xlsx"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    logger.info(f"Starting extraction: {original_filename} (year={year or 'auto-detect'}, llm={use_llm})")

    # Define progress callback that updates the job
    def progress_callback(step: str, status: str, progress: float, message: str = ""):
        if job is not None:
            job.update_step(step, status=status, progress=progress, message=message)
            # Update overall progress based on step progress
            step_weights = {
                "Finding financial statement pages": 15,
                "Detecting financial year": 5,
                "Filtering standalone pages": 5,
                "Extracting Balance Sheet": 15,
                "Extracting P&L Statement": 15,
                "Extracting Cash Flow Statement": 15,
                "Mapping Balance Sheet data": 10,
                "Mapping P&L data": 5,
                "Mapping Cash Flow data": 5,
                "Writing to Excel template": 5,
                "Computing completeness": 5,
            }
            total_weight = sum(step_weights.values())
            weighted_progress = 0
            for s in job.steps:
                w = step_weights.get(s.step, 1)
                if s.status == "completed":
                    weighted_progress += w
                elif s.status == "active":
                    weighted_progress += w * (s.progress / 100)
            job.overall_progress = round(file_base_progress + (weighted_progress / total_weight) * file_progress_weight, 1)

    # Initialize LLM instance if requested
    llm_instance = None
    if use_llm:
        try:
            from ews_agent.llm_config import get_llm
            llm_instance = get_llm()
            logger.info(f"LLM instance created successfully for {original_filename}")
        except Exception as e:
            logger.warning(f"Failed to initialize LLM for {original_filename}: {e}. Falling back to deterministic-only mode.")
            llm_instance = None

    try:
        agent = SmartExtractionAgent(
            llm=llm_instance,
            use_llm=use_llm and llm_instance is not None,
            verify_with_llm=use_llm and llm_instance is not None,
            progress_callback=progress_callback,
        )

        result = agent.run(
            pdf_path=pdf_path,
            template_path=TEMPLATE_PATH,
            output_path=output_path,
            year=year,  # None = auto-detect
        )

        return {
            "filename": original_filename,
            "year": result.year,
            "success": len(result.errors) == 0,
            "error": "; ".join(result.errors) if result.errors else "",
            "output_path": result.output_path,
            "page_detection": {
                "balance_sheet": result.pages_found.balance_sheet,
                "profit_and_loss": result.pages_found.profit_and_loss,
                "cash_flow": result.pages_found.cash_flow,
                "changes_in_equity": result.pages_found.changes_in_equity,
                "detection_method": result.pages_found.detection_method,
            },
            "extraction_stats": {
                "bs_rows_extracted": result.bs_rows_extracted,
                "pl_rows_extracted": result.pl_rows_extracted,
                "cf_rows_extracted": result.cf_rows_extracted,
            },
            "mapping_stats": {
                "bs_mapped": result.bs_mapped,
                "pl_mapped": result.pl_mapped,
                "cf_mapped": result.cf_mapped,
            },
            "writing_stats": {
                "bs_written": result.bs_written,
                "pl_written": result.pl_written,
                "cf_written": result.cf_written,
            },
            "completeness": {
                "bs": f"{result.bs_completeness:.1%}",
                "pl": f"{result.pl_completeness:.1%}",
                "cf": f"{result.cf_completeness:.1%}",
                "overall": f"{result.overall_completeness:.1%}",
            },
        }

    except Exception as e:
        logger.error(f"Extraction failed for {original_filename}: {e}", exc_info=True)
        return {
            "filename": original_filename,
            "year": year,
            "success": False,
            "error": str(e),
            "output_path": "",
        }


# ============================================================================
# API ENDPOINTS
# ============================================================================

# Serve the web UI at root
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the web UI."""
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>EWS API Running</h1><p>Web UI not found. Use /docs for API docs.</p>")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    template_exists = os.path.exists(TEMPLATE_PATH)
    return {
        "status": "healthy" if template_exists else "degraded",
        "template_found": template_exists,
        "template_path": TEMPLATE_PATH,
        "active_jobs": sum(1 for j in jobs.values() if j.status in (JobStatus.PENDING, JobStatus.PROCESSING)),
        "total_jobs": len(jobs),
    }


def _extract_year_from_filename(filename: str) -> int | None:
    """
    Try to extract a financial year from the PDF filename.
    
    Indian financial year convention: FY "2017-18" means year ending
    March 31, 2018. We always return the ENDING year.
    
    Patterns matched (ordered by specificity):
        - "Annual-Report-2022-2023.pdf" → 2023 (4-digit both sides)
        - "AnnualReport2017-18.pdf" → 2018 (4-digit + 2-digit suffix)
        - "RajeshExportsAR202021.pdf" → 2021 (6-digit compact YYYY+YY)
        - "Report_FY2024.pdf" → 2024
        - "2023_Annual_Report.pdf" → 2023 (single year, low confidence)
    """
    import re
    name = Path(filename).stem
    
    # Pattern 1: "2022-2023" or "2022_2023" (4-digit both sides) → take second year
    m = re.search(r'(20\d{2})\s*[-_]\s*(20\d{2})', name)
    if m:
        year1, year2 = int(m.group(1)), int(m.group(2))
        if year2 == year1 + 1:
            return year2
    
    # Pattern 2: "2017-18" or "2017_18" (4-digit + 2-digit) → construct ending year
    m = re.search(r'(20\d{2})\s*[-_]\s*(\d{2})', name)
    if m:
        year1 = int(m.group(1))
        suffix = int(m.group(2))
        ending_year = 2000 + suffix
        if ending_year == year1 + 1:
            return ending_year
    
    # Pattern 3: "202021" or "202425" (6-digit compact YYYY+YY)
    # Handles filenames like "RajeshExportsAR202021" or "AR201920REL"
    m = re.search(r'(20\d{2})(\d{2})', name)
    if m:
        year1 = int(m.group(1))
        suffix = int(m.group(2))
        ending_year = 2000 + suffix
        if ending_year == year1 + 1:
            return ending_year
    
    # Pattern 4: "FY2024" or "fy2024"
    m = re.search(r'FY\s*(20\d{2})', name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    
    # Pattern 5: any 4-digit year 2000-2099 (lowest confidence)
    m = re.search(r'(20\d{2})', name)
    if m:
        return int(m.group(1))
    
    return None


def parse_page_range(page_str: str) -> list[int] | None:
    """
    Parse a page range string into a list of page numbers.

    Examples:
        "45-60" -> [45, 46, ..., 60]
        "45,47,50" -> [45, 47, 50]
        "45-50,55,60-65" -> [45, 46, ..., 50, 55, 60, 61, ..., 65]
        "" -> None (all pages)
    """
    if not page_str or not page_str.strip():
        return None

    pages = []
    for part in page_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.extend(range(int(start), int(end) + 1))
        else:
            pages.append(int(part))
    return pages


@app.post("/extract")
async def extract(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(..., description="One or more PDF annual reports"),
    years: str = Form("", description="Financial year(s), comma-separated. Empty = auto-detect from PDF."),
    use_llm: bool = Form(False, description="Enable LLM for page identification fallback"),
):
    """
    Upload one or more PDF annual reports and extract financial data.

    The agent automatically:
        - Detects which pages contain BS/P&L/CF statements
        - Detects the financial year from filename or PDF content
        - Prefers standalone over consolidated statements
        - Extracts table data deterministically (like Excel's "Get Data from PDF")
        - Maps extracted rows to the template using fuzzy matching

    The years parameter is optional. If empty, the year is auto-detected from
    the PDF filename (e.g., "Annual-Report-2022-2023.pdf" → 2023) or from
    the PDF content. If provided, it can be a single year (applied to all files)
    or comma-separated years matching the number of files.

    Returns a job_id that can be used to check status and download results.
    """
    # Validate template
    if not os.path.exists(TEMPLATE_PATH):
        raise HTTPException(status_code=500, detail=f"Template file not found: {TEMPLATE_PATH}")

    # Validate file count
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 files per request")

    # Parse years — optional, comma-separated
    parsed_years: list[int | None] = []
    if years.strip():
        try:
            parsed_years = [int(y.strip()) for y in years.split(",") if y.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid year format: '{years}'. Use comma-separated integers.")
        
        if len(parsed_years) == 1 and len(files) > 1:
            parsed_years = parsed_years * len(files)
        elif len(parsed_years) != len(files):
            raise HTTPException(
                status_code=400,
                detail=f"Number of years ({len(parsed_years)}) must match number of files ({len(files)}), "
                       f"or provide a single year to apply to all files",
            )
    else:
        # Auto-detect: try filename first, then PDF content (None = let agent detect)
        parsed_years = [None] * len(files)
        for i, file in enumerate(files):
            fname = file.filename or f"upload_{i}.pdf"
            year_from_name = _extract_year_from_filename(fname)
            if year_from_name:
                parsed_years[i] = year_from_name
                logger.info(f"Auto-detected year {year_from_name} from filename: {fname}")

    # Validate and save uploaded files
    pdf_configs = []
    job_id = str(uuid.uuid4())[:8]
    job_upload_dir = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(job_upload_dir, exist_ok=True)

    for i, file in enumerate(files):
        # Validate extension
        ext = Path(file.filename).suffix.lower() if file.filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            # Clean up
            shutil.rmtree(job_upload_dir, ignore_errors=True)
            raise HTTPException(
                status_code=400,
                detail=f"File '{file.filename}' has unsupported extension '{ext}'. Only PDF files are allowed.",
            )

        # Save uploaded file
        save_path = os.path.join(job_upload_dir, file.filename or f"upload_{i}.pdf")
        try:
            content = await file.read()
            if len(content) > MAX_FILE_SIZE:
                shutil.rmtree(job_upload_dir, ignore_errors=True)
                raise HTTPException(
                    status_code=400,
                    detail=f"File '{file.filename}' exceeds maximum size of {MAX_FILE_SIZE // (1024*1024)}MB",
                )
            with open(save_path, "wb") as f:
                f.write(content)
        except HTTPException:
            raise
        except Exception as e:
            shutil.rmtree(job_upload_dir, ignore_errors=True)
            raise HTTPException(status_code=500, detail=f"Failed to save file '{file.filename}': {str(e)}")

        pdf_configs.append({
            "pdf_path": save_path,
            "year": parsed_years[i],  # None = auto-detect from PDF content
            "original_filename": file.filename or f"upload_{i}.pdf",
        })

    # Create job
    job = Job(job_id=job_id, file_count=len(files))
    jobs[job_id] = job

    # Add background task — FastAPI runs this after sending the response
    background_tasks.add_task(run_extraction_job, job, pdf_configs, use_llm)

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "status": JobStatus.PENDING,
            "message": f"Processing {len(files)} PDF(s). Use /status/{job_id} to check progress.",
            "files": [c["original_filename"] for c in pdf_configs],
            "years": [c["year"] for c in pdf_configs],
        },
    )


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    """Get the status of an extraction job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    return job.to_dict()


@app.get("/download/{job_id}")
async def download_results(job_id: str):
    """
    Download extraction results.

    If there's a single output file, returns it directly as an Excel file.
    If there are multiple output files, returns a ZIP archive.
    """
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
        raise HTTPException(status_code=409, detail=f"Job '{job_id}' is still {job.status}. Try again later.")

    if not job.output_files:
        raise HTTPException(status_code=404, detail=f"No output files available for job '{job_id}'")

    # Verify all output files exist
    existing_files = [f for f in job.output_files if os.path.exists(f)]
    if not existing_files:
        raise HTTPException(status_code=404, detail="Output files have been removed or are unavailable")

    if len(existing_files) == 1:
        # Single file: return directly
        filepath = existing_files[0]
        filename = os.path.basename(filepath)
        return FileResponse(
            path=filepath,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        # Multiple files: return as ZIP
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for filepath in existing_files:
                filename = os.path.basename(filepath)
                zf.write(filepath, filename)
        zip_buffer.seek(0)

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=extraction_results_{job_id}.zip"
            },
        )


@app.get("/download/{job_id}/{filename}")
async def download_single_file(job_id: str, filename: str):
    """Download a single output file from a job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
        raise HTTPException(status_code=409, detail=f"Job '{job_id}' is still {job.status}")

    # Find the requested file
    for filepath in job.output_files:
        if os.path.basename(filepath) == filename:
            if os.path.exists(filepath):
                return FileResponse(
                    path=filepath,
                    filename=filename,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            else:
                raise HTTPException(status_code=404, detail=f"File '{filename}' no longer exists")

    raise HTTPException(status_code=404, detail=f"File '{filename}' not found in job '{job_id}'")


@app.get("/jobs")
async def list_jobs():
    """List all jobs (most recent first)."""
    sorted_jobs = sorted(jobs.values(), key=lambda j: j.created_at, reverse=True)
    return {
        "total": len(sorted_jobs),
        "jobs": [j.to_dict() for j in sorted_jobs[:50]],  # Limit to 50 most recent
    }


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and its output files."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if job.status in (JobStatus.PENDING, JobStatus.PROCESSING):
        raise HTTPException(status_code=409, detail=f"Cannot delete job '{job_id}' while it is {job.status}")

    # Clean up output files
    for filepath in job.output_files:
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except OSError:
            pass

    # Clean up upload directory
    upload_dir = os.path.join(UPLOAD_DIR, job_id)
    if os.path.exists(upload_dir):
        shutil.rmtree(upload_dir, ignore_errors=True)

    # Remove from job store
    del jobs[job_id]

    return {"message": f"Job '{job_id}' deleted"}


# ============================================================================
# RAG PROXY ENDPOINTS
# ============================================================================
# These endpoints proxy requests to the RAG pipeline running on port 8081.
# This allows the browser to talk to a single port (8080) while the RAG
# pipeline runs as an isolated service on 8081.

import httpx

RAG_SERVICE_URL = os.environ.get("RAG_SERVICE_URL", "http://localhost:8081")


@app.post("/rag/upload")
async def rag_upload(file: UploadFile = File(...)):
    """Proxy: Upload PDF to RAG vector store."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            content = await file.read()
            response = await client.post(
                f"{RAG_SERVICE_URL}/rag/upload",
                files={"file": (file.filename, content, "application/pdf")},
            )
            return JSONResponse(status_code=response.status_code, content=response.json())
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="RAG service unavailable. Make sure rag_app is running on port 8081.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"RAG proxy error: {str(e)}")


@app.delete("/rag/delete")
async def rag_delete(filename: str):
    """Proxy: Delete PDF from RAG vector store."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.delete(
                f"{RAG_SERVICE_URL}/rag/delete",
                params={"filename": filename},
            )
            return JSONResponse(status_code=response.status_code, content=response.json())
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="RAG service unavailable")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"RAG proxy error: {str(e)}")


@app.get("/rag/list")
async def rag_list():
    """Proxy: List PDFs in RAG vector store."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(f"{RAG_SERVICE_URL}/rag/list")
            return JSONResponse(status_code=response.status_code, content=response.json())
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="RAG service unavailable")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"RAG proxy error: {str(e)}")


@app.get("/rag/stats")
async def rag_stats():
    """Proxy: Get RAG vector store statistics."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(f"{RAG_SERVICE_URL}/rag/stats")
            return JSONResponse(status_code=response.status_code, content=response.json())
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="RAG service unavailable")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"RAG proxy error: {str(e)}")


@app.post("/rag/ask")
async def rag_ask(request: dict):
    """Proxy: Ask question to RAG Q/A chatbot."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                f"{RAG_SERVICE_URL}/rag/ask",
                json=request,
            )
            return JSONResponse(status_code=response.status_code, content=response.json())
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="RAG service unavailable")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"RAG proxy error: {str(e)}")


@app.post("/rag/clear-chat")
async def rag_clear_chat(session_id: str = "default"):
    """Proxy: Clear RAG chat session."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{RAG_SERVICE_URL}/rag/clear-chat",
                params={"session_id": session_id},
            )
            return JSONResponse(status_code=response.status_code, content=response.json())
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="RAG service unavailable")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"RAG proxy error: {str(e)}")


@app.post("/rag/validate")
async def rag_validate(request: dict):
    """Proxy: Run CA RAG agent validation on extraction Excel."""
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            response = await client.post(
                f"{RAG_SERVICE_URL}/rag/validate",
                json=request,
            )
            return JSONResponse(status_code=response.status_code, content=response.json())
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="RAG service unavailable")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"RAG proxy error: {str(e)}")


@app.get("/rag/health")
async def rag_health():
    """Proxy: Check RAG service health."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{RAG_SERVICE_URL}/rag/health")
            return JSONResponse(status_code=response.status_code, content=response.json())
        except httpx.ConnectError:
            return JSONResponse(status_code=200, content={"status": "unavailable", "message": "RAG service not running on port 8081"})
        except Exception as e:
            return JSONResponse(status_code=200, content={"status": "error", "message": str(e)})


@app.get("/rag/progress/{session_id}")
async def rag_progress(session_id: str):
    """Proxy: Get CA RAG validation progress."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{RAG_SERVICE_URL}/rag/progress/{session_id}")
            return JSONResponse(status_code=response.status_code, content=response.json())
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="RAG service unavailable")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"RAG proxy error: {str(e)}")


@app.get("/rag/download/{filename}")
async def rag_download_file(filename: str):
    """
    Download a RAG-validated Excel file from the api_output directory.
    
    The CA RAG agent saves color-coded Excel files as {base}_rag_validated.xlsx
    in the same directory as the original extraction output (api_output/).
    This endpoint serves those files for download.
    """
    # Security: only allow .xlsx files and prevent path traversal
    if not filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files can be downloaded")
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found. The RAG-validated Excel may not have been generated yet.")
    
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/rag/prompt-excel")
async def rag_prompt_excel():
    """
    Proxy: Download a reference Excel showing all RAG questions per template item.
    
    The prompt Excel lets users review exactly what the CA RAG agent will ask
    for each line item before running validation.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(f"{RAG_SERVICE_URL}/rag/prompt-excel")
            if response.status_code == 200:
                from fastapi.responses import StreamingResponse as SR
                return SR(
                    io.BytesIO(response.content),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=rag_prompt_reference.xlsx"},
                )
            return JSONResponse(status_code=response.status_code, content=response.json())
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="RAG service unavailable")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"RAG proxy error: {str(e)}")


# ============================================================================
# STARTUP / SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup():
    """Validate template on startup."""
    if not os.path.exists(TEMPLATE_PATH):
        logger.error(f"Template file not found: {TEMPLATE_PATH}")
    else:
        logger.info(f"Template file found: {TEMPLATE_PATH}")

    logger.info("EWS Extraction API started")


@app.on_event("shutdown")
async def shutdown():
    """Clean up on shutdown."""
    logger.info("EWS Extraction API shutting down")


# ============================================================================
# MAIN (for direct execution)
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
