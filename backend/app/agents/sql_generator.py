"""
SQL Generator Agent
Model: Gemini Flash
Task: write a single valid DuckDB SQL SELECT query that implements the plan
"""
from __future__ import annotations

from app.llm_client import LLMClient, infer_provider
from app.models.schemas import AgentStep, LinkedSchema, PipelineState, SchemaInfo

_SYSTEM = """\
You are an expert DuckDB SQL writer. Given a step-by-step query plan and the relevant database
schema, write a single valid DuckDB SQL query that implements the plan.

Rules:
- Output ONLY the raw SQL query — no markdown fences, no explanation, no trailing semicolon
- Use only SELECT statements — absolutely no INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, or
  any other DDL/DML
- Only reference the tables and columns provided in the schema — do not hallucinate column names
- Use DuckDB SQL syntax (compatible with most standard SQL; DuckDB supports QUALIFY, UNNEST,
  struct access, etc.)
- If the plan has multiple steps, implement them all in a single query using CTEs or subqueries
- Select ONLY the columns needed to directly answer the question. Do not add extra descriptive,
  contextual, or "helpful" columns that were not asked for — the caller compares your output
  against an exact expected result, so any extra column causes a mismatch even if the answer is
  otherwise correct
- Prefer the simplest correct query. For "highest"/"lowest"/"top-N" questions, use
  ORDER BY ... LIMIT N rather than filtering by MAX()/MIN() equality in a separate CTE — the
  equality-based approach can silently return the wrong number of rows on ties or type mismatches
- Return column values exactly as stored in the schema — do not transform them into
  human-readable labels (e.g. via CASE WHEN) unless the question explicitly asks for that
- Sample values are shown for each column — use them to match the data's actual casing,
  formatting, and value style (e.g. how names, dates, or categories are really stored)
  instead of guessing a format from how the question happens to be phrased
"""


def _linked_schema_to_text(linked: LinkedSchema, schema_info: SchemaInfo) -> str:
    sample_rows_by_table = {t.name: t.sample_rows for t in schema_info.tables}
    lines = []
    for table in linked.tables:
        cols = linked.columns.get(table, [])
        lines.append(f"Table: {table}  Columns: {', '.join(cols)}")
        samples = sample_rows_by_table.get(table, [])
        if samples:
            trimmed = [{c: row.get(c) for c in cols if c in row} for row in samples[:2]]
            lines.append(f"  Sample values: {trimmed}")
    return "\n".join(lines)


def run_sql_generator(
    state: PipelineState,
    llm: LLMClient,
    model: str,
) -> dict:
    assert state.linked_schema is not None
    assert state.query_plan is not None
    assert state.schema_info is not None

    schema_text = _linked_schema_to_text(state.linked_schema, state.schema_info)
    plan_text = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(state.query_plan))

    user_msg = (
        f"Schema:\n{schema_text}\n\n"
        f"Plan:\n{plan_text}\n\n"
        f"Question: {state.user_question}\n\n"
        "Write the DuckDB SQL query (SELECT only, no markdown, no explanation):"
    )

    # On retry, append the previous error so the model can fix it
    if state.execution_error and state.retry_count > 0:
        user_msg += (
            f"\n\nPREVIOUS ATTEMPT FAILED (attempt {state.retry_count}/3):\n"
            f"{state.execution_error}\n\n"
            "Fix the SQL based on this error and try again."
        )

    resp = llm.generate(
        provider=infer_provider(model),
        model=model,
        system=_SYSTEM,
        user=user_msg,
        temperature=0.0,
        agent_name="sql_generator",
    )

    sql = resp.text.strip()
    # Strip accidental markdown fences if the model ignores instructions
    if sql.startswith("```"):
        lines = sql.splitlines()
        sql = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    step = AgentStep(
        name="sql_generator",
        model_used=model,
        latency_ms=resp.latency_ms,
        input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens,
        input_summary=user_msg[:400].replace("\n", " "),
        output_summary=sql[:120].replace("\n", " "),
    )
    return {
        "generated_sql": sql,
        "trace_log": state.trace_log + [step],
    }
