"""
Explainer Agent
Model: Gemini Flash
Task: write a plain-English answer grounded strictly in the execution result
"""
from __future__ import annotations

import json

from app.llm_client import LLMClient, infer_provider
from app.models.schemas import AgentStep, PipelineState

_SYSTEM = """\
You are a data analyst explaining query results to a non-technical user.

Rules:
- Ground your answer ONLY in the data provided — never state numbers, names, or facts that
  are not present in the result rows
- Write 2-4 sentences of clear, friendly prose
- If there are zero rows, say so plainly and suggest why that might be
- Do not mention SQL, tables, or technical database terms
- Do not repeat the question back to the user verbatim
"""

# Cap the result rows sent to the model to avoid huge prompts
_MAX_ROWS_IN_PROMPT = 20


def run_explainer(
    state: PipelineState,
    llm: LLMClient,
    model: str,
) -> dict:
    # If execution failed, explain the failure gracefully — never surface the raw
    # execution_error (SQL internals, catalog errors, attempt counts) to the user.
    # The real error is still captured on the trace step for anyone debugging.
    if state.execution_error:
        answer = (
            "I wasn't able to answer that question — the query didn't run successfully "
            "after a few attempts. Try rephrasing or simplifying your question."
        )
        step = AgentStep(
            name="explainer",
            model_used=model,
            latency_ms=0.0,
            input_summary=state.execution_error[:400].replace("\n", " "),
            output_summary="reported a generic failure to the user",
        )
        return {"final_answer": answer, "trace_log": state.trace_log + [step]}

    rows = state.execution_result or []
    sample = rows[:_MAX_ROWS_IN_PROMPT]
    rows_text = json.dumps(sample, default=str, indent=2)
    truncated = len(rows) > _MAX_ROWS_IN_PROMPT
    result_note = (
        f"(Showing {len(sample)} of {len(rows)} rows)" if truncated else f"({len(rows)} rows)"
    )

    user_msg = (
        f"Question: {state.user_question}\n\n"
        f"Query result {result_note}:\n{rows_text}\n\n"
        "Write a plain-English answer based only on this data."
    )

    resp = llm.generate(
        provider=infer_provider(model),
        model=model,
        system=_SYSTEM,
        user=user_msg,
        temperature=0.3,
        agent_name="explainer",
    )

    step = AgentStep(
        name="explainer",
        model_used=model,
        latency_ms=resp.latency_ms,
        input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens,
        input_summary=user_msg[:400].replace("\n", " "),
        output_summary=resp.text[:80].replace("\n", " "),
    )
    return {
        "final_answer": resp.text.strip(),
        "trace_log": state.trace_log + [step],
    }
