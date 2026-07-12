#!/usr/bin/env python3
"""
Baseline runner — naive single-prompt text-to-SQL (spec §7.2).

One LLM call: full database schema + question → raw SQL. No schema linking, no
planning, no validation/retry loop.

Default model is gemini-2.5-flash-lite on a paid-tier project — matches the model
used by run_multiagent_eval.py's default, so the comparison isolates architecture,
not model choice. Override with --model (e.g. openai/gpt-oss-20b via Groq) if quota
changes.

Usage:
    python eval/run_baseline.py                 # full stratified sample (150 Q)
    python eval/run_baseline.py --limit 3        # smoke test
    python eval/run_baseline.py --per-difficulty 100
    python eval/run_baseline.py --model openai/gpt-oss-20b
    python eval/run_baseline.py --retry-failed --delay 3   # re-attempt only errored questions
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from common import RESULTS_DIR, PredictResult, load_stratified_sample, run_eval  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.config import get_settings  # noqa: E402
from app.llm_client import LLMClient, infer_provider  # noqa: E402
from app.models.schemas import SchemaInfo  # noqa: E402
from app.tracing import flush_langfuse, traced_session  # noqa: E402

OUT_PATH = RESULTS_DIR / "baseline_results.json"
DEFAULT_MODEL = "gemini-2.5-flash-lite"  # see module docstring

_SYSTEM = """\
You are an expert DuckDB SQL writer. Given a database schema and a question, write a \
single valid DuckDB SQL query that answers the question.

Rules:
- Output ONLY the raw SQL query — no markdown fences, no explanation, no trailing semicolon
- Use only SELECT statements
- Only reference the tables and columns provided in the schema
- Use DuckDB SQL syntax
- Select ONLY the columns needed to directly answer the question — no extra descriptive columns
- Prefer the simplest correct query: for "highest"/"lowest"/"top-N" questions, use
  ORDER BY ... LIMIT N rather than a separate MAX()/MIN() filter
- Return column values exactly as stored — do not transform them into human-readable labels
  unless the question explicitly asks for that
"""


def _schema_to_text(schema: SchemaInfo) -> str:
    lines = []
    for table in schema.tables:
        col_strs = ", ".join(f"{c.name} ({c.dtype})" for c in table.columns)
        lines.append(f"Table: {table.name}\n  Columns: {col_strs}")
        if table.sample_rows:
            lines.append(f"  Sample rows: {table.sample_rows[:2]}")
    return "\n\n".join(lines)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not line.startswith("```")).strip()
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N questions")
    parser.add_argument("--per-difficulty", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument(
        "--retry-failed", action="store_true",
        help="Clear previously-errored questions and re-attempt them",
    )
    parser.add_argument(
        "--delay", type=float, default=0.0, help="Seconds to sleep between questions"
    )
    args = parser.parse_args()

    settings = get_settings()
    llm = LLMClient(settings)
    model = args.model

    sample = load_stratified_sample(per_difficulty=args.per_difficulty, seed=args.seed)
    if args.limit:
        sample = sample[: args.limit]

    def predict(q_text: str, conn, schema_info: SchemaInfo, item: dict) -> PredictResult:
        schema_text = _schema_to_text(schema_info)
        user_msg = f"Schema:\n{schema_text}\n\nQuestion: {q_text}\n\nSQL:"
        with traced_session(
            f"eval-q{item['question_id']}", name="eval_baseline",
            metadata={"question": q_text, "difficulty": item["difficulty"]},
        ):
            resp = llm.generate(
                provider=infer_provider(model),
                model=model,
                system=_SYSTEM,
                user=user_msg,
                temperature=0.0,
                agent_name="baseline_sql_generator",
            )
        return PredictResult(
            sql=_strip_fences(resp.text),
            input_tokens=resp.input_tokens or 0,
            output_tokens=resp.output_tokens or 0,
            latency_ms=resp.latency_ms,
            retry_count=0,
            model_used=model,
        )

    run_eval(
        sample, predict, OUT_PATH, label="baseline",
        retry_failed=args.retry_failed, delay_seconds=args.delay,
    )
    flush_langfuse()


if __name__ == "__main__":
    main()
