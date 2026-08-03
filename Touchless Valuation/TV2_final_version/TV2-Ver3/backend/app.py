"""
app.py — Touchless Valuation : E-Vardhan: standalone FastAPI service.

Endpoints
  GET  /                         health check
  GET  /health                   health check (JSON)
  GET  /api/tool/sectors         Sector -> Industry taxonomy
  POST /api/tool/reset-cache     Reset in-memory cache
  POST /api/tool/screen          screen comparables by thresholds
  POST /api/tool/value           CCM valuation
  POST /api/tool/report          detailed HTML report
  --- User Tracking & Admin ---
  POST /api/auth/login           Check user access (login)
  POST /api/trial/log            Log a transaction step with structured data
  POST /api/trial/new-uuid       Generate a fresh UUID for a new trial session
  GET  /api/admin/overview       DB overview (table counts)
  GET  /api/admin/users          List all users
  POST /api/admin/users          Add a new user
  DELETE /api/admin/users        Delete a user
  GET  /api/admin/transaction-data  List transaction data (filterable)
  GET  /api/admin/search-data    List search/trial data (backward-compatible)
  GET  /api/admin/companies      List all companies (mirror)
  POST /api/admin/refresh-companies  Re-populate companies from comps_v2.db
"""

import os
import sys

# Add project root to sys.path so that `database` package is importable
_BACKEND = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_BACKEND)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, field_validator

from database import (sectors_with_availability, reset_cache, AS_OF,
                      MULTIPLE_SOURCE, dataset_meta,
                      init_user_db, check_user_access, update_last_login,
                      add_user, delete_user, get_all_users,
                      new_trial_uuid, log_transaction, log_trial,
                      get_transaction_data, get_search_data, get_all_search_data,
                      get_all_companies, refresh_companies, admin_overview)
from screening import screen
from valuation import value
from report import render_report

BASE = _BACKEND
PORT = int(os.environ.get("PORT", "8000"))

app = FastAPI(title="Touchless Valuation : E-Vardhan",
              description="CCM valuation on published comparable multiples. "
                          "Median multiple, no adjustments, range +/-5%.")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                   allow_headers=["*"])


@app.on_event("startup")
def _startup():
    """Initialise the user tracking database on first boot."""
    init_user_db()


def _err(code, message):
    return JSONResponse({"error": {"code": code, "message": message}},
                        status_code=code)


# ═══════════════════════════════════════════════════════════════════════════
# HEALTH / META
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "service": "E-Vardhan Valuation API"}


@app.get("/api/tool/sectors", tags=["tool"])
def sectors():
    reset_cache()
    return {"as_of": AS_OF, "multiple_source": MULTIPLE_SOURCE,
            "dataset": dataset_meta(), "sectors": sectors_with_availability()}


@app.get("/api/tool/dataset-meta", tags=["tool"])
def do_dataset_meta():
    return dataset_meta()


@app.post("/api/tool/reset-cache", tags=["tool"])
def do_reset_cache():
    reset_cache()
    return {"status": "ok", "message": "Cache cleared"}


# ═══════════════════════════════════════════════════════════════════════════
# SCREENING / VALUATION / REPORT
# ═══════════════════════════════════════════════════════════════════════════

class ScreenBodyRaw(BaseModel):
    sub_sector: str
    thresholds: dict = {}
    subject: dict = {}
    all: bool = False
    
    model_config = {"populate_by_name": True}
    
    @field_validator("all", mode="before")
    @classmethod
    def convert_all(cls, v):
        """Convert any input type to boolean."""
        if v is True or v == "true" or v == "True" or v == 1:
            return True
        if v is False or v is None or v == "false" or v == "False" or v == 0:
            return False
        return False


@app.post("/api/tool/screen", tags=["tool"])
def do_screen(body: ScreenBodyRaw):
    reset_cache()
    all_param = bool(body.all)
    result = screen(body.sub_sector, body.thresholds, body.subject or None, all=all_param)
    result["_debug"] = {
        "sub_sector_sent": body.sub_sector,
        "thresholds_sent": body.thresholds,
        "all_param_sent": all_param,
        "pool_size": result.get("pool_size", 0),
        "qualified": result.get("qualified", 0),
    }
    return result


