"""
database/user_db.py — User tracking & access control for TV E-Vardhan.

Tables in TV_E-Vardhan.db
═════════════════════════
    1. companies         — Full company data (mirror of comps_v2.db with all columns
                           including code, year_end). 3,772+ listed Indian companies.
    2. users             — User login & access control (username, password, role, etc.)
    3. transaction_data  — Structured log of every user action: step 1 inputs (subject
                           company & financials), step 2 filters (sector, sub-sector,
                           thresholds), step 3 peer selections, step 4 valuation results.
                           Also captures login (step 0) and sign-out (step 99).

Uses raw sqlite3 from the Python standard library — no ORM.
All SQL is standard and PostgreSQL-compatible (no SQLite-specific syntax).
"""

import os
import json
import uuid as _uuid
import sqlite3
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
USER_DB = os.path.join(_HERE, "TV_E-Vardhan.db")
COMP_DB = os.path.join(_HERE, "comps_v2.db")

# ---------------------------------------------------------------------------
# Schema — written so that each CREATE TABLE runs with IF NOT EXISTS,
# making init_user_db() idempotent.
# ---------------------------------------------------------------------------

_SCHEMA_COMPANIES = """
CREATE TABLE IF NOT EXISTS companies (
    code            INTEGER,
    name            TEXT,
    sector          TEXT,
    industry        TEXT,
    revenue         REAL,
    ebitda          REAL,
    pat             REAL,
    net_worth       REAL,
    total_debt      REAL,
    net_debt        REAL,
    cash            REAL,
    market_cap      REAL,
    enterprise_value REAL,
    pe              REAL,
    ev_ebitda       REAL,
    ev_revenue      REAL,
    mktcap_sales    REAL,
    mode            TEXT,
    year_end        REAL
);
"""

