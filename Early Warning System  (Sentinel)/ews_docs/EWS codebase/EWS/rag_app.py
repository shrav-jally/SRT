"""
RAG Application — Isolated FastAPI server for RAG pipeline

Runs on port 8081 (separate from main EWS app on 8080).

Endpoints:
    POST /rag/upload       — Upload PDF, parse, store in vector DB
    DELETE /rag/delete     — Delete PDF from vector DB
    GET  /rag/list         — List stored PDFs
    GET  /rag/stats        — Vector store statistics
    POST /rag/ask          — Q/A chatbot
    POST /rag/clear-chat   — Clear chat session
    POST /rag/validate     — Run CA RAG agent on extraction Excel
    GET  /rag/health       — Health check
"""

import logging
import os
import shutil
import uuid
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag_agent import config
from rag_agent.pdf_parser import extract_pages, get_pdf_info
from rag_agent import vector_store
from rag_agent.qa_bot import ask_question, clear_session
from rag_agent.ca_rag_agent import run_ca_rag_validation, get_progress as get_rag_progress, generate_prompt_excel

logger = logging.getLogger(__name__)

app = FastAPI(
    title="EWS RAG Pipeline",
    description="RAG-based Q/A and CA validation for financial statement extraction",
    version="0.1.0",
)

# CORS — allow main EWS app and browser to call RAG API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure directories exist
os.makedirs(config.UPLOAD_DIR, exist_ok=True)
os.makedirs(config.RAG_OUTPUT_DIR, exist_ok=True)


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class AskRequest(BaseModel):
    question: str
    session_id: str = "default"
    filter_filename: Optional[str] = None
    top_k: int = 5


class ValidateRequest(BaseModel):
    extraction_excel_path: str
    pdf_filename: Optional[str] = None
    statement_types: list[str] = ["balance_sheet", "profit_and_loss", "cash_flow"]
    session_id: str = "default"


