#!/usr/bin/env python3
"""
Phase 1 manual verification script.
Runs the full pipeline against 5 sample Chinook questions and prints a
detailed trace so you can visually verify each agent's output.

Usage (from repo root):
    python backend/scripts/test_phase1.py
    python backend/scripts/test_phase1.py "Your own question here"

Environment: a .env file (or exported env vars) with GEMINI_API_KEY and GROQ_API_KEY.
"""
from __future__ import annotations

import sys
import textwrap
import time
from pathlib import Path

# Add backend/ to sys.path so `app` is importable without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # type: ignore[import]

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.config import get_settings  # noqa: E402
from app.db.session_db import get_schema_info, open_chinook  # noqa: E402
from app.graph.pipeline import build_graph  # noqa: E402
from app.llm_client import LLMClient  # noqa: E402
from app.models.schemas import PipelineState  # noqa: E402

SAMPLE_QUESTIONS = [
    "Which 5 artists have the most albums?",
    "What are the top 3 best-selling genres by total revenue?",
    "List the 10 most expensive tracks and their album names.",
    "How many customers does each country have? Show the top 5.",
    "Which employee has handled the most customer support tickets?",
]

_SEP = "─" * 72


def _print_step(idx: int, step) -> None:
    print(f"\n  [{idx + 1}] {step.name}")
    print(f"       model   : {step.model_used}")
    print(f"       latency : {step.latency_ms:.0f} ms")
    tokens = ""
    if step.input_tokens is not None:
        tokens += f"in={step.input_tokens}"
    if step.output_tokens is not None:
        tokens += f"  out={step.output_tokens}"
    if tokens:
        print(f"       tokens  : {tokens}")
    if step.output_summary:
        summary = textwrap.shorten(step.output_summary, width=80, placeholder="…")
        print(f"       summary : {summary}")


def run_question(question: str, graph, conn, schema_info) -> None:
    print(f"\n{_SEP}")
    print(f"QUESTION: {question}")
    print(_SEP)

    initial = PipelineState(user_question=question, schema_info=schema_info)
    result: PipelineState = graph.invoke(initial)  # type: ignore[assignment]

    # ── Schema Linker ──────────────────────────────────────────────────────
    if result.linked_schema:
        ls = result.linked_schema
        print("\n▶ LINKED SCHEMA")
        print(f"  Tables : {ls.tables}")
        for t, cols in ls.columns.items():
            print(f"  {t}: {cols}")
        if ls.ambiguous:
            print(f"  ⚠ ambiguous — {ls.notes}")

    # ── Query Plan ─────────────────────────────────────────────────────────
    if result.query_plan:
        print("\n▶ QUERY PLAN")
        for i, step in enumerate(result.query_plan, 1):
            print(f"  {i}. {step}")

    # ── Generated SQL ──────────────────────────────────────────────────────
    if result.generated_sql:
        print("\n▶ GENERATED SQL")
        for line in result.generated_sql.splitlines():
            print(f"  {line}")

    # ── Execution Result ───────────────────────────────────────────────────
    if result.execution_error:
        print(f"\n▶ EXECUTION ERROR\n  {result.execution_error}")
    elif result.execution_result is not None:
        rows = result.execution_result
        print(f"\n▶ EXECUTION RESULT ({len(rows)} rows)")
        for row in rows[:10]:
            print(f"  {row}")
        if len(rows) > 10:
            print(f"  … {len(rows) - 10} more rows")

    # ── Final Answer ───────────────────────────────────────────────────────
    print("\n▶ ANSWER")
    for line in (result.final_answer or "").splitlines():
        print(f"  {line}")

    # ── Trace ──────────────────────────────────────────────────────────────
    print("\n▶ AGENT TRACE")
    for i, step in enumerate(result.trace_log):
        _print_step(i, step)

    total_latency = sum(s.latency_ms for s in result.trace_log)
    total_in = sum(s.input_tokens or 0 for s in result.trace_log)
    total_out = sum(s.output_tokens or 0 for s in result.trace_log)
    print(
        f"\n  Total pipeline latency: {total_latency:.0f} ms | "
        f"tokens in={total_in} out={total_out}"
    )


def main() -> None:
    # Support passing a custom question as CLI arg
    questions = sys.argv[1:] if len(sys.argv) > 1 else SAMPLE_QUESTIONS

    settings = get_settings()
    llm = LLMClient(settings)

    print("Opening Chinook database…")
    conn = open_chinook()
    schema_info = get_schema_info(conn)
    print(f"Schema loaded: {len(schema_info.tables)} tables")

    print("Building LangGraph pipeline…")
    graph = build_graph(conn, llm, settings)
    print("Pipeline ready.\n")

    for i, question in enumerate(questions):
        if i > 0:
            time.sleep(5)  # avoid per-minute rate limits on free-tier Gemini
        try:
            run_question(question, graph, conn, schema_info)
        except Exception as exc:
            print(f"\n[ERROR] {question!r}\n  {exc}")

    print(f"\n{_SEP}")
    print("Done.")


if __name__ == "__main__":
    main()
