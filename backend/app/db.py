"""
Thin, Postgres-ready data-access layer over the standard library.

Why not an ORM: the pipeline issues a small number of well-understood queries.
A 60-line wrapper keeps the dependency surface at zero while remaining portable:
write SQL once with `?` placeholders and portable types; the wrapper adapts to
SQLite (today) or PostgreSQL (via psycopg, when DATABASE_URL points at one).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable, Sequence

from .config import DATABASE_URL


def _is_pg(url: str) -> bool:
    return url.startswith("postgres://") or url.startswith("postgresql://")


IS_POSTGRES = _is_pg(DATABASE_URL)

# Portable column types: (sqlite, postgres)
INT = "INTEGER"
TEXT = "TEXT"
REAL = "DOUBLE PRECISION" if IS_POSTGRES else "REAL"
BOOL = "BOOLEAN" if IS_POSTGRES else "INTEGER"


def _sqlite_path(url: str) -> str:
    # sqlite:///C:/path/to.db  -> C:/path/to.db
    return url[len("sqlite:///"):]


def _adapt(sql: str) -> str:
    """SQLite uses ? placeholders; psycopg uses %s. Author with ? everywhere."""
    return sql.replace("?", "%s") if IS_POSTGRES else sql


@contextmanager
def connect():
    """Yield a DB-API connection with row access by name; commit on success."""
    if IS_POSTGRES:
        import psycopg  # lazy: only needed when actually targeting Postgres
        from psycopg.rows import dict_row

        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(_sqlite_path(DATABASE_URL))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def execute(conn, sql: str, params: Sequence[Any] = ()) -> None:
    conn.execute(_adapt(sql), params)


def executemany(conn, sql: str, rows: Iterable[Sequence[Any]]) -> None:
    cur = conn.cursor()
    cur.executemany(_adapt(sql), list(rows))


def query(conn, sql: str, params: Sequence[Any] = ()) -> list[dict]:
    cur = conn.cursor()
    cur.execute(_adapt(sql), params)
    rows = cur.fetchall()
    if IS_POSTGRES:
        return list(rows)  # already dict_row
    return [dict(r) for r in rows]


def query_one(conn, sql: str, params: Sequence[Any] = ()) -> dict | None:
    rows = query(conn, sql, params)
    return rows[0] if rows else None
