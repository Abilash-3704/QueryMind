"""
Validator node — Phase 2.
Pure code (no LLM). Owns SQL guardrail checking, execution, and sanity checks.
On failure it sets execution_error and increments retry_count so the conditional
edge in pipeline.py can route back to the SQL Generator.
"""
from __future__ import annotations

from typing import Any

import duckdb
import sqlglot
from app.db.sandbox import GuardrailError, assert_select_only
from app.db.session_db import execute_query
from app.models.schemas import LinkedSchema, PipelineState

_MAX_RETRIES = 3


def _sample_referenced_columns(
    sql: str,
    linked_schema: LinkedSchema | None,
    conn: duckdb.DuckDBPyConnection,
    limit: int = 5,
) -> str:
    """Best-effort: sample a few actual distinct values for columns referenced in a
    query that returned zero rows, so the retry prompt shows real data (casing, date
    format, category labels, ...) instead of a vague "may be filtering incorrectly"."""
    if linked_schema is None:
        return ""
    try:
        parsed = sqlglot.parse_one(sql, dialect="duckdb")
    except Exception:
        return ""
    referenced = {c.name for c in parsed.find_all(sqlglot.exp.Column)}
    if not referenced:
        return ""

    col_to_table: dict[str, str] = {}
    for table, cols in linked_schema.columns.items():
        for col in cols:
            if col in referenced:
                col_to_table[col] = table

    samples = []
    for col, table in list(col_to_table.items())[:5]:
        try:
            rows = conn.execute(
                f'SELECT DISTINCT "{col}" FROM "{table}" LIMIT {limit}'
            ).fetchall()
            samples.append(f"{table}.{col}: {[r[0] for r in rows]}")
        except Exception:
            continue
    return "; ".join(samples)


def run_validator(conn: duckdb.DuckDBPyConnection):
    """Return a LangGraph node function that validates and executes SQL."""

    def _node(state: PipelineState) -> dict[str, Any]:
        sql = state.generated_sql or ""
        attempt = state.retry_count + 1

        if not sql:
            return {
                "execution_result": None,
                "execution_error": f"Attempt {attempt}: No SQL was generated.",
                "retry_count": state.retry_count + 1,
            }

        try:
            assert_select_only(sql)
        except GuardrailError as exc:
            return {
                "execution_result": None,
                "execution_error": (
                    f"Attempt {attempt}: GuardrailError: {exc}. SQL was: {sql[:200]}"
                ),
                "retry_count": state.retry_count + 1,
            }

        try:
            rows = execute_query(conn, sql, timeout_seconds=10)
        except Exception as exc:
            return {
                "execution_result": None,
                "execution_error": (
                    f"Attempt {attempt}: ExecutionError: {exc}. SQL was: {sql[:200]}"
                ),
                "retry_count": state.retry_count + 1,
            }

        if rows == [] and state.retry_count < _MAX_RETRIES - 1:
            hint = _sample_referenced_columns(sql, state.linked_schema, conn)
            hint_text = f" Actual values found in the referenced columns: {hint}." if hint else ""
            return {
                "execution_result": [],
                "execution_error": (
                    f"Attempt {attempt}: Query returned zero rows — "
                    "the SQL may be filtering incorrectly or joining on the wrong key."
                    f"{hint_text} SQL was: {sql[:200]}"
                ),
                "retry_count": state.retry_count + 1,
            }

        return {
            "execution_result": rows,
            "execution_error": None,
        }

    return _node
