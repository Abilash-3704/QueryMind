"""
SQL guardrails — code-level enforcement, NOT prompt-level.

assert_select_only() must be called before every SQL execution. It uses sqlglot to parse
and verify the statement is a plain SELECT (or CTE-wrapped SELECT). If sqlglot cannot parse
the SQL, a keyword-based fallback check rejects any obvious DDL/DML.

This is a deliberate security boundary: even if the LLM ignores its system prompt and
generates a DROP TABLE or DELETE, the query never reaches DuckDB.
"""
from __future__ import annotations

import re

import sqlglot
import sqlglot.errors

_BLOCKED_KEYWORDS = frozenset({
    "DROP", "DELETE", "INSERT", "UPDATE", "CREATE", "ALTER",
    "TRUNCATE", "EXECUTE", "COPY", "ATTACH", "DETACH", "VACUUM",
})

# Regex pattern for whole-word match (precompiled for speed)
_BLOCKED_RE = re.compile(
    r"\b(" + "|".join(_BLOCKED_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


class GuardrailError(Exception):
    """Raised when SQL fails the SELECT-only guardrail check."""


def assert_select_only(sql: str) -> None:
    """
    Raise GuardrailError if `sql` is not a pure SELECT (or CTE SELECT) statement.

    Two layers:
      1. sqlglot AST check (primary) — parses and confirms root node is Select.
         CTEs parse as Select with a .with_ property, so they pass correctly.
      2. Keyword fallback (belt-and-suspenders) — fires only when sqlglot cannot parse
         the SQL at all (malformed input). Rejects any SQL that starts with a blocked
         keyword or contains one as a whole word.
    """
    stripped = sql.strip()
    if not stripped:
        raise GuardrailError("Empty SQL statement.")

    # ── Layer 1: sqlglot AST ──────────────────────────────────────────────
    parse_error: str | None = None
    try:
        statement = sqlglot.parse_one(stripped, dialect="duckdb")
        if not isinstance(statement, sqlglot.exp.Select):
            raise GuardrailError(
                f"Only SELECT statements are permitted; "
                f"got {type(statement).__name__}: {stripped[:120]}"
            )
        return  # passed — exit early
    except GuardrailError:
        raise
    except Exception as exc:
        # sqlglot failed to parse — note the error, fall through to fallback
        parse_error = str(exc)

    # ── Layer 2: keyword fallback ─────────────────────────────────────────
    upper = stripped.upper().lstrip()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise GuardrailError(
            f"SQL does not begin with SELECT or WITH "
            f"{'(sqlglot parse failed: ' + parse_error + ')' if parse_error else ''}. "
            f"Got: {stripped[:120]}"
        )
    match = _BLOCKED_RE.search(stripped)
    if match:
        raise GuardrailError(
            f"Forbidden keyword '{match.group().upper()}' found in SQL "
            f"(sqlglot parse failed: {parse_error}). SQL: {stripped[:120]}"
        )
