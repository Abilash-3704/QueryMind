"""
Schema Linker Agent
Model: Groq openai/gpt-oss-20b (fast classification task)
Task: identify which tables/columns are relevant to the user question
"""
from __future__ import annotations

from app.llm_client import LLMClient, infer_provider
from app.models.schemas import (
    AgentStep,
    LinkedSchema,
    PipelineState,
    SchemaInfo,
)

_SYSTEM = """\
You are a database schema analyst. Given a database schema and a natural language question,
identify exactly which tables and columns are needed to answer that question.

Return a JSON object with:
- "table_columns": list of objects, each with "table" (string) and "columns" (list of strings)
  — one entry per relevant table, listing only the columns needed for this question
- "ambiguous": true if the question is ambiguous about which data to use, false otherwise
- "notes": brief explanation of why these tables/columns were chosen (or null)

Example format:
{
  "table_columns": [
    {"table": "Artist", "columns": ["ArtistId", "Name"]},
    {"table": "Album", "columns": ["AlbumId", "ArtistId"]}
  ],
  "ambiguous": false,
  "notes": null
}

Only include tables and columns that are genuinely needed. Do not hallucinate table or
column names that are not in the schema.
"""


def _schema_to_text(schema: SchemaInfo) -> str:
    lines = []
    for table in schema.tables:
        col_strs = ", ".join(f"{c.name} ({c.dtype})" for c in table.columns)
        lines.append(f"Table: {table.name}\n  Columns: {col_strs}")
        if table.sample_rows:
            lines.append(f"  Sample rows: {table.sample_rows[:2]}")
    return "\n\n".join(lines)


def run_schema_linker(
    state: PipelineState,
    llm: LLMClient,
    model: str,
) -> dict:
    assert state.schema_info is not None, "schema_info must be set before schema_linker"

    schema_text = _schema_to_text(state.schema_info)
    user_msg = (
        f"Database schema:\n\n{schema_text}\n\n"
        f"Question: {state.user_question}\n\n"
        "Identify the relevant tables and columns."
    )

    resp = llm.generate(
        provider=infer_provider(model),
        model=model,
        system=_SYSTEM,
        user=user_msg,
        temperature=0.0,
        response_schema=LinkedSchema,
        agent_name="schema_linker",
    )

    linked: LinkedSchema = resp.parsed  # type: ignore[assignment]

    step = AgentStep(
        name="schema_linker",
        model_used=model,
        latency_ms=resp.latency_ms,
        input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens,
        input_summary=user_msg[:400].replace("\n", " "),
        output_summary=f"tables={linked.tables}",
    )
    return {
        "linked_schema": linked,
        "trace_log": state.trace_log + [step],
    }
