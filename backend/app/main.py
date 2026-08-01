"""
FastAPI application — the Python AI/valuation backend.

The Next.js app (frontend + its own API routes) is the user-facing layer and
calls into this service. CORS is open to localhost dev origins.

Run:  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routers import companies, extraction, intake

app = FastAPI(
    title="Comparable-Company Valuation Platform",
    version="3.0.0",
    description="Real-multiple comparable valuation over the Capitaline universe.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(companies.router)
app.include_router(extraction.router)
app.include_router(intake.router)

# Serve the prebuilt static frontend (frontend/out) same-origin, so the whole
# platform runs from one Python process — `python run.py`, no Node required.
_STATIC = Path(__file__).resolve().parent.parent.parent / "frontend" / "out"
if _STATIC.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC), html=True), name="ui")
else:
    @app.get("/")
    def root():
        return {"service": "valuation-platform", "docs": "/docs",
                "health": "/api/health",
                "note": "frontend/out not found — build with BUILD_STATIC=1 npm run build"}
