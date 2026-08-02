"""Annual-report extraction routes bridged to the qwen-onprem pipeline."""
from __future__ import annotations

import asyncio
import io
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter(prefix="/api/extract", tags=["extraction"])

_EXTERNAL_ROOT = Path(__file__).resolve().parents[4] / "_external_ews"
_EXTERNAL_GRAPH = _EXTERNAL_ROOT / "graph"

_EXTERNAL_READY = False
_EXTERNAL_ERROR: str | None = None

if _EXTERNAL_ROOT.exists():
    import sys as _sys

    for _path in (_EXTERNAL_ROOT, _EXTERNAL_GRAPH):
        _path_str = str(_path)
        if _path_str not in _sys.path:
            _sys.path.insert(0, _path_str)

try:
    from sources.annual_report.extraction_pipeline import run_full_extraction
    from sources.annual_report.vlm_extractor import vlm_extract_all, vlm_extract_to_excel

    _EXTERNAL_READY = True
except Exception as exc:  # pragma: no cover - guarded by status endpoint
    _EXTERNAL_ERROR = str(exc)


EXTRACTED_FINANCIALS_KEYS = [
    "name", "sector", "industry", "revenue", "ebitda", "ebit", "pat",
    "net_worth", "total_debt", "cash",
]


def _is_wired() -> bool:
    return _EXTERNAL_READY


async def _save_upload(tmp_dir: Path, upload: UploadFile) -> Path:
    dest = tmp_dir / (upload.filename or "report.pdf")
    data = await upload.read()
    dest.write_bytes(data)
    return dest


def _as_json_response(payload: dict[str, Any]) -> JSONResponse:
    return JSONResponse(content=payload)


def _build_zip(pdf_path: Path, result: dict[str, Any], excel_bytes: bytes, *, suffix: str) -> StreamingResponse:
    json_bytes = json.dumps(result, indent=2, default=str).encode("utf-8")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{pdf_path.stem}_{suffix}.json", json_bytes)
        zf.writestr(f"{pdf_path.stem}_{suffix}.xlsx", excel_bytes)
    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{pdf_path.stem}_{suffix}.zip"'},
    )


@router.get("")
def extract_status():
    return {
        "configured": _is_wired(),
        "returns": EXTRACTED_FINANCIALS_KEYS,
        "pipelines": ["json", "excel", "zip", "full"],
        "external_root": str(_EXTERNAL_ROOT) if _EXTERNAL_ROOT.exists() else None,
        "note": "qwen-onprem annual-report pipeline bridge",
        "error": _EXTERNAL_ERROR if not _EXTERNAL_READY else None,
    }


@router.post("")
async def extract(file: UploadFile = File(...), dpi: int = Query(150, ge=72, le=400)):
    if not _is_wired():
        raise HTTPException(status_code=501, detail=f"Extraction pipeline not available: {_EXTERNAL_ERROR}")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        pdf_path = await _save_upload(tmp_dir, file)
        result = await asyncio.to_thread(vlm_extract_all, pdf_path=pdf_path, dpi=dpi)
        return _as_json_response(result)


@router.post("/excel")
async def extract_excel(file: UploadFile = File(...), dpi: int = Query(150, ge=72, le=400)):
    if not _is_wired():
        raise HTTPException(status_code=501, detail=f"Extraction pipeline not available: {_EXTERNAL_ERROR}")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        pdf_path = await _save_upload(tmp_dir, file)
        excel_bytes = await asyncio.to_thread(vlm_extract_to_excel, pdf_path=pdf_path, dpi=dpi)
        return StreamingResponse(
            io.BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{pdf_path.stem}_vlm_output.xlsx"'},
        )


@router.post("/zip")
async def extract_zip(file: UploadFile = File(...), dpi: int = Query(150, ge=72, le=400)):
    if not _is_wired():
        raise HTTPException(status_code=501, detail=f"Extraction pipeline not available: {_EXTERNAL_ERROR}")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        pdf_path = await _save_upload(tmp_dir, file)
        result = await asyncio.to_thread(vlm_extract_all, pdf_path=pdf_path, dpi=dpi)
        excel_bytes = await asyncio.to_thread(vlm_extract_to_excel, pdf_path=pdf_path, dpi=dpi)
        return _build_zip(pdf_path, result, excel_bytes, suffix="extracted")


@router.post("/full")
async def extract_full(
    file: UploadFile = File(...),
    dpi: int = Query(150, ge=72, le=400),
    use_llm_taxonomy: bool = Query(True),
):
    if not _is_wired():
        raise HTTPException(status_code=501, detail=f"Extraction pipeline not available: {_EXTERNAL_ERROR}")

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_dir = Path(tmp_str)
        pdf_path = await _save_upload(tmp_dir, file)
        result = await asyncio.to_thread(
            run_full_extraction,
            pdf_path=pdf_path,
            dpi=dpi,
            use_llm_taxonomy=use_llm_taxonomy,
        )
        excel_bytes = await asyncio.to_thread(vlm_extract_to_excel, pdf_path=pdf_path, dpi=dpi)
        return _build_zip(pdf_path, result, excel_bytes, suffix="full_extraction")