class DeleteRequest(BaseModel):
    filename: str


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/rag/health")
async def health():
    """Health check for RAG service."""
    try:
        stats = vector_store.get_stats()
        return {
            "status": "ok",
            "total_chunks": stats["total_chunks"],
            "total_pdfs": stats["total_pdfs"],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/rag/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Upload a PDF, parse it page-by-page, and store chunks in vector DB.

    Returns:
        Dict with filename, num_pages, num_chunks stored.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Save uploaded file
    upload_id = uuid.uuid4().hex[:8]
    upload_subdir = os.path.join(config.UPLOAD_DIR, upload_id)
    os.makedirs(upload_subdir, exist_ok=True)

    file_path = os.path.join(upload_subdir, file.filename)
    try:
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # Parse PDF into page chunks
    try:
        chunks = extract_pages(file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse PDF: {e}")

    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="No text could be extracted from this PDF. It may be scanned/image-based."
        )

    # Store chunks in vector DB
    try:
        num_stored = vector_store.store_chunks(chunks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store in vector DB: {e}")

    # Get PDF info
    info = get_pdf_info(file_path)

    return {
        "filename": file.filename,
        "upload_id": upload_id,
        "num_pages": info["num_pages"] if info else len(set(c.page_number for c in chunks)),
        "num_chunks": num_stored,
        "file_size_bytes": info["file_size_bytes"] if info else len(content),
        "message": f"Successfully uploaded and indexed {file.filename}",
    }


@app.delete("/rag/delete")
async def delete_pdf(filename: str):
    """
    Delete all chunks for a specific PDF from the vector DB.

    Query params:
        filename: The PDF filename to delete.
    """
    try:
        num_deleted = vector_store.delete_pdf(filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete from vector DB: {e}")

    if num_deleted == 0:
        raise HTTPException(status_code=404, detail=f"PDF '{filename}' not found in vector store")

    # Also remove from uploads directory
    for subdir in os.listdir(config.UPLOAD_DIR):
        subdir_path = os.path.join(config.UPLOAD_DIR, subdir)
        if os.path.isdir(subdir_path):
            for f in os.listdir(subdir_path):
                if f == filename:
                    os.remove(os.path.join(subdir_path, f))
                    # Remove empty subdir
                    if not os.listdir(subdir_path):
                        os.rmdir(subdir_path)

    return {
        "filename": filename,
        "num_chunks_deleted": num_deleted,
        "message": f"Deleted {num_deleted} chunks for '{filename}'",
    }


@app.get("/rag/list")
async def list_pdfs():
    """List all PDFs stored in the vector DB with chunk counts."""
    try:
        pdfs = vector_store.list_pdfs()
        return {"pdfs": pdfs, "total": len(pdfs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/rag/stats")
async def get_stats():
    """Get vector store statistics."""
    try:
        stats = vector_store.get_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rag/ask")
async def ask(request: AskRequest):
    """
    Ask a question using the RAG Q/A chatbot.

    The chatbot retrieves relevant chunks from the vector store and
    uses LLM to generate an answer grounded in the retrieved context.
    """
    try:
        result = ask_question(
            question=request.question,
            session_id=request.session_id,
            filter_filename=request.filter_filename,
            top_k=request.top_k,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Q/A failed: {e}")


@app.post("/rag/clear-chat")
async def clear_chat(session_id: str = "default"):
    """Clear a chat session's history."""
    clear_session(session_id)
    return {"message": f"Chat session '{session_id}' cleared"}


@app.post("/rag/validate")
async def validate_extraction(request: ValidateRequest, background_tasks: BackgroundTasks):
    """
    Run the CA RAG agent to validate and fill extraction results.

    This endpoint starts the validation in the background and returns
    a session_id that can be polled via /rag/progress/{session_id}.

    Color scheme:
    - YELLOW: RAG changed a value (original was different)
    - GREEN:  RAG filled a previously empty cell
    - LIGHT BLUE: RAG verified value matches (no change)
    """
    # Validate the extraction Excel exists
    if not os.path.exists(request.extraction_excel_path):
        raise HTTPException(
            status_code=404,
            detail=f"Extraction Excel not found: {request.extraction_excel_path}"
        )

    # Run validation in background
    background_tasks.add_task(
        _run_validation_bg,
        extraction_excel_path=request.extraction_excel_path,
        pdf_filename=request.pdf_filename,
        statement_types=request.statement_types,
        session_id=request.session_id,
    )

    return {
        "status": "started",
        "session_id": request.session_id,
        "message": "CA RAG validation started. Poll /rag/progress/{session_id} for progress.",
    }


def _run_validation_bg(
    extraction_excel_path: str,
    pdf_filename: str = None,
    statement_types: list = None,
    session_id: str = "default",
):
    """Background task for CA RAG validation."""
    try:
        result = run_ca_rag_validation(
            extraction_excel_path=extraction_excel_path,
            pdf_filename=pdf_filename,
            statement_types=statement_types,
            session_id=session_id,
        )
        # Store result in progress store
        _progress_results[session_id] = result
    except Exception as e:
        logger.error(f"CA RAG validation failed: {e}", exc_info=True)
        from rag_agent.ca_rag_agent import _progress_store
        if session_id in _progress_store:
            _progress_store[session_id]["status"] = "failed"
            _progress_store[session_id]["current_step"] = f"Failed: {str(e)}"
            _progress_store[session_id]["details"].append(f"ERROR: {str(e)}")


# Store for completed validation results
_progress_results = {}


@app.get("/rag/progress/{session_id}")
async def get_validation_progress(session_id: str):
    """
    Get the progress of a CA RAG validation session.

    Returns current step, progress %, completed items, and detail logs.
    When status is "completed", also includes the full validation result.
    """
    progress = get_rag_progress(session_id)
    result = dict(progress)

    # If completed, include the full result
    if progress.get("status") == "completed" and session_id in _progress_results:
        result["result"] = _progress_results[session_id]

    # If failed, include error info
    if progress.get("status") == "failed":
        result["error"] = progress.get("details", [])[-1] if progress.get("details") else "Unknown error"

    return result


@app.get("/rag/prompt-excel")
async def prompt_excel():
    """
    Generate and download a reference Excel showing exactly what questions
    the CA RAG agent will ask for each template item.

    This lets users review the RAG prompts before running validation.
    The Excel has one sheet per statement type (BS, P&L, CF) with columns:
        - Section, Template Item, RAG Question, Purpose (verify/fill)
    """
    try:
        output_path = generate_prompt_excel()
        from fastapi.responses import FileResponse
        return FileResponse(
            path=output_path,
            filename="rag_prompt_reference.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        logger.error(f"Failed to generate prompt Excel: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate prompt Excel: {str(e)}")


@app.on_event("startup")
async def startup():
    """Initialize vector store on startup."""
    logger.info("RAG Pipeline starting up...")
    try:
        stats = vector_store.get_stats()
        logger.info(
            f"Vector store ready: {stats['total_chunks']} chunks, "
            f"{stats['total_pdfs']} PDFs"
        )
    except Exception as e:
        logger.warning(f"Vector store initialization warning: {e}")
        logger.info("Vector store will be initialized on first use")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    logger.info("RAG Pipeline shutting down")


# ============================================================================
# RUN DIRECTLY
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "rag_app:app",
        host=config.RAG_APP_HOST,
        port=config.RAG_APP_PORT,
        reload=False,
        log_level="info",
    )
