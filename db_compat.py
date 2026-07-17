"""
db_compat.py — Database compatibility layer.

Supports both SQLite (local dev) and PostgreSQL (Supabase production).
Set the DATABASE_URL environment variable to switch to PostgreSQL.

Usage in database.py:
    from db_compat import get_connection, IS_POSTGRES, PK, BLOB, INT_PK_SINGLETON
"""

import os
import re
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get('DATABASE_URL')
IS_POSTGRES = bool(DATABASE_URL)


# ─── DDL type aliases ─────────────────────────────────────────────────────────
if IS_POSTGRES:
    PK = 'SERIAL PRIMARY KEY'          # auto-increment PK for PostgreSQL
    BLOB = 'BYTEA'                     # binary data
    INT_PK_SINGLETON = 'INTEGER PRIMARY KEY'  # singleton table (settings)
else:
    PK = 'INTEGER PRIMARY KEY AUTOINCREMENT'
    BLOB = 'BLOB'
    INT_PK_SINGLETON = 'INTEGER PRIMARY KEY CHECK (id = 1)'


# ─── SQL normalisation ────────────────────────────────────────────────────────
_SQLITE_TO_PG = [
    ("DATE('now', 'localtime')",               "CURRENT_DATE::text"),
    ("DATETIME('now', 'localtime')",           "NOW()"),
    ("DATE(timestamp, 'localtime')",           "((timestamp AT TIME ZONE 'UTC')::date)::text"),
    ("DATE(check_in_time, 'localtime')",       "((check_in_time AT TIME ZONE 'UTC')::date)::text"),
    ("DATE(closed_at, 'localtime')",           "((closed_at AT TIME ZONE 'UTC')::date)::text"),
    ("datetime(a.check_in_time, 'localtime')", "a.check_in_time"),
    ("datetime(a.check_out_time, 'localtime')","a.check_out_time"),
    ("datetime(check_in_time, 'localtime')",   "check_in_time"),
    ("datetime(check_out_time, 'localtime')",  "check_out_time"),
    ("substr(",                                "substring("),
]


def _normalize_sql(sql: str) -> str:
    """Translate SQLite-specific SQL syntax to PostgreSQL equivalents."""
    if not IS_POSTGRES:
        return sql
    sql = sql.replace('?', '%s')
    for sqlite_expr, pg_expr in _SQLITE_TO_PG:
        sql = sql.replace(sqlite_expr, pg_expr)
    return sql


# ─── Cursor wrapper ───────────────────────────────────────────────────────────
class CompatCursor:
    """
    Cursor wrapper that normalises SQL execution across SQLite and PostgreSQL:
    - Translates ? placeholders to %s for PostgreSQL
    - Replaces SQLite date functions with PostgreSQL equivalents
    - Captures lastrowid via RETURNING id for PostgreSQL INSERTs
    """

    def __init__(self, raw_cursor):
        self._cur = raw_cursor
        self.lastrowid = None

    def execute(self, sql: str, params=None):
        sql = _normalize_sql(sql)

        # Convert empty collections or tuples to None for psycopg2/sqlite3 compatibility
        exec_params = params if params else None

        if IS_POSTGRES and re.match(r'\s*INSERT\s+', sql, re.IGNORECASE):
            # Append RETURNING id if not already present
            if 'RETURNING' not in sql.upper():
                sql = sql.rstrip().rstrip(';') + ' RETURNING id'
            self._cur.execute(sql, exec_params)
            try:
                row = self._cur.fetchone()
                self.lastrowid = row[0] if row else None
            except Exception:
                self.lastrowid = None
        else:
            self._cur.execute(sql, exec_params)
            if not IS_POSTGRES:
                self.lastrowid = getattr(self._cur, 'lastrowid', None)

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def rowcount(self):
        return self._cur.rowcount


# ─── Connection wrapper ───────────────────────────────────────────────────────
class CompatConnection:
    """Thin wrapper around sqlite3 / psycopg2 connection."""

    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self) -> CompatCursor:
        return CompatCursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ─── Factory ─────────────────────────────────────────────────────────────────
def get_connection() -> CompatConnection:
    """
    Return a CompatConnection to either SQLite or PostgreSQL depending on
    whether the DATABASE_URL environment variable is set.
    """
    if IS_POSTGRES:
        import psycopg2
        raw = psycopg2.connect(DATABASE_URL)
        return CompatConnection(raw)
    else:
        import sqlite3
        from pathlib import Path
        db_path = str(Path(__file__).parent / 'attendance.db')
        raw = sqlite3.connect(db_path)
        return CompatConnection(raw)


# ─── Schema helpers ───────────────────────────────────────────────────────────
def column_exists(cursor: CompatCursor, table_name: str, column_name: str) -> bool:
    """Check whether a column exists in a table (DB-agnostic)."""
    if IS_POSTGRES:
        cursor._cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = %s AND column_name = %s",
            (table_name, column_name)
        )
        return cursor._cur.fetchone() is not None
    else:
        cursor._cur.execute(f"PRAGMA table_info({table_name})")
        return any(row[1] == column_name for row in cursor._cur.fetchall())


def ensure_column(cursor: CompatCursor, table_name: str,
                  column_name: str, column_definition: str):
    """Add a column if it does not already exist (DB-agnostic)."""
    if IS_POSTGRES:
        # PostgreSQL 9.6+ supports ADD COLUMN IF NOT EXISTS
        cursor._cur.execute(
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN IF NOT EXISTS {column_name} {column_definition}"
        )
    else:
        if not column_exists(cursor, table_name, column_name):
            cursor._cur.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
            )
# ─── Exception compatibility aliases ──────────────────────────────────────────
if IS_POSTGRES:
    import psycopg2
    DBException = psycopg2.Error
    IntegrityError = psycopg2.IntegrityError
else:
    import sqlite3
    DBException = sqlite3.Error
    IntegrityError = sqlite3.IntegrityError