_VALID_MATRICES = ("EV/Revenue", "EV/EBITDA", "P/E")


class ValueBody(BaseModel):
    subject: dict
    matrix: str = ""
    matrices: list = []
    sub_sector: str
    thresholds: dict = {}
    selected_peers: list = []
    disclaimer_accepted_date: str = ""


def _requested_matrices(body):
    """Selected matrices, de-duplicated and order-preserving."""
    raw = list(body.matrices) if body.matrices else ([body.matrix] if body.matrix else [])
    seen, out = set(), []
    for m in raw:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _value(body):
    matrices = _requested_matrices(body)
    if not matrices:
        return None, _err(422, "select at least one method: EV/Revenue, "
                               "EV/EBITDA or P/E")
    bad = [m for m in matrices if m not in _VALID_MATRICES]
    if bad:
        return None, _err(422, "invalid method(s): " + ", ".join(bad))
    sc = screen(body.sub_sector, body.thresholds, body.subject or None)
    comps = body.selected_peers or sc["comparables"]
    if not comps:
        return None, _err(422, "no comparable companies match the selected "
                               "sub-sector and thresholds")
    results = [value(body.subject, comps, m) for m in matrices]
    result = dict(results[0])
    result["matrices"] = matrices
    result["ccm_by_matrix"] = {r["matrix"]: r["ccm"] for r in results}
    result["screening"] = sc
    result["meta"] = {"as_of": AS_OF, "multiple_source": MULTIPLE_SOURCE,
                      "methods": ["CCM"], "range_basis": "+/- 5%",
                      "disclaimer_accepted_date": body.disclaimer_accepted_date or ""}
    if body.selected_peers:
        result["selected_peers"] = body.selected_peers
    return result, None


@app.post("/api/tool/value", tags=["tool"])
def do_value(body: ValueBody):
    result, err = _value(body)
    return err if err is not None else result


@app.post("/api/tool/report", tags=["tool"], response_class=HTMLResponse)
@app.get("/api/tool/report", tags=["tool"], response_class=HTMLResponse)
def do_report(body: ValueBody = None, print: bool = Query(False, alias="print")):
    # For GET requests, we return a minimal report page
    if not body or not body.subject:
        return HTMLResponse(
            "<html><head><title>Report</title></head><body>"
            "<p>Submit a POST request with valuation data to generate report.</p>"
            "</body></html>"
        )
    result, err = _value(body)
    if err is not None:
        return err
    html_content = render_report(result)
    if print:
        html_content = html_content.replace("</body>",
            "<script>window.addEventListener('load',()=>setTimeout(()=>window.print(),400));</script></body>")
    return HTMLResponse(html_content)


# ═══════════════════════════════════════════════════════════════════════════
# USER AUTH
# ═══════════════════════════════════════════════════════════════════════════

class LoginBody(BaseModel):
    username: str


@app.post("/api/auth/login", tags=["auth"])
def do_login(body: LoginBody):
    """Check whether the given username has access.
    Returns the user record on success, 401 on failure."""
    user = check_user_access(body.username)
    if not user:
        return _err(401, f"User '{body.username}' does not have access. "
                         "Contact your administrator.")
    update_last_login(body.username)
    return {"status": "ok", "user": user}


# ═══════════════════════════════════════════════════════════════════════════
# TRIAL / TRANSACTION LOGGING
# ═══════════════════════════════════════════════════════════════════════════

class TrialLogBody(BaseModel):
    uuid: str
    username: str
    step_number: int
    action: str = ""
    # Step 1: Subject company inputs
    company_name: str = ""
    sector: str = ""
    sub_sector: str = ""
    revenue: float = None
    ebitda: float = None
    pat: float = None
    net_worth: float = None
    total_debt: float = None
    cash: float = None
    valuation_matrices: str = ""
    # Step 2: Screening filters
    screen_sector: str = ""
    screen_sub_sector: str = ""
    threshold_revenue_min: float = None
    threshold_revenue_max: float = None
    threshold_ebitda_min: float = None
    threshold_ebitda_max: float = None
    threshold_pat_min: float = None
    threshold_pat_max: float = None
    # Step 3: Peer selection
    peers_selected: str = ""
    peer_count: int = None
    # Step 4: Valuation results
    ev_ebitda_median: float = None
    ev_revenue_median: float = None
    pe_median: float = None
    concluded_value: float = None
    value_min: float = None
    value_max: float = None
    # Catch-all for additional data
    trial_data: dict = {}


