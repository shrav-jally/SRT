"""
One-command launcher:  python run.py

Does everything needed on a fresh clone:
  1. checks Python version
  2. installs missing Python dependencies (pip, from backend/requirements.txt)
  3. loads .env — if GROQ_API_KEY is missing, asks once and saves it
     (Enter to skip: the engine then runs fully deterministic, no LLM step)
  4. ensures the comparables database exists (backend/data/comps.db ships in
     the repo; rebuilds from the Capitaline .xls extracts only if absent)
  5. starts the platform on ONE port and opens your browser

No Node/npm needed at runtime — the UI is a prebuilt static export served by
the Python backend.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

# Load .env early so PORT and other env vars are available.
_ROOT = Path(__file__).resolve().parent  # directory containing run.py
_envfile = _ROOT / ".env"
if _envfile.is_file():
    for _line in _envfile.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ[_k.strip()] = _v.strip()

ROOT = _ROOT
BACKEND = ROOT / "backend"
PORT = int(os.environ.get("PORT", "8000"))

REQUIRED = {  # import name -> pip spec
    "fastapi": "fastapi>=0.115",
    "uvicorn": "uvicorn[standard]>=0.30",
    "pydantic": "pydantic>=2.7",
    "xlrd": "xlrd==2.0.2",
    "multipart": "python-multipart>=0.0.9",
    "numpy": "numpy",
    "sklearn": "scikit-learn",
    "langgraph": "langgraph",
}


def step(msg: str) -> None:
    print(f"\n=== {msg}")


def ensure_python() -> None:
    if sys.version_info < (3, 10):
        sys.exit(f"Python 3.10+ required (you have {sys.version.split()[0]})")


def ensure_deps() -> None:
    missing = [spec for mod, spec in REQUIRED.items()
               if importlib.util.find_spec(mod) is None]
    if not missing:
        print("all Python dependencies present")
        return
    print("installing:", ", ".join(missing))
    subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])


def ensure_env() -> None:
    envfile = ROOT / ".env"
    if envfile.is_file() and "GROQ_API_KEY" in envfile.read_text(encoding="utf-8"):
        print(".env found (GROQ_API_KEY configured — LLM analyst enabled)")
        return
    print("No GROQ_API_KEY configured. The LLM analyst step is optional —")
    print("get a free key at https://console.groq.com/keys")
    try:
        key = input("Paste GROQ_API_KEY (or press Enter to skip): ").strip()
    except EOFError:
        key = ""
    if key:
        with open(envfile, "a", encoding="utf-8") as f:
            f.write(f"\nGROQ_API_KEY={key}\n")
        print("saved to .env — LLM analyst enabled")
    else:
        print("skipped — running fully deterministic (no LLM)")


def ensure_db() -> None:
    dbfile = BACKEND / "data" / "comps.db"
    if dbfile.is_file() and dbfile.stat().st_size > 1_000_000:
        print(f"comparables DB present ({dbfile.stat().st_size/1e6:.0f} MB)")
        return
    print("comps.db missing — rebuilding from the Capitaline .xls extracts...")
    subprocess.check_call([sys.executable, "-m", "app.etl.build_db"], cwd=BACKEND)


def refresh_drift() -> None:
    """Market-drift factor: how far the stored snapshot sits below today's
    market. Refreshed if missing or older than a week (needs internet;
    skipped silently offline, in which case no drift is applied)."""
    drift_file = BACKEND / "data" / "market_drift.json"
    fresh = False
    if drift_file.is_file():
        import json
        from datetime import datetime, timezone
        try:
            d = json.loads(drift_file.read_text(encoding="utf-8"))
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(d["computed_at"])).days
            fresh = age <= 7
            print(f"market drift x{d['drift_factor']} ({age}d old)"
                  + ("" if fresh else " — refreshing"))
        except Exception:
            pass
    if fresh:
        return
    try:
        subprocess.check_call([sys.executable, "-m", "app.engine.live_market"],
                              cwd=BACKEND, timeout=180)
    except Exception:
        print("could not refresh (offline?) — no drift adjustment applied")


def serve() -> None:
    url = f"http://localhost:{PORT}"
    print(f"\nPlatform: {url}   (API docs: {url}/docs)   Ctrl+C to stop")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, log_level="info")


if __name__ == "__main__":
    step("1/6 Python version")
    ensure_python()
    step("2/6 dependencies")
    ensure_deps()
    step("3/6 configuration (.env)")
    ensure_env()
    step("4/6 comparables database")
    ensure_db()
    step("5/6 live market drift")
    refresh_drift()
    step("6/6 starting")
    serve()
