"""
Smoke test for the Phase 1 pipeline.
Uses a mocked LLMClient — no network, no API keys needed.
Asserts that the graph compiles, runs all 4 agent nodes in order,
and produces a non-empty final_answer.
"""
from __future__ import annotations

# Add backend/ to path for direct test invocation
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_schema_info() -> SchemaInfo:
    return SchemaInfo(
        tables=[
            TableInfo(
                name="Artist",
                columns=[ColumnInfo(name="ArtistId", dtype="INTEGER"),
                         ColumnInfo(name="Name", dtype="VARCHAR")],
                sample_rows=[{"ArtistId": 1, "Name": "AC/DC"}],
            ),
            TableInfo(
                name="Album",
                columns=[ColumnInfo(name="AlbumId", dtype="INTEGER"),
                         ColumnInfo(name="Title", dtype="VARCHAR"),
                         ColumnInfo(name="ArtistId", dtype="INTEGER")],
                sample_rows=[{"AlbumId": 1, "Title": "For Those About To Rock", "ArtistId": 1}],
            ),
        ]
    )


@pytest.fixture
def mock_duckdb_conn(mock_schema_info):
    """Minimal DuckDB-like connection that returns canned query results."""
    conn = MagicMock()

    def fake_execute(sql, *args, **kwargs):
        result = MagicMock()
        result.fetchall.return_value = [("Iron Maiden", 21)]
        result.description = [("Name", None, None, None, None, None, None),
                               ("album_count", None, None, None, None, None, None)]
        return result

    conn.execute.side_effect = fake_execute
    return conn


@pytest.fixture
def mock_llm():
    """LLMClient that returns canned structured responses without hitting any API."""
    llm = MagicMock(spec=LLMClient)

    def fake_generate(*, provider, model, system, user, temperature=0.0, response_schema=None, agent_name="llm_call"):
        if response_schema is LinkedSchema:
            parsed = LinkedSchema(
                table_columns=[
                    LinkedTableColumns(table="Artist", columns=["Name"]),
                    LinkedTableColumns(table="Album", columns=["ArtistId"]),
                ],
            )
            return LLMResponse(
                text=parsed.model_dump_json(),
                parsed=parsed,
                model=model, provider=provider,
                input_tokens=100, output_tokens=50, latency_ms=120.0,
            )
        if response_schema is QueryPlan:
            parsed = QueryPlan(steps=["Count albums per artist", "Order by count desc", "Take top 5"])
            return LLMResponse(
                text=parsed.model_dump_json(),
                parsed=parsed,
                model=model, provider=provider,
                input_tokens=150, output_tokens=60, latency_ms=200.0,
            )
        # SQL generator / Explainer — plain text response
        if "sql" in system.lower() or "duckdb" in system.lower():
            sql = "SELECT ar.Name, COUNT(*) AS album_count FROM Artist ar JOIN Album al ON ar.ArtistId = al.ArtistId GROUP BY ar.Name ORDER BY album_count DESC LIMIT 5"
            return LLMResponse(
                text=sql, parsed=None,
                model=model, provider=provider,
                input_tokens=200, output_tokens=40, latency_ms=180.0,
            )
        # Explainer
        answer = "Iron Maiden has the most albums with 21."
        return LLMResponse(
            text=answer, parsed=None,
            model=model, provider=provider,
            input_tokens=120, output_tokens=30, latency_ms=150.0,
        )

    llm.generate.side_effect = fake_generate
    return llm


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_graph_compiles(mock_duckdb_conn, mock_llm):
    from app.config import Settings
    from app.graph.pipeline import build_graph

    settings = MagicMock(spec=Settings)
    settings.schema_linker_model = "openai/gpt-oss-20b"
    settings.query_planner_model = "gemini-2.5-flash-lite"
    settings.sql_generator_model = "gemini-2.5-flash-lite"
    settings.explainer_model = "gemini-2.5-flash-lite"

    graph = build_graph(mock_duckdb_conn, mock_llm, settings)
    assert graph is not None


