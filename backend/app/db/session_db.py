"""
DuckDB session management.

Phase 1: loads the hardcoded Chinook SQLite file into an in-memory DuckDB connection
         via DuckDB's built-in sqlite scanner.
Phase 3: extended to accept user-uploaded CSVs.
"""
from __future__ import annotations

import re
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
from app.models.schemas import ColumnInfo, SchemaInfo, TableInfo

# __file__ = backend/app/db/session_db.py  →  parents[2] = backend/
CHINOOK_PATH = Path(__file__).resolve().parents[2] / "data" / "chinook.sqlite"


def _fetchall_as_dicts(cursor: duckdb.DuckDBPyConnection) -> list[dict]:
    """Convert a fetchall() result to a list of dicts using cursor description."""
    rows = cursor.fetchall()
    if not rows:
        return []
    col_names = [desc[0] for desc in cursor.description]
    return [dict(zip(col_names, row)) for row in rows]


def open_chinook() -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB connection with Chinook attached."""
    if not CHINOOK_PATH.exists():
        raise FileNotFoundError(
            f"Chinook database not found at {CHINOOK_PATH}. "
            "Run: python backend/scripts/bootstrap_chinook.py"
        )
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL sqlite; LOAD sqlite;")
    conn.execute(f"ATTACH '{CHINOOK_PATH}' AS chinook (TYPE sqlite, READ_ONLY);")
    conn.execute("USE chinook;")
    return conn


def get_schema_info(conn: duckdb.DuckDBPyConnection) -> SchemaInfo:
    """Introspect the active DuckDB connection and return table/column metadata."""
    tables_result = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = current_schema() ORDER BY table_name;"
    ).fetchall()
    table_names = [row[0] for row in tables_result]

    tables: list[TableInfo] = []
    for tname in table_names:
        cols_result = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ? "
            "ORDER BY ordinal_position;",
            [tname],
        ).fetchall()
        columns = [ColumnInfo(name=row[0], dtype=row[1]) for row in cols_result]

        try:
            cur = conn.execute(f'SELECT * FROM "{tname}" LIMIT 3;')
            sample_rows = _fetchall_as_dicts(cur)
        except Exception:
            sample_rows = []

        tables.append(TableInfo(name=tname, columns=columns, sample_rows=sample_rows))

    return SchemaInfo(tables=tables)


def execute_query(
    conn: duckdb.DuckDBPyConnection, sql: str, timeout_seconds: int = 10
) -> list[dict]:
    """Execute a SQL query with a timeout; raises on error or timeout."""
    import concurrent.futures

    def _run():
        cur = conn.execute(sql)
        return _fetchall_as_dicts(cur)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            conn.interrupt()
            raise TimeoutError(f"Query exceeded {timeout_seconds}s timeout: {sql[:120]}")


# ---------------------------------------------------------------------------
# Session store — Phase 3
# ---------------------------------------------------------------------------

SESSION_TTL_DEFAULT = 30 * 60  # 30 minutes in seconds


@dataclass
class Session:
    session_id: str
    conn: duckdb.DuckDBPyConnection
    schema_info: SchemaInfo
    created_at: float = field(default_factory=time.monotonic)
    last_accessed: float = field(default_factory=time.monotonic)


_SESSIONS: dict[str, Session] = {}


def _filename_to_table_name(filename: str) -> str:
    """Convert an uploaded filename to a safe DuckDB table name.

    'My Sales Data 2024.csv' → 'my_sales_data_2024'
    """
    stem = Path(filename).stem
    name = re.sub(r"[^A-Za-z0-9_]", "_", stem).strip("_").lower()
    # Remove consecutive underscores
    name = re.sub(r"_+", "_", name)
    if not name:
        return "uploaded_table"
    # Table names cannot start with a digit in DuckDB
    if name[0].isdigit():
        name = "t_" + name
    return name


def _load_csv_into_conn(conn: duckdb.DuckDBPyConnection, csv_bytes: bytes, filename: str) -> None:
    """Write csv_bytes to a temp file and CREATE TABLE ... AS SELECT * FROM read_csv_auto(...)."""
    table_name = _filename_to_table_name(filename)
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(csv_bytes)
        tmp_path = f.name
    try:
        conn.execute(
            f'CREATE OR REPLACE TABLE "{table_name}" AS '
            f"SELECT * FROM read_csv_auto('{tmp_path}')"
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def load_csv_to_session(
    csv_bytes: bytes,
    filename: str,
    ttl_seconds: int = SESSION_TTL_DEFAULT,
) -> Session:
    """Create a new in-memory DuckDB session from a CSV file."""
    conn = duckdb.connect(":memory:")
    _load_csv_into_conn(conn, csv_bytes, filename)
    schema_info = get_schema_info(conn)
    session_id = str(uuid.uuid4())
    session = Session(session_id=session_id, conn=conn, schema_info=schema_info)
    _SESSIONS[session_id] = session
    _cleanup_expired(ttl_seconds)
    return session


def append_csv_to_session(
    session: Session,
    csv_bytes: bytes,
    filename: str,
) -> None:
    """Load an additional CSV into an existing session as a new table."""
    _load_csv_into_conn(session.conn, csv_bytes, filename)
    session.schema_info = get_schema_info(session.conn)


def get_session(session_id: str, ttl_seconds: int = SESSION_TTL_DEFAULT) -> Session:
    """Look up a session by ID. Raises KeyError if not found, TimeoutError if expired."""
    session = _SESSIONS.get(session_id)
    if session is None:
        raise KeyError(session_id)
    if time.monotonic() - session.last_accessed > ttl_seconds:
        del _SESSIONS[session_id]
        raise TimeoutError(session_id)
    session.last_accessed = time.monotonic()
    return session


def _cleanup_expired(ttl_seconds: int) -> None:
    now = time.monotonic()
    expired = [k for k, s in _SESSIONS.items() if now - s.last_accessed > ttl_seconds]
    for k in expired:
        del _SESSIONS[k]