_SCHEMA_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    UNIQUE NOT NULL,
    password_hash   TEXT    NOT NULL DEFAULT '',
    full_name       TEXT    NOT NULL DEFAULT '',
    role            TEXT    NOT NULL DEFAULT 'user',
    is_active       INTEGER NOT NULL DEFAULT 1,
    last_login      TEXT    NOT NULL DEFAULT '',
    created_at      TEXT    NOT NULL DEFAULT ''
);
"""

_SCHEMA_TRANSACTION = """
CREATE TABLE IF NOT EXISTS transaction_data (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid            TEXT    NOT NULL,
    username        TEXT    NOT NULL,
    step_number     INTEGER NOT NULL DEFAULT 0,
    action          TEXT    NOT NULL DEFAULT '',

    -- Step 1: Subject Company inputs
    company_name    TEXT    DEFAULT '',
    sector          TEXT    DEFAULT '',
    sub_sector      TEXT    DEFAULT '',
    revenue         REAL    DEFAULT NULL,
    ebitda          REAL    DEFAULT NULL,
    pat             REAL    DEFAULT NULL,
    net_worth       REAL    DEFAULT NULL,
    total_debt      REAL    DEFAULT NULL,
    cash            REAL    DEFAULT NULL,
    valuation_matrices TEXT DEFAULT '',

    -- Step 2: Screening / filter inputs
    screen_sector       TEXT    DEFAULT '',
    screen_sub_sector   TEXT    DEFAULT '',
    threshold_revenue_min  REAL DEFAULT NULL,
    threshold_revenue_max  REAL DEFAULT NULL,
    threshold_ebitda_min   REAL DEFAULT NULL,
    threshold_ebitda_max   REAL DEFAULT NULL,
    threshold_pat_min      REAL DEFAULT NULL,
    threshold_pat_max      REAL DEFAULT NULL,

    -- Step 3: Peer selection
    peers_selected   TEXT    DEFAULT '',
    peer_count       INTEGER DEFAULT 0,

    -- Step 4: Valuation results
    ev_ebitda_median REAL DEFAULT NULL,
    ev_revenue_median REAL DEFAULT NULL,
    pe_median        REAL DEFAULT NULL,
    concluded_value  REAL DEFAULT NULL,
    value_min        REAL DEFAULT NULL,
    value_max        REAL DEFAULT NULL,

    -- Catch-all JSON for any additional data
    input_data       TEXT    DEFAULT '{}',

    created_at       TEXT    NOT NULL DEFAULT ''
);
"""

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now():
    """UTC ISO-8601 timestamp — portable across SQLite and PostgreSQL."""
    return datetime.now(timezone.utc).isoformat()


def _connect():
    """Open TV_E-Vardhan.db with row factory enabled."""
    con = sqlite3.connect(USER_DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def init_user_db():
    """Create all 3 tables if they do not exist, then seed the demo user and
    populate the companies table from comps_v2.db (if empty)."""
    con = _connect()
    try:
        con.executescript(_SCHEMA_COMPANIES + _SCHEMA_USERS + _SCHEMA_TRANSACTION)
        con.commit()

        # Seed demo user if the table is empty
        count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            con.execute(
                "INSERT INTO users (username, password_hash, full_name, role, is_active, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("demo@valuetech.com", "", "Demo User", "user", 1, _now()),
            )
            con.commit()

        # Populate companies from comps_v2.db if empty
        comp_count = con.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        if comp_count == 0 and os.path.exists(COMP_DB):
            _populate_companies(con)
    finally:
        con.close()


def _populate_companies(con):
    """Copy company rows from comps_v2.db into the companies table."""
    if not os.path.exists(COMP_DB):
        return
    src = sqlite3.connect(COMP_DB)
    src.row_factory = sqlite3.Row
    try:
        rows = src.execute(
            "SELECT code, name, sector, industry, revenue, ebitda, pat, "
            "net_worth, total_debt, net_debt, cash, market_cap, enterprise_value, "
            "pe, ev_ebitda, ev_revenue, mktcap_sales, mode, year_end FROM comps"
        ).fetchall()
        con.executemany(
            "INSERT INTO companies "
            "(code, name, sector, industry, revenue, ebitda, pat, net_worth, "
            "total_debt, net_debt, cash, market_cap, enterprise_value, "
            "pe, ev_ebitda, ev_revenue, mktcap_sales, mode, year_end) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [tuple(r) for r in rows],
        )
        con.commit()
    finally:
        src.close()


# ---------------------------------------------------------------------------
# User access control
# ---------------------------------------------------------------------------

def check_user_access(username: str) -> dict:
    """Return user record dict if the username has access, else None.
    Only active users (is_active=1) can log in."""
    if not username:
        return None
    con = _connect()
    try:
        row = con.execute(
            "SELECT id, username, password_hash, full_name, role, is_active, last_login, created_at "
            "FROM users WHERE username = ? AND is_active = 1",
            (username.strip(),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def update_last_login(username: str):
    """Set last_login to now for the given user."""
    con = _connect()
    try:
        con.execute(
            "UPDATE users SET last_login = ? WHERE username = ?",
            (_now(), username.strip()),
        )
        con.commit()
    finally:
        con.close()


def add_user(username: str, role: str = "user", full_name: str = "",
             password_hash: str = "") -> dict:
    """Insert a new user. Returns the new user record dict.
    Raises ValueError if username already exists."""
    username = username.strip()
    if not username:
        raise ValueError("username cannot be empty")
    con = _connect()
    try:
        con.execute(
            "INSERT INTO users (username, password_hash, full_name, role, is_active, created_at) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (username, password_hash, full_name, role, _now()),
        )
        con.commit()
        row = con.execute(
            "SELECT id, username, password_hash, full_name, role, is_active, last_login, created_at "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row)
    except sqlite3.IntegrityError:
        raise ValueError(f"username '{username}' already exists")
    finally:
        con.close()


def delete_user(username: str) -> bool:
    """Delete a user by username. Returns True if deleted, False if not found."""
    con = _connect()
    try:
        cur = con.execute("DELETE FROM users WHERE username = ?", (username.strip(),))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def get_all_users() -> list:
    """Return all user records (for admin view)."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT id, username, password_hash, full_name, role, is_active, last_login, created_at "
            "FROM users ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Trial / transaction data logging
# ---------------------------------------------------------------------------

def new_trial_uuid() -> str:
    """Generate a new UUID4 string for a trial."""
    return str(_uuid.uuid4())


