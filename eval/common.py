"""
Shared harness for BIRD eval runners (run_baseline.py, run_multiagent_eval.py).

Handles: stratified sampling, per-question DuckDB connections against BIRD SQLite
databases, checkpointed result writing (resume-safe against rate-limit interruptions),
and cost estimation. Scoring (EX/VES) happens later in compare_report.py — runners only
capture the predicted SQL + cost/latency/token metadata.
"""
from __future__ import annotations

import json
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import duckdb
from tqdm import tqdm

# Make `app` importable without installing the backend package
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.session_db import get_schema_info  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
DATA_DIR = EVAL_DIR / "data"
RESULTS_DIR = EVAL_DIR / "results"
DEV_JSON_PATH = DATA_DIR / "dev.json"
DEV_DATABASES_DIR = DATA_DIR / "dev_databases"

DIFFICULTIES = ("simple", "moderate", "challenging")

# USD per 1M tokens — list prices, used only for an "estimated cost" narrative.
# Actual eval runs use free-tier quotas.
PRICE_TABLE = {
    "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "openai/gpt-oss-20b": {"input": 0.10, "output": 0.50},
}


@dataclass
class PredictResult:
    sql: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    retry_count: int = 0
    error: str | None = None
    model_used: str = ""
    # Set this directly when a run spans multiple models (e.g. the multi-agent
    # pipeline mixes Groq + Gemini) — estimate_cost() can't price a combined
    # token count against a single model's rate card in that case.
    est_cost_usd: float | None = None


@dataclass
class QuestionResult:
    question_id: int
    db_id: str
    difficulty: str
    question: str
    gold_sql: str
    predicted_sql: str | None
    error: str | None
    input_tokens: int
    output_tokens: int
    latency_ms: float
    retry_count: int
    est_cost_usd: float
    model_used: str = ""


def load_stratified_sample(
    dev_json_path: Path = DEV_JSON_PATH,
    per_difficulty: int = 50,
    seed: int = 42,
) -> list[dict]:
    """Fixed-seed stratified sample: `per_difficulty` questions from each difficulty level."""
    data = json.loads(dev_json_path.read_text())
    by_difficulty: dict[str, list[dict]] = {d: [] for d in DIFFICULTIES}
    for item in data:
        if item["difficulty"] in by_difficulty:
            by_difficulty[item["difficulty"]].append(item)

    rng = random.Random(seed)
    sample: list[dict] = []
    for level in DIFFICULTIES:
        pool = by_difficulty[level]
        n = min(per_difficulty, len(pool))
        sample.extend(rng.sample(pool, n))
    return sample


def load_all_questions(dev_json_path: Path) -> list[dict]:
    """Load every entry verbatim, no sampling — for a `dev.json` that is already a
    pre-selected fixed subset (e.g. `eval/ci_fixtures/dev.json`), where re-sampling
    on top of an already-small, already-deterministic set would be redundant."""
    return json.loads(dev_json_path.read_text())


def open_bird_db(
    db_id: str, databases_dir: Path = DEV_DATABASES_DIR
) -> duckdb.DuckDBPyConnection:
    """Attach a BIRD dev database (SQLite) read-only into a fresh in-memory DuckDB connection.

    `databases_dir` defaults to the full downloaded dataset; pass
    `eval/ci_fixtures/dev_databases` to read the small committed CI subset instead."""
    db_path = databases_dir / db_id / f"{db_id}.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"BIRD database not found: {db_path}")
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL sqlite; LOAD sqlite;")
    conn.execute(f"ATTACH '{db_path}' AS db (TYPE sqlite, READ_ONLY);")
    conn.execute("USE db;")
    return conn


def build_question_text(item: dict) -> str:
    """Append BIRD's 'evidence' (external knowledge) to the question, as BIRD's own
    eval prompts do — both systems get this equally, so it doesn't bias the comparison."""
    question = item["question"]
    evidence = item.get("evidence")
    if evidence:
        question += f"\n\nContext / domain knowledge: {evidence}"
    return question


def estimate_cost(model_used: str, input_tokens: int, output_tokens: int) -> float:
    prices = PRICE_TABLE.get(model_used)
    if not prices:
        return 0.0
    return (input_tokens / 1_000_000) * prices["input"] + (
        output_tokens / 1_000_000
    ) * prices["output"]


def _load_checkpoint(out_path: Path) -> list[dict]:
    if out_path.exists():
        return json.loads(out_path.read_text())
    return []


def _save_checkpoint(out_path: Path, results: list[dict]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str))


def run_eval(
    sample: list[dict],
    predict,  # Callable[[str, duckdb.DuckDBPyConnection, SchemaInfo, dict], PredictResult]
    out_path: Path,
    label: str = "eval",
    retry_failed: bool = False,
    delay_seconds: float = 0.0,
    databases_dir: Path | None = None,
) -> list[dict]:
    """Run `predict` over every question in `sample`, checkpointing after each one.

    Resumable: if `out_path` already has results for a question_id, it's skipped —
    UNLESS retry_failed=True, in which case previously-errored entries (e.g. from a
    rate-limit outage) are cleared and re-attempted instead of being treated as done.
    `delay_seconds` adds a pause between questions to avoid re-triggering sustained
    provider throttling on a retry pass. `databases_dir` overrides where the BIRD
    SQLite files are read from (defaults to the full downloaded dataset) — pass
    `eval/ci_fixtures/dev_databases` when running against the small CI fixture.
    """
    results = _load_checkpoint(out_path)

    if retry_failed:
        before = len(results)
        results = [r for r in results if not r.get("error")]
        cleared = before - len(results)
        if cleared:
            print(f"[{label}] Clearing {cleared} previously-failed result(s) for retry.")

    done_ids = {r["question_id"] for r in results}

    pending = [item for item in sample if item["question_id"] not in done_ids]
    if not pending:
        print(f"[{label}] All {len(sample)} questions already completed at {out_path}")
        return results

    print(f"[{label}] Running {len(pending)} questions ({len(done_ids)} already done)…")

    for item in tqdm(pending, desc=label):
        q_text = build_question_text(item)
        try:
            conn = open_bird_db(item["db_id"], databases_dir=databases_dir or DEV_DATABASES_DIR)
            schema_info = get_schema_info(conn)
            pred = predict(q_text, conn, schema_info, item)
            conn.close()
        except Exception as exc:
            pred = PredictResult(sql=None, error=f"{type(exc).__name__}: {exc}")

        cost = (
            pred.est_cost_usd
            if pred.est_cost_usd is not None
            else estimate_cost(pred.model_used, pred.input_tokens, pred.output_tokens)
        )
        result = QuestionResult(
            question_id=item["question_id"],
            db_id=item["db_id"],
            difficulty=item["difficulty"],
            question=item["question"],
            gold_sql=item["SQL"],
            predicted_sql=pred.sql,
            error=pred.error,
            input_tokens=pred.input_tokens,
            output_tokens=pred.output_tokens,
            latency_ms=pred.latency_ms,
            retry_count=pred.retry_count,
            est_cost_usd=cost,
            model_used=pred.model_used,
        )
        results.append(result.__dict__)
        _save_checkpoint(out_path, results)

        if delay_seconds:
            time.sleep(delay_seconds)

    print(f"[{label}] Done. {len(results)} total results at {out_path}")
    return results
