"""Root entry point for the Financial Tables Extractor API.

Run from the project root::

    python -m uvicorn app:app --host 127.0.0.1 --port 8080 --reload

Using ``python -m uvicorn`` ensures the same Python interpreter that has
all dependencies installed is used (avoids issues with multiple Python
versions on the system).

This simply re-exports the FastAPI application from
``graph.app.financial_tables_api`` so that the app file lives at the
project root while all implementation code stays inside ``graph/``.
"""

import sys
from pathlib import Path

# Ensure the project root and graph/ are on sys.path so that
# ``sources.annual_report.*`` and ``db`` resolve correctly.
_PROJECT_ROOT = str(Path(__file__).resolve().parent)
_GRAPH_DIR = str(Path(__file__).resolve().parent / "graph")

for _p in (_PROJECT_ROOT, _GRAPH_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from graph.app.financial_tables_api import app  # noqa: E402

__all__ = ["app"]