def test_pipeline_runs_end_to_end(mock_schema_info, mock_duckdb_conn, mock_llm):
    from app.config import Settings
    from app.graph.pipeline import build_graph

    settings = MagicMock(spec=Settings)
    settings.schema_linker_model = "openai/gpt-oss-20b"
    settings.query_planner_model = "gemini-2.5-flash-lite"
    settings.sql_generator_model = "gemini-2.5-flash-lite"
    settings.explainer_model = "gemini-2.5-flash-lite"

    graph = build_graph(mock_duckdb_conn, mock_llm, settings)
    initial = PipelineState(
        user_question="Which 5 artists have the most albums?",
        schema_info=mock_schema_info,
    )
    result = graph.invoke(initial)

    # All agent outputs populated
    assert result["linked_schema"] is not None
    assert result["query_plan"] is not None
    assert len(result["query_plan"]) > 0
    assert result["generated_sql"] is not None
    assert result["final_answer"] is not None
    assert len(result["final_answer"]) > 0

    # All 4 agent steps logged
    trace = result["trace_log"]
    names = [s.name for s in trace]
    assert "schema_linker" in names
    assert "query_planner" in names
    assert "sql_generator" in names
    assert "explainer" in names


def test_sql_generator_prompt_includes_sample_values(mock_schema_info):
    """The SQL Generator's prompt should show real sample values for linked columns,
    not just column names — otherwise it has to guess casing/date format/labels blind."""
    from app.agents.sql_generator import run_sql_generator
    from app.llm_client import LLMClient, LLMResponse, Provider
    from app.models.schemas import LinkedSchema, LinkedTableColumns, PipelineState

    llm = MagicMock(spec=LLMClient)
    llm.generate.return_value = LLMResponse(
        text="SELECT Name FROM Artist",
        model="gemini-2.5-flash-lite", provider=Provider.GEMINI,
        input_tokens=10, output_tokens=5, latency_ms=1.0,
    )

    linked = LinkedSchema(table_columns=[LinkedTableColumns(table="Artist", columns=["Name"])])
    state = PipelineState(
        user_question="who has the most albums",
        schema_info=mock_schema_info,
        linked_schema=linked,
        query_plan=["Find the artist with the most albums"],
    )

    run_sql_generator(state, llm, "gemini-2.5-flash-lite")

    user_msg = llm.generate.call_args.kwargs["user"]
    assert "Sample values" in user_msg
    assert "AC/DC" in user_msg
    # Only the linked column ("Name") should appear in the trimmed sample, not ArtistId
    assert "ArtistId" not in user_msg.split("Sample values")[1].split("]")[0]


def test_execution_error_handled_gracefully(mock_schema_info, mock_llm):
    """If DuckDB throws, the explainer should produce a graceful, generic message —
    never leaking the raw execution_error (SQL internals, catalog errors, attempt
    counts) into what the user actually sees."""
    from app.config import Settings
    from app.graph.pipeline import build_graph

    bad_conn = MagicMock()
    bad_conn.execute.side_effect = Exception("syntax error near 'SELEKT'")

    settings = MagicMock(spec=Settings)
    settings.schema_linker_model = "openai/gpt-oss-20b"
    settings.query_planner_model = "gemini-2.5-flash-lite"
    settings.sql_generator_model = "gemini-2.5-flash-lite"
    settings.explainer_model = "gemini-2.5-flash-lite"

    graph = build_graph(bad_conn, mock_llm, settings)
    initial = PipelineState(
        user_question="bad question",
        schema_info=mock_schema_info,
    )
    result = graph.invoke(initial)

    assert result["execution_error"] is not None
    assert result["final_answer"] is not None
    assert "wasn't able" in result["final_answer"].lower()
    # The raw technical error must never leak into the user-facing answer
    assert result["execution_error"] not in result["final_answer"]
    assert "syntax error" not in result["final_answer"].lower()

    # The real error should still be captured on the trace for debugging
    explainer_step = next(s for s in result["trace_log"] if s.name == "explainer")
    assert "syntax error" in (explainer_step.input_summary or "").lower()
