"""
Guardrail tests — verify that sandbox.assert_select_only() blocks all DDL/DML
and that the validator node propagates GuardrailErrors into the retry loop.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.sandbox import GuardrailError, assert_select_only

# ---------------------------------------------------------------------------
# assert_select_only — blocked statements
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sql", [
    "DROP TABLE Artist",
    "drop table artist",                         # case-insensitive
    "DELETE FROM Artist WHERE ArtistId = 1",
    "INSERT INTO Artist (Name) VALUES ('Evil')",
    "UPDATE Artist SET Name = 'Evil' WHERE ArtistId = 1",
    "CREATE TABLE evil (id INT)",
    "ALTER TABLE Artist ADD COLUMN evil TEXT",
    "TRUNCATE TABLE Artist",
    "EXECUTE sp_evil",
    "ATTACH 'evil.db' AS evil",
    "DETACH evil",
])
def test_blocked_statements_raise(sql: str) -> None:
    with pytest.raises(GuardrailError):
        assert_select_only(sql)


def test_multi_statement_blocked() -> None:
    """sqlglot rejects multiple statements — second statement is a DROP."""
    with pytest.raises((GuardrailError, Exception)):
        assert_select_only("SELECT 1; DROP TABLE Artist")


def test_drop_disguised_in_comment_blocked() -> None:
    """The keyword check must find DROP even when sqlglot parsing fails."""
    # Force the fallback path by submitting something sqlglot won't parse cleanly
    # but that still contains a DROP keyword
    malformed_with_drop = "DROP !!! INVALID SYNTAX TABLE Artist"
    with pytest.raises(GuardrailError):
        assert_select_only(malformed_with_drop)


# ---------------------------------------------------------------------------
# assert_select_only — allowed statements
# ---------------------------------------------------------------------------

def test_simple_select_passes() -> None:
    assert_select_only("SELECT * FROM Artist")


def test_lowercase_select_passes() -> None:
    assert_select_only("select artistid, name from artist limit 10")


def test_cte_select_passes() -> None:
    assert_select_only(
        "WITH top_artists AS (SELECT ArtistId, COUNT(*) AS cnt "
        "FROM Album GROUP BY ArtistId) "
        "SELECT * FROM top_artists ORDER BY cnt DESC LIMIT 5"
    )


def test_complex_join_select_passes() -> None:
    assert_select_only(
        "SELECT ar.Name, SUM(il.UnitPrice * il.Quantity) AS revenue "
        "FROM Artist ar "
        "JOIN Album al ON ar.ArtistId = al.ArtistId "
        "JOIN Track t ON al.AlbumId = t.AlbumId "
        "JOIN InvoiceLine il ON t.TrackId = il.TrackId "
        "GROUP BY ar.Name ORDER BY revenue DESC LIMIT 10"
    )


def test_empty_sql_blocked() -> None:
    with pytest.raises(GuardrailError):
        assert_select_only("")


def test_whitespace_only_blocked() -> None:
    with pytest.raises(GuardrailError):
        assert_select_only("   \n\t  ")


# ---------------------------------------------------------------------------
# Validator node integration — retry loop fires on GuardrailError
# ---------------------------------------------------------------------------

def test_validator_blocks_drop_and_increments_retry() -> None:
    """The validator node should catch DROP TABLE and set execution_error + retry_count."""
    from app.agents.validator import run_validator
    from app.models.schemas import ColumnInfo, PipelineState, SchemaInfo, TableInfo

    conn = MagicMock()  # never reached — guardrail fires first

    schema = SchemaInfo(tables=[
        TableInfo(name="Artist", columns=[ColumnInfo(name="ArtistId", dtype="INTEGER")]),
    ])
    state = PipelineState(
        user_question="drop everything",
        schema_info=schema,
        generated_sql="DROP TABLE Artist",
        retry_count=0,
    )

    result = run_validator(conn)(state)

    assert result["execution_error"] is not None
    assert "GuardrailError" in result["execution_error"]
    assert result["retry_count"] == 1
    assert result["execution_result"] is None
    conn.execute.assert_not_called()  # DuckDB was never touched


def test_validator_blocks_delete_and_increments_retry() -> None:
    conn = MagicMock()
    from app.agents.validator import run_validator
    from app.models.schemas import ColumnInfo, PipelineState, SchemaInfo, TableInfo

    schema = SchemaInfo(tables=[
        TableInfo(name="Artist", columns=[ColumnInfo(name="ArtistId", dtype="INTEGER")]),
    ])
    state = PipelineState(
        user_question="delete records",
        schema_info=schema,
        generated_sql="DELETE FROM Artist",
        retry_count=0,
    )

    result = run_validator(conn)(state)

    assert result["execution_error"] is not None
    assert result["retry_count"] == 1
    conn.execute.assert_not_called()


def test_validator_passes_valid_select() -> None:
    """A real DuckDB connection executes a valid SELECT and returns rows."""
    import duckdb
    from app.agents.validator import run_validator
    from app.models.schemas import ColumnInfo, PipelineState, SchemaInfo, TableInfo

    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE t (id INTEGER, val VARCHAR)")
    conn.execute("INSERT INTO t VALUES (1, 'a'), (2, 'b')")

    schema = SchemaInfo(tables=[
        TableInfo(name="t", columns=[
            ColumnInfo(name="id", dtype="INTEGER"),
            ColumnInfo(name="val", dtype="VARCHAR"),
        ]),
    ])
    state = PipelineState(
        user_question="show all",
        schema_info=schema,
        generated_sql="SELECT id, val FROM t ORDER BY id",
        retry_count=0,
    )

    result = run_validator(conn)(state)

    assert result["execution_error"] is None
    assert result["execution_result"] == [{"id": 1, "val": "a"}, {"id": 2, "val": "b"}]


def test_validator_zero_rows_includes_sample_value_hint() -> None:
    """When a filter returns zero rows, the retry hint should show real column values
    so the SQL generator can fix casing/formatting instead of guessing again blind."""
    import duckdb
    from app.agents.validator import run_validator
    from app.models.schemas import (
        ColumnInfo,
        LinkedSchema,
        LinkedTableColumns,
        PipelineState,
        SchemaInfo,
        TableInfo,
    )

    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE Artist (ArtistId INTEGER, Name VARCHAR)")
    conn.execute("INSERT INTO Artist VALUES (1, 'Iron Maiden'), (2, 'AC/DC')")

    schema = SchemaInfo(tables=[
        TableInfo(name="Artist", columns=[
            ColumnInfo(name="ArtistId", dtype="INTEGER"),
            ColumnInfo(name="Name", dtype="VARCHAR"),
        ]),
    ])
    linked = LinkedSchema(table_columns=[LinkedTableColumns(table="Artist", columns=["Name"])])
    state = PipelineState(
        user_question="find iron maiden",
        schema_info=schema,
        linked_schema=linked,
        generated_sql="SELECT Name FROM Artist WHERE Name = 'iron maiden'",
        retry_count=0,
    )

    result = run_validator(conn)(state)

    assert result["execution_result"] == []
    assert result["retry_count"] == 1
    assert "Actual values found" in result["execution_error"]
    assert "Iron Maiden" in result["execution_error"]


def test_retry_loop_routes_back_to_sql_generator() -> None:
    """
    Full pipeline integration: mock LLM returns DROP TABLE on attempt 1,
    valid SQL on attempt 2. Assert retry_count == 1 and final_answer is set.
    """
    from unittest.mock import MagicMock

    import duckdb
    from app.config import Settings
    from app.graph.pipeline import build_graph
    from app.llm_client import LLMClient, LLMResponse
    from app.models.schemas import (
        ColumnInfo,
        LinkedSchema,
        LinkedTableColumns,
        PipelineState,
        QueryPlan,
        SchemaInfo,
        TableInfo,
    )

    # Real in-memory DuckDB with one table
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE Artist (ArtistId INTEGER, Name VARCHAR)")
    conn.execute("INSERT INTO Artist VALUES (1, 'Iron Maiden'), (2, 'AC/DC')")

    call_count = {"n": 0}

    def fake_generate(*, provider, model, system, user, temperature=0.0, response_schema=None, agent_name="llm_call"):
        call_count["n"] += 1
        if response_schema is LinkedSchema:
            parsed = LinkedSchema(table_columns=[
                LinkedTableColumns(table="Artist", columns=["ArtistId", "Name"]),
            ])
            return LLMResponse(text=parsed.model_dump_json(), parsed=parsed,
                               model=model, provider=provider,
                               input_tokens=50, output_tokens=20, latency_ms=100.0)
        if response_schema is QueryPlan:
            parsed = QueryPlan(steps=["Select all artists"])
            return LLMResponse(text=parsed.model_dump_json(), parsed=parsed,
                               model=model, provider=provider,
                               input_tokens=50, output_tokens=10, latency_ms=80.0)
        # SQL generator — return bad SQL first, good SQL on retry
        if "sql" in system.lower() or "duckdb" in system.lower():
            if call_count["n"] <= 3:  # first sql_generator call
                bad_sql = "DROP TABLE Artist"
                return LLMResponse(text=bad_sql, parsed=None,
                                   model=model, provider=provider,
                                   input_tokens=100, output_tokens=10, latency_ms=150.0)
            good_sql = "SELECT Name FROM Artist ORDER BY ArtistId"
            return LLMResponse(text=good_sql, parsed=None,
                               model=model, provider=provider,
                               input_tokens=100, output_tokens=20, latency_ms=150.0)
        # Explainer
        return LLMResponse(text="There are 2 artists.", parsed=None,
                           model=model, provider=provider,
                           input_tokens=80, output_tokens=15, latency_ms=120.0)

    llm = MagicMock(spec=LLMClient)
    llm.generate.side_effect = fake_generate

    settings = MagicMock(spec=Settings)
    settings.schema_linker_model = "openai/gpt-oss-20b"
    settings.query_planner_model = "gemini-2.5-flash-lite"
    settings.sql_generator_model = "gemini-2.5-flash-lite"
    settings.explainer_model = "gemini-2.5-flash-lite"

    schema = SchemaInfo(tables=[
        TableInfo(name="Artist", columns=[
            ColumnInfo(name="ArtistId", dtype="INTEGER"),
            ColumnInfo(name="Name", dtype="VARCHAR"),
        ], sample_rows=[]),
    ])
    graph = build_graph(conn, llm, settings)
    result = graph.invoke(PipelineState(user_question="show artists", schema_info=schema))

    assert result["retry_count"] >= 1, "Expected at least one retry"
    assert result["final_answer"] is not None
    assert len(result["final_answer"]) > 0
