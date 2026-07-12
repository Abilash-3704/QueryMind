"""
LangGraph pipeline — Phase 2 (validator + conditional retry loop).

Graph:
  START → schema_linker → query_planner → sql_generator → validator
                                                ↑                ↓ (conditional)
                                                └── retry ───────┤ error + retry_count < 3
                                                                  ↓ success OR exhausted
                                                              explainer → END
"""
from __future__ import annotations

import duckdb
from app.agents.explainer import run_explainer
from app.agents.query_planner import run_query_planner
from app.agents.schema_linker import run_schema_linker
from app.agents.sql_generator import run_sql_generator
from app.agents.validator import run_validator
from app.config import Settings
from app.llm_client import LLMClient
from app.models.schemas import PipelineState
from langgraph.graph import END, START, StateGraph


def _route_after_validator(state: PipelineState) -> str:
    """Retry if there's an error and retries remain; otherwise proceed to explainer."""
    if state.execution_error and state.retry_count < 3:
        return "sql_generator"
    return "explainer"


def build_graph(
    conn: duckdb.DuckDBPyConnection,
    llm: LLMClient,
    settings: Settings,
):
    """Build and compile the Phase 2 pipeline with validator + retry loop."""
    builder = StateGraph(PipelineState)

    builder.add_node(
        "schema_linker",
        lambda s: run_schema_linker(s, llm, settings.schema_linker_model),
    )
    builder.add_node(
        "query_planner",
        lambda s: run_query_planner(s, llm, settings.query_planner_model),
    )
    builder.add_node(
        "sql_generator",
        lambda s: run_sql_generator(s, llm, settings.sql_generator_model),
    )
    builder.add_node("validator", run_validator(conn))
    builder.add_node(
        "explainer",
        lambda s: run_explainer(s, llm, settings.explainer_model),
    )

    builder.add_edge(START, "schema_linker")
    builder.add_edge("schema_linker", "query_planner")
    builder.add_edge("query_planner", "sql_generator")
    builder.add_edge("sql_generator", "validator")
    builder.add_conditional_edges(
        "validator",
        _route_after_validator,
        {"sql_generator": "sql_generator", "explainer": "explainer"},
    )
    builder.add_edge("explainer", END)

    return builder.compile()
