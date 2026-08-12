"""
BGV Voice Agent — Database Module

SQLite database layer for the Background Verification (BGV)
Insufficiency Resolution Voice Agent. Uses standard-library sqlite3
with WAL mode for safe concurrent reads during active calls.

Tables
------
candidates, verification_components, insufficiencies,
conversation_logs, audit_trails, faqs
"""

import sqlite3
import os
import json
from datetime import datetime, date, timedelta

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "bgv_agent.db",
)


# ------------------------------------------------------------------
# Connection Management
# ------------------------------------------------------------------

def get_connection():
    """
    Return a new SQLite connection configured for the BGV agent.

    Each tool call should use its own connection so the FastMCP
    thread-pool never shares a connection object across threads.
    """
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ------------------------------------------------------------------
# Schema Initialisation
# ------------------------------------------------------------------

def init_db():
    """Create all tables, indexes, and updated_at triggers."""
    conn = get_connection()
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    conn.close()


_SCHEMA_SQL = """
-- =============================================================
-- TABLES
-- =============================================================

CREATE TABLE IF NOT EXISTS candidates (
    candidate_id        TEXT PRIMARY KEY,
    full_name           TEXT NOT NULL,
    preferred_name      TEXT,
    email               TEXT,
    phone_e164          TEXT,
    preferred_language  TEXT DEFAULT 'en-US',
    client_company      TEXT,
    role_applied_for    TEXT,
    package_type        TEXT DEFAULT 'STANDARD',
    case_status         TEXT DEFAULT 'INITIATED',
    case_initiated_on   DATE,
    sla_deadline        DATE,
    assigned_analyst    TEXT,
    timezone            TEXT DEFAULT 'UTC',
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS verification_components (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id          TEXT NOT NULL,
    component_type        TEXT NOT NULL,
    component_status      TEXT DEFAULT 'PENDING',
    institution_or_employer TEXT,
    declared_start_date   DATE,
    declared_end_date     DATE,
    declared_designation  TEXT,
    declared_value        TEXT,          -- JSON blob for flexible fields
    created_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (candidate_id)
        REFERENCES candidates(candidate_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS insufficiencies (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id        TEXT NOT NULL,
    component_id        INTEGER NOT NULL,
    reason_code         TEXT NOT NULL,
    reason_detail       TEXT,
    raised_on           DATETIME DEFAULT CURRENT_TIMESTAMP,
    raised_by_analyst   TEXT,
    resolution_required TEXT,
    is_resolved         BOOLEAN DEFAULT 0,
    resolved_on         DATETIME,
    resolution_method   TEXT,
    attempt_count       INTEGER DEFAULT 0,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (candidate_id)
        REFERENCES candidates(candidate_id) ON DELETE CASCADE,
    FOREIGN KEY (component_id)
        REFERENCES verification_components(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS conversation_sessions (
    session_id        TEXT PRIMARY KEY,
    candidate_id      TEXT,
    started_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at          DATETIME,
    outcome           TEXT,
    full_transcript   TEXT DEFAULT '',
    FOREIGN KEY (candidate_id)
        REFERENCES candidates(candidate_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_trails (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id               TEXT,
    candidate_id             TEXT,
    intent_detected          TEXT,
    action_taken             TEXT,
    insufficiency_id         INTEGER,
    old_status               TEXT,
    new_status               TEXT,
    summary                  TEXT,
    intent_distribution_json TEXT,
    total_turns              INTEGER,
    call_duration_sec        INTEGER,
    resolution_outcome       TEXT,
    timestamp                DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (candidate_id)
        REFERENCES candidates(candidate_id) ON DELETE CASCADE,
    FOREIGN KEY (insufficiency_id)
        REFERENCES insufficiencies(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS faqs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    category            TEXT,
    question            TEXT,
    normalized_question TEXT,
    keywords_json       TEXT,
    answer              TEXT,
    follow_up_prompt    TEXT,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================
-- INDEXES
-- =============================================================
CREATE INDEX IF NOT EXISTS idx_cand_status
    ON candidates(case_status);
CREATE INDEX IF NOT EXISTS idx_cand_name
    ON candidates(full_name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_vc_cand
    ON verification_components(candidate_id);
CREATE INDEX IF NOT EXISTS idx_insuf_cand
    ON insufficiencies(candidate_id);
CREATE INDEX IF NOT EXISTS idx_insuf_comp
    ON insufficiencies(component_id);
CREATE INDEX IF NOT EXISTS idx_insuf_resolved
    ON insufficiencies(is_resolved);

CREATE INDEX IF NOT EXISTS idx_audit_session
    ON audit_trails(session_id);
CREATE INDEX IF NOT EXISTS idx_audit_cand
    ON audit_trails(candidate_id);
CREATE INDEX IF NOT EXISTS idx_faq_cat
    ON faqs(category);
CREATE INDEX IF NOT EXISTS idx_faq_norm
    ON faqs(normalized_question);

-- =============================================================
-- TRIGGERS — keep updated_at fresh on row mutation
-- The WHEN guard prevents infinite recursion.
-- =============================================================
CREATE TRIGGER IF NOT EXISTS trg_cand_upd
AFTER UPDATE ON candidates
WHEN OLD.updated_at = NEW.updated_at
BEGIN
    UPDATE candidates
       SET updated_at = datetime('now')
     WHERE candidate_id = NEW.candidate_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_vc_upd
AFTER UPDATE ON verification_components
WHEN OLD.updated_at = NEW.updated_at
BEGIN
    UPDATE verification_components
       SET updated_at = datetime('now')
     WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_insuf_upd
AFTER UPDATE ON insufficiencies
WHEN OLD.updated_at = NEW.updated_at
BEGIN
    UPDATE insufficiencies
       SET updated_at = datetime('now')
     WHERE id = NEW.id;
END;
"""