def log_transaction(uuid: str, username: str, step_number: int,
                    action: str = "", **fields) -> dict:
    """Log one transaction row. Accepts structured fields matching the
    transaction_data schema, plus a catch-all input_data dict.

    Parameters
    ----------
    uuid        : trial session UUID
    username    : who performed the action
    step_number : 0=login, 1=subject_input, 2=screening, 3=peer_select, 4=valuation, 99=signout
    action      : descriptive label (e.g. 'login_disclaimer_accepted')
    **fields    : any of the structured columns (company_name, sector, sub_sector,
                  revenue, ebitda, pat, net_worth, total_debt, cash, valuation_matrices,
                  screen_sector, screen_sub_sector,
                  threshold_revenue_min, threshold_revenue_max,
                  threshold_ebitda_min, threshold_ebitda_max,
                  threshold_pat_min, threshold_pat_max,
                  peers_selected, peer_count,
                  ev_ebitda_median, ev_revenue_median, pe_median,
                  concluded_value, value_min, value_max,
                  input_data)
    """
    # Structured column names (excluding id, uuid, username, step_number, action, created_at)
    STRUCTURED_COLS = {
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
    }

    # Separate structured fields from extra data
    structured = {}
    extra = {}
    input_data_raw = fields.pop("input_data", None)

    for k, v in fields.items():
        if k in STRUCTURED_COLS:
            structured[k] = v
        else:
            extra[k] = v

    # Merge any pre-existing input_data dict with extra fields
    if isinstance(input_data_raw, dict):
        input_data_raw.update(extra)
        input_data_json = json.dumps(input_data_raw)
    elif extra:
        input_data_json = json.dumps(extra)
    elif input_data_raw:
        input_data_json = json.dumps(input_data_raw) if isinstance(input_data_raw, dict) else str(input_data_raw)
    else:
        input_data_json = "{}"

    # Build INSERT dynamically
    cols = ["uuid", "username", "step_number", "action", "input_data", "created_at"]
    vals = [uuid, username.strip(), step_number, action, input_data_json, _now()]

    for k, v in structured.items():
        cols.append(k)
        vals.append(v)

    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)

    con = _connect()
    try:
        con.execute(
            f"INSERT INTO transaction_data ({col_names}) VALUES ({placeholders})",
            vals,
        )
        con.commit()
        row = con.execute(
            "SELECT * FROM transaction_data WHERE id = last_insert_rowid()"
        ).fetchone()
        return dict(row)
    finally:
        con.close()


# Backward-compatible alias
log_trial = log_transaction


def get_transaction_data(username: str = None, uuid: str = None,
                         step_number: int = None) -> list:
    """Return transaction data, optionally filtered by username, uuid, or step."""
    con = _connect()
    try:
        q = "SELECT * FROM transaction_data"
        params = []
        clauses = []
        if username:
            clauses.append("username = ?")
            params.append(username.strip())
        if uuid:
            clauses.append("uuid = ?")
            params.append(uuid)
        if step_number is not None:
            clauses.append("step_number = ?")
            params.append(step_number)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY id DESC"
        rows = con.execute(q, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


# Backward-compatible aliases
get_search_data = get_transaction_data
get_all_search_data = lambda: get_transaction_data()


# ---------------------------------------------------------------------------
# Companies table (mirror of comps_v2.db)
# ---------------------------------------------------------------------------

def get_all_companies() -> list:
    """Return all company records from the companies table."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT code, name, sector, industry, revenue, ebitda, pat, "
            "net_worth, total_debt, net_debt, cash, market_cap, "
            "enterprise_value, pe, ev_ebitda, ev_revenue, mktcap_sales, mode, year_end "
            "FROM companies ORDER BY code"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def refresh_companies():
    """Re-populate the companies table from comps_v2.db."""
    if not os.path.exists(COMP_DB):
        return 0
    con = _connect()
    try:
        con.execute("DELETE FROM companies")
        _populate_companies(con)
        count = con.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        return count
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Admin: all tables overview
# ---------------------------------------------------------------------------

def admin_overview() -> dict:
    """Return counts and info from all 3 tables (for admin dashboard)."""
    con = _connect()
    try:
        user_count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        txn_count = con.execute("SELECT COUNT(*) FROM transaction_data").fetchone()[0]
        comp_count = con.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        return {
            "tables": {
                "users": {"count": user_count},
                "transaction_data": {"count": txn_count},
                "companies": {"count": comp_count},
            },
            "db_path": USER_DB,
        }
    finally:
        con.close()
