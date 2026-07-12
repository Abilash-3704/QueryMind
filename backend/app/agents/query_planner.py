"""
Query Planner Agent
Model: Gemini Flash
Task: decompose the question into a step-by-step logical plan in plain English
"""
from __future__ import annotations

from app.llm_client import LLMClient, infer_provider
from app.models.schemas import AgentStep, LinkedSchema, PipelineState, QueryPlan

_SYSTEM = """\
You are a SQL query planning expert. Given a natural language question and a schema subset
(the relevant tables and columns), produce a step-by-step logical plan that describes how
to answer the question with SQL.

Each step should be a plain English description of one logical operation
(e.g., "Filter orders to only include rows from 2023",
       "Join the Track and Album tables on AlbumId",
       "Group by Genre and count the number of tracks").

Return a JSON object with:
- "steps": a list of step strings (ordered, 2-6 steps is typical)
- "clarification_needed": true only if the question is genuinely unanswerable without more
  information from the user (missing essential context that has no reasonable default)
- "clarification_question": the question to ask the user if clarification_needed is true, else null

Important: do NOT set clarification_needed=true just because the question is broad — make a
reasonable interpretation and proceed. Only use it when truly blocked.
"""


def _linked_schema_to_text(linked: LinkedSchema) -> str:
    lines = []
    for table in linked.tables:
        cols = linked.columns.get(table, [])
        lines.append(f"Table: {table}  Columns: {', '.join(cols)}")
    if linked.notes:
        lines.append(f"\nSchema notes: {linked.notes}")
    return "\n".join(lines)


def run_query_planner(
    state: PipelineState,
    llm: LLMClient,
    model: str,
) -> dict:
    assert state.linked_schema is not None, "linked_schema must be set before query_planner"

    schema_text = _linked_schema_to_text(state.linked_schema)
    user_msg = (
        f"Relevant schema:\n{schema_text}\n\n"
        f"Question: {state.user_question}\n\n"
        "Produce the step-by-step SQL plan."
    )

    resp = llm.generate(
        provider=infer_provider(model),
        model=model,
        system=_SYSTEM,
        user=user_msg,
        temperature=0.0,
        response_schema=QueryPlan,
        agent_name="query_planner",
    )

    plan: QueryPlan = resp.parsed  # type: ignore[assignment]

    step = AgentStep(
        name="query_planner",
        model_used=model,
        latency_ms=resp.latency_ms,
        input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens,
        input_summary=user_msg[:400].replace("\n", " "),
        output_summary=f"{len(plan.steps)} steps; clarification_needed={plan.clarification_needed}",
    )
    return {
        "query_plan": plan.steps,
        "trace_log": state.trace_log + [step],
    }
