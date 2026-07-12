#!/usr/bin/env python3
"""
Multi-agent runner — full QueryMind pipeline (schema linking → planning → SQL
generation → validation/retry → explanation), reusing the exact deployed graph.

Overrides ALL FOUR agent models (schema_linker, query_planner, sql_generator,
explainer) to a single model — default gemini-2.5-flash-lite on a paid-tier project
— rather than the deployed app's default per-agent split (Groq for schema linking,
Gemini for the rest). Using one model everywhere in eval avoids a mixed-provider
run silently depending on whichever provider happens to be healthy that day; it
also matches the baseline runner's single-model setup, so the comparison still
isolates architecture, not model choice. This is an eval-only override —
backend/app/config.py defaults (used by the deployed app) are untouched.

Usage:
    python eval/run_multiagent_eval.py                 # full stratified sample (150 Q)
    python eval/run_multiagent_eval.py --limit 3        # smoke test
    python eval/run_multiagent_eval.py --per-difficulty 100
    python eval/run_multiagent_eval.py --model openai/gpt-oss-20b   # all-Groq instead
    python eval/run_multiagent_eval.py --retry-failed --delay 3   # re-attempt only errored questions
    python eval/run_multiagent_eval.py --fixtures-dir eval/ci_fixtures --out eval/results/ci_run_results.json
        # small committed CI subset instead of the full dataset — see check_regression.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from common import (  # noqa: E402
    RESULTS_DIR,
    PredictResult,
    estimate_cost,
    load_all_questions,
    load_stratified_sample,
    run_eval,
)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.config import get_settings  # noqa: E402
from app.graph.pipeline import build_graph  # noqa: E402
from app.llm_client import LLMClient  # noqa: E402
from app.models.schemas import PipelineState, SchemaInfo  # noqa: E402
from app.tracing import flush_langfuse, traced_session  # noqa: E402

OUT_PATH = RESULTS_DIR / "multiagent_results.json"
DEFAULT_MODEL = "gemini-2.5-flash-lite"  # see module docstring


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
    parser.add_argument(
        "--fixtures-dir", type=str, default=None,
        help="Read a pre-selected fixed subset from this dir (e.g. eval/ci_fixtures) "
        "instead of sampling from the full downloaded BIRD dataset — used by the "
        "CI regression gate, which can't fetch the full 1.4GB dataset on every run.",
    )
    parser.add_argument(
        "--out", type=str, default=None,
        help="Override the output path (default: eval/results/multiagent_results.json). "
        "The CI gate must pass its own path here so it never clobbers the real run.",
    )
    args = parser.parse_args()

    settings = get_settings().model_copy(
        update={
            "schema_linker_model": args.model,
            "query_planner_model": args.model,
            "sql_generator_model": args.model,
            "explainer_model": args.model,
        }
    )
    llm = LLMClient(settings)

    databases_dir = None
    if args.fixtures_dir:
        fixtures_dir = Path(args.fixtures_dir)
        sample = load_all_questions(fixtures_dir / "dev.json")
        databases_dir = fixtures_dir / "dev_databases"
    else:
        sample = load_stratified_sample(per_difficulty=args.per_difficulty, seed=args.seed)
    if args.limit:
        sample = sample[: args.limit]

    out_path = Path(args.out) if args.out else OUT_PATH

    def predict(q_text: str, conn, schema_info: SchemaInfo, item: dict) -> PredictResult:
        graph = build_graph(conn, llm, settings)
        initial = PipelineState(user_question=q_text, schema_info=schema_info)
        with traced_session(
            f"eval-q{item['question_id']}", name="eval_multiagent",
            metadata={"question": q_text, "difficulty": item["difficulty"]},
        ):
            result = graph.invoke(initial)

        trace = result["trace_log"]
        input_tokens = sum(s.input_tokens or 0 for s in trace)
        output_tokens = sum(s.output_tokens or 0 for s in trace)
        latency_ms = sum(s.latency_ms for s in trace)
        models_used = sorted({s.model_used for s in trace if s.model_used})
        # Sum cost per-step (each step may use a different model/provider) rather than
        # pricing the combined token count against a single model's rate card.
        total_cost = sum(
            estimate_cost(s.model_used, s.input_tokens or 0, s.output_tokens or 0)
            for s in trace
        )

        return PredictResult(
            sql=result.get("generated_sql"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            retry_count=result.get("retry_count", 0),
            error=result.get("execution_error"),
            model_used=",".join(models_used),
            est_cost_usd=total_cost,
        )

    run_eval(
        sample, predict, out_path, label="multiagent",
        retry_failed=args.retry_failed, delay_seconds=args.delay,
        databases_dir=databases_dir,
    )
    flush_langfuse()


if __name__ == "__main__":
    main()