@app.post("/api/trial/log", tags=["trial"])
def do_log_trial(body: TrialLogBody):
    """Log a transaction step.  The frontend generates a UUID per trial session
    and logs structured step data as the user progresses through the workflow.
    Step 0=login, 1=subject_input, 2=screening, 3=peer_select, 4=valuation, 99=signout."""
    try:
        # Build structured fields from the body
        fields = {}
        structured_keys = [
            "company_name", "sector", "sub_sector",
            "revenue", "ebitda", "pat", "net_worth", "total_debt", "cash",
            "valuation_matrices",
            "screen_sector", "screen_sub_sector",
            "threshold_revenue_min", "threshold_revenue_max",
            "threshold_ebitda_min", "threshold_ebitda_max",
            "threshold_pat_min", "threshold_pat_max",
            "peers_selected", "peer_count",
            "ev_ebitda_median", "ev_revenue_median", "pe_median",
            "concluded_value", "value_min", "value_max",
        ]
        for k in structured_keys:
            v = getattr(body, k, None)
            if v is not None and v != "" and v != 0:
                fields[k] = v

        # Merge trial_data dict as input_data (for any extra fields)
        if body.trial_data:
            fields["input_data"] = body.trial_data

        record = log_transaction(
            body.uuid, body.username, body.step_number,
            action=body.action, **fields
        )
        return {"status": "ok", "record": record}
    except Exception as e:
        return _err(500, str(e))


@app.post("/api/trial/new-uuid", tags=["trial"])
def do_new_uuid():
    """Generate a fresh UUID for a new trial session."""
    return {"uuid": new_trial_uuid()}


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/admin/overview", tags=["admin"])
def do_admin_overview():
    """DB overview: table counts and metadata."""
    return admin_overview()


@app.get("/api/admin/users", tags=["admin"])
def do_admin_users():
    """List all users with access."""
    return {"users": get_all_users()}


class AddUserBody(BaseModel):
    username: str
    role: str = "user"
    full_name: str = ""


@app.post("/api/admin/users", tags=["admin"])
def do_admin_add_user(body: AddUserBody):
    """Add a new user (grant access)."""
    try:
        user = add_user(body.username, body.role, full_name=body.full_name)
        return {"status": "ok", "user": user}
    except ValueError as e:
        return _err(409, str(e))


class DeleteUserBody(BaseModel):
    username: str


@app.delete("/api/admin/users", tags=["admin"])
def do_admin_delete_user(body: DeleteUserBody):
    """Remove a user (revoke access)."""
    ok = delete_user(body.username)
    if not ok:
        return _err(404, f"User '{body.username}' not found")
    return {"status": "ok", "message": f"User '{body.username}' deleted"}


@app.get("/api/admin/transaction-data", tags=["admin"])
def do_admin_transaction_data(username: str = Query(None),
                               uuid: str = Query(None),
                               step_number: int = Query(None)):
    """List transaction data, optionally filtered by username, uuid, or step_number."""
    return {"data": get_transaction_data(username=username, uuid=uuid,
                                          step_number=step_number)}


@app.get("/api/admin/search-data", tags=["admin"])
def do_admin_search_data(username: str = Query(None), uuid: str = Query(None)):
    """List search/trial data (backward-compatible alias for transaction-data)."""
    return {"data": get_search_data(username=username, uuid=uuid)}


@app.get("/api/admin/companies", tags=["admin"])
def do_admin_companies():
    """List all companies from the mirror table."""
    return {"companies": get_all_companies()}


@app.post("/api/admin/refresh-companies", tags=["admin"])
def do_admin_refresh_companies():
    """Re-populate the companies table from comps_v2.db."""
    count = refresh_companies()
    return {"status": "ok", "companies_count": count}


# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    db_path = os.path.join(_ROOT, "database", "comps_v2.db")
    if not os.path.exists(db_path):
        print("WARNING: comps_v2.db not found in database/ folder.", flush=True)
    HOST = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("app:app", host=HOST, port=PORT, log_level="info")