# ------------------------------------------------------------------
# Query Helpers — Reads
# ------------------------------------------------------------------

def find_candidate_by_name(name: str):
    """
    Case-insensitive candidate lookup.

    Tries exact match on full_name / preferred_name first,
    then falls back to substring (LIKE %name%).
    """
    if not name:
        return None

    conn = get_connection()
    try:
        clean = name.strip().lower()

        # 1. Exact match
        row = conn.execute(
            """SELECT * FROM candidates
               WHERE LOWER(full_name) = ? OR LOWER(preferred_name) = ?""",
            (clean, clean),
        ).fetchone()
        if row:
            return dict(row)

        # 2. Substring / partial match
        row = conn.execute(
            """SELECT * FROM candidates
               WHERE LOWER(full_name) LIKE ? OR LOWER(preferred_name) LIKE ?""",
            (f"%{clean}%", f"%{clean}%"),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_candidate_by_id(candidate_id: str):
    """Direct lookup by candidate_id."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM candidates WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_unresolved_insufficiencies(candidate_id: str):
    """
    Return every *unresolved* insufficiency for a candidate,
    joined with the parent verification-component context.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                i.id               AS insufficiency_id,
                i.reason_code,
                i.reason_detail,
                i.resolution_required,
                i.is_resolved,
                i.attempt_count,
                i.raised_on,
                vc.id              AS component_id,
                vc.component_type,
                vc.institution_or_employer,
                vc.declared_designation,
                vc.declared_start_date,
                vc.declared_end_date,
                vc.declared_value
            FROM insufficiencies i
            JOIN verification_components vc
              ON i.component_id = vc.id
            WHERE i.candidate_id = ?
              AND i.is_resolved = 0
            ORDER BY i.id
            """,
            (candidate_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_insufficiencies(candidate_id: str):
    """Return resolved + unresolved insufficiencies."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                i.id               AS insufficiency_id,
                i.reason_code,
                i.reason_detail,
                i.resolution_required,
                i.is_resolved,
                i.attempt_count,
                i.raised_on,
                i.resolved_on,
                i.resolution_method,
                vc.id              AS component_id,
                vc.component_type,
                vc.institution_or_employer,
                vc.declared_designation,
                vc.declared_start_date,
                vc.declared_end_date
            FROM insufficiencies i
            JOIN verification_components vc
              ON i.component_id = vc.id
            WHERE i.candidate_id = ?
            ORDER BY i.is_resolved, i.id
            """,
            (candidate_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_component_for_insufficiency(insufficiency_id: int):
    """Given an insufficiency id, return its component_id + candidate_id."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT component_id, candidate_id FROM insufficiencies WHERE id = ?",
            (insufficiency_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ------------------------------------------------------------------
# Query Helpers — Writes (all return dicts or None)
# ------------------------------------------------------------------

def resolve_insufficiency_in_db(
    insufficiency_id: int,
    method: str = "VOICE_AGENT",
):
    """
    Mark an insufficiency as resolved.

    Also clears the parent component when all its insufficiencies
    are resolved, and clears the candidate when ALL insufficiencies
    across all components are resolved.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT is_resolved, candidate_id, component_id "
            "FROM insufficiencies WHERE id = ?",
            (insufficiency_id,),
        ).fetchone()
        if not row:
            return None

        was_resolved = bool(row["is_resolved"])
        candidate_id = row["candidate_id"]
        component_id = row["component_id"]

        conn.execute(
            """UPDATE insufficiencies
               SET is_resolved = 1,
                   resolved_on = datetime('now'),
                   resolution_method = ?
             WHERE id = ?""",
            (method, insufficiency_id),
        )

        # Clear component if all its insufficiencies are now resolved
        remaining = conn.execute(
            """SELECT COUNT(*) AS cnt FROM insufficiencies
               WHERE component_id = ? AND is_resolved = 0 AND id != ?""",
            (component_id, insufficiency_id),
        ).fetchone()["cnt"]
        if remaining == 0:
            conn.execute(
                "UPDATE verification_components SET component_status = 'CLEARED' WHERE id = ?",
                (component_id,),
            )

        # Clear candidate if ALL insufficiencies are resolved
        total_open = conn.execute(
            """SELECT COUNT(*) AS cnt FROM insufficiencies
               WHERE candidate_id = ? AND is_resolved = 0""",
            (candidate_id,),
        ).fetchone()["cnt"]
        if total_open == 0:
            conn.execute(
                "UPDATE candidates SET case_status = 'CLEARED' WHERE candidate_id = ?",
                (candidate_id,),
            )

        conn.commit()
        return {
            "was_already_resolved": was_resolved,
            "candidate_id": candidate_id,
            "component_id": component_id,
        }
    finally:
        conn.close()


def mark_resubmission_in_db(insufficiency_id: int, eta_hours: int):
    """
    Record that the candidate has promised to resubmit.

    Idempotent — repeated calls increment attempt_count and
    update the ETA rather than creating duplicate rows.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT candidate_id, attempt_count FROM insufficiencies WHERE id = ?",
            (insufficiency_id,),
        ).fetchone()
        if not row:
            return None

        candidate_id = row["candidate_id"]

        conn.execute(
            "UPDATE insufficiencies SET attempt_count = attempt_count + 1 WHERE id = ?",
            (insufficiency_id,),
        )
        conn.execute(
            """UPDATE candidates
               SET case_status = 'AWAITING_CANDIDATE'
             WHERE candidate_id = ?
               AND case_status = 'INSUFFICIENCY_RAISED'""",
            (candidate_id,),
        )
        conn.commit()
        return {"candidate_id": candidate_id, "eta_hours": eta_hours}
    finally:
        conn.close()


def update_contact_in_db(candidate_id: str, field: str, new_value: str):
    """
    Update an allowed contact field on the candidate record.

    Returns the old + new values, or None if the field is
    disallowed or the candidate does not exist.
    """
    allowed = {"email", "phone_e164", "preferred_name", "preferred_language"}
    if field not in allowed:
        return None

    conn = get_connection()
    try:
        old_row = conn.execute(
            f"SELECT {field} FROM candidates WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        if not old_row:
            return None

        old_value = old_row[field]
        conn.execute(
            f"UPDATE candidates SET {field} = ? WHERE candidate_id = ?",
            (new_value, candidate_id),
        )
        conn.commit()
        return {"field": field, "old_value": old_value, "new_value": new_value}
    finally:
        conn.close()


def add_hr_contact_in_db(
    component_id: int,
    contact_name: str,
    email: str,
    phone: str,
):
    """
    Append an alternate HR contact to a verification component's
    declared_value JSON blob.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT declared_value, candidate_id FROM verification_components WHERE id = ?",
            (component_id,),
        ).fetchone()
        if not row:
            return None

        existing = json.loads(row["declared_value"]) if row["declared_value"] else {}
        existing["alternate_hr_contact"] = {
            "name": contact_name,
            "email": email,
            "phone": phone,
            "added_via": "VOICE_AGENT",
            "added_on": datetime.utcnow().isoformat(),
        }
        conn.execute(
            "UPDATE verification_components SET declared_value = ? WHERE id = ?",
            (json.dumps(existing), component_id),
        )
        conn.commit()
        return {"component_id": component_id, "candidate_id": row["candidate_id"]}
    finally:
        conn.close()


def add_reference_in_db(
    component_id: int,
    ref_name: str,
    relationship: str,
    email: str,
    phone: str,
):
    """
    Append a substitute reference to a verification component's
    declared_value JSON blob.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT declared_value, candidate_id FROM verification_components WHERE id = ?",
            (component_id,),
        ).fetchone()
        if not row:
            return None

        existing = json.loads(row["declared_value"]) if row["declared_value"] else {}
        existing["substitute_reference"] = {
            "name": ref_name,
            "relationship": relationship,
            "email": email,
            "phone": phone,
            "added_via": "VOICE_AGENT",
            "added_on": datetime.utcnow().isoformat(),
        }
        conn.execute(
            "UPDATE verification_components SET declared_value = ? WHERE id = ?",
            (json.dumps(existing), component_id),
        )
        conn.commit()
        return {"component_id": component_id, "candidate_id": row["candidate_id"]}
    finally:
        conn.close()


def extend_sla_in_db(candidate_id: str, days: int, reason: str):
    """
    Extend the SLA deadline by 1–5 calendar days.

    Returns old and new deadlines, or None on validation failure.
    """
    if days < 1 or days > 5:
        return None

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT sla_deadline FROM candidates WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        if not row:
            return None

        old_deadline = row["sla_deadline"]
        new_deadline = (
            date.fromisoformat(old_deadline) + timedelta(days=days)
        ).isoformat()

        conn.execute(
            "UPDATE candidates SET sla_deadline = ? WHERE candidate_id = ?",
            (new_deadline, candidate_id),
        )
        conn.commit()
        return {
            "old_deadline": old_deadline,
            "new_deadline": new_deadline,
            "extension_days": days,
            "reason": reason,
        }
    finally:
        conn.close()


def log_audit_trail(
    candidate_id: str,
    action_taken: str,
    insufficiency_id: int = None,
    old_status: str = None,
    new_status: str = None,
    intent_detected: str = None,
    summary: str = None,
    resolution_outcome: str = None,
    session_id: str = None,
):
    """Insert one audit-trail row."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO audit_trails
               (session_id, candidate_id, intent_detected, action_taken,
                insufficiency_id, old_status, new_status, summary,
                resolution_outcome)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id, candidate_id, intent_detected, action_taken,
                insufficiency_id, old_status, new_status, summary,
                resolution_outcome,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def start_conversation_session(candidate_id: str, session_id: str):
    """Start a new conversation session/thread."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO conversation_sessions
               (session_id, candidate_id)
               VALUES (?, ?)""",
            (session_id, candidate_id)
        )
        conn.commit()
    finally:
        conn.close()


def end_conversation_session(session_id: str, outcome: str):
    """End a conversation session."""
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE conversation_sessions
               SET ended_at = datetime('now'), outcome = ?
               WHERE session_id = ?""",
            (outcome, session_id)
        )
        conn.commit()
    finally:
        conn.close()


