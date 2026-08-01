"""
VLM PDF-extraction interface — INTENTIONALLY A BLANK STUB.

The working vision-language extractor (annual-report PDF -> financials) lives in
the user's separate module and will be wired in here later. This file defines
the stable contract the rest of the platform depends on so the integration is a
drop-in: implement `extract_financials(pdf_bytes)` and the /api/extract endpoint
and the front-end "upload a PDF" flow light up unchanged.

Contract — return a dict shaped like ExtractedFinancials so it can be passed
straight to POST /api/value/custom as `target`.
"""
from __future__ import annotations

from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter(prefix="/api/extract", tags=["extraction"])

# The shape the VLM must return (keys line up with CustomTarget).
EXTRACTED_FINANCIALS_KEYS = [
    "name", "sector", "industry", "revenue", "ebitda", "ebit", "pat",
    "net_worth", "total_debt", "cash",
]


def extract_financials(pdf_bytes: bytes) -> dict:
    """Placeholder. Replace the body with a call into the working VLM extractor.
    Must return a dict with EXTRACTED_FINANCIALS_KEYS (values may be None)."""
    raise NotImplementedError("VLM extractor not wired in yet")


@router.get("")
def extract_status():
    """Advertises whether the VLM is configured — the UI uses this to decide
    whether to show the 'Upload PDF' path or fall back to the manual form."""
    try:
        configured = extract_financials.__doc__ is not None and _is_wired()
    except Exception:
        configured = False
    return {"configured": configured,
            "returns": EXTRACTED_FINANCIALS_KEYS,
            "note": "Blank stub — plug the working VLM extractor into "
                    "app/routers/extraction.py::extract_financials"}


def _is_wired() -> bool:
    # Flip to True once extract_financials is implemented for real.
    return False


@router.post("")
async def extract(file: UploadFile = File(...)):
    if not _is_wired():
        raise HTTPException(
            status_code=501,
            detail="VLM extraction not configured. Wire up "
                   "app/routers/extraction.py::extract_financials, or use "
                   "POST /api/value/custom with manually entered financials.",
        )
    data = await file.read()
    return extract_financials(data)