def log_conversation_turn(
    session_id: str,
    candidate_id: str,
    turn_index: int,
    speaker: str,
    text: str,
    stt_latency_ms: int = None,
    llm_latency_ms: int = None,
    tts_latency_ms: int = None,
    ttft_ms: int = None,
    vad_chunk_count: int = None,
    intent_classified: str = None,
    routed_via: str = None,
):
    """Log a single turn in a conversation session. Auto-creates session if missing."""
    conn = get_connection()
    try:
        # Auto-create the session if the LLM forgot to call start_session
        conn.execute(
            """INSERT OR IGNORE INTO conversation_sessions (session_id, candidate_id)
               VALUES (?, ?)""",
            (session_id, candidate_id)
        )
        conn.execute(
            """UPDATE conversation_sessions
               SET full_transcript = full_transcript || ? || ': ' || ? || CHAR(10)
               WHERE session_id = ?""",
            (speaker, text, session_id)
        )
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------------
# Reset helper
# ------------------------------------------------------------------

def drop_all_tables():
    """Drop every table. Used by the 'Reset Demo Data' flow."""
    conn = get_connection()
    conn.executescript(
        """
        DROP TABLE IF EXISTS audit_trails;
        DROP TABLE IF EXISTS conversation_logs;
        DROP TABLE IF EXISTS conversation_sessions;
        DROP TABLE IF EXISTS insufficiencies;
        DROP TABLE IF EXISTS verification_components;
        DROP TABLE IF EXISTS faqs;
        DROP TABLE IF EXISTS candidates;
        """
    )
    conn.commit()
    conn.close()
