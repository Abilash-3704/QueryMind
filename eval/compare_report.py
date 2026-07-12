#!/usr/bin/env python3
"""
Compare baseline vs multi-agent BIRD eval results and generate the README report table.

Reads eval/results/baseline_results.json + multiagent_results.json (produced by
run_baseline.py / run_multiagent_eval.py), scores each predicted SQL against gold
SQL using metrics.py (EX + R-VES), aggregates by BIRD difficulty, and writes:
    eval/results/comparison_report.md    (human-readable, goes in the README)
    eval/results/comparison_report.json  (machine-readable, served by GET /eval-report)

Both result files may contain leftover entries from earlier/abandoned runs with a
different sample size (the harness checkpoints by question_id and accumulates across
runs). To keep the comparison apples-to-apples, this script scores only the
question_ids present in BOTH files — not everything in either JSON.

Usage:
    python eval/compare_report.py
    python eval/compare_report.py --skip-ves          # EX only, much faster (no timing loop)
    python eval/compare_report.py --completed-only     # drop questions where either side
                                                        # errored (e.g. a rate-limit outage),
                                                        # instead of scoring them as 0
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import RESULTS_DIR, estimate_cost, open_bird_db  # noqa: E402
from metrics import aggregate_by_difficulty, execution_accuracy, reward_ves  # noqa: E402

BASELINE_PATH = RESULTS_DIR / "baseline_results.json"
MULTIAGENT_PATH = RESULTS_DIR / "multiagent_results.json"
REPORT_MD_PATH = RESULTS_DIR / "comparison_report.md"
REPORT_JSON_PATH = RESULTS_DIR / "comparison_report.json"

DIFFICULTIES = ("simple", "moderate", "challenging")


def _score_results(results: list[dict], label: str, compute_ves: bool) -> list[dict]:
    """Group by db_id (one connection per DB, reused across its questions) and score."""
    by_db: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_db[r["db_id"]].append(r)

    scored = []
    for db_id, questions in by_db.items():
        try:
            conn = open_bird_db(db_id)
        except FileNotFoundError as exc:
            print(f"[{label}] WARNING: {exc} — scoring {len(questions)} question(s) as incorrect")
            for q in questions:
                scored.append({**q, "ex": 0, "ves": 0.0})
            continue

        for q in questions:
            ex = execution_accuracy(conn, q["predicted_sql"], q["gold_sql"])
            ves = reward_ves(conn, q["predicted_sql"], q["gold_sql"]) if compute_ves else 0.0
            scored.append({**q, "ex": ex, "ves": ves})
        conn.close()

    return scored


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _fmt_ves(x: float) -> str:
    return f"{x:.1f}"


def _recompute_cost(r: dict) -> float:
    """Recompute from token counts + the current PRICE_TABLE rather than trusting the
    stored est_cost_usd, which is stale if a model was added to PRICE_TABLE after the
    run. Only accurate for a single model; multi-model traces fall back to 0."""
    models = [m for m in r.get("model_used", "").split(",") if m]
    if len(models) != 1:
        return r.get("est_cost_usd", 0.0)
    return estimate_cost(models[0], r.get("input_tokens", 0), r.get("output_tokens", 0))


def _secondary_stats(results: list[dict]) -> dict:
    return {
        "avg_retries": statistics.mean(r.get("retry_count", 0) for r in results) if results else 0,
        "avg_latency_ms": statistics.mean(r.get("latency_ms", 0) for r in results) if results else 0,
        "avg_input_tokens": statistics.mean(r.get("input_tokens", 0) for r in results)
        if results
        else 0,
        "avg_output_tokens": statistics.mean(r.get("output_tokens", 0) for r in results)
        if results
        else 0,
        "avg_cost_usd": statistics.mean(_recompute_cost(r) for r in results) if results else 0,
        "n": len(results),
    }


def _distinct_models(results: list[dict]) -> str:
    models = sorted({m for r in results for m in r.get("model_used", "").split(",") if m})
    return ", ".join(models) if models else "unknown"


def _render_markdown(
    ex_baseline: dict, ex_multi: dict, ves_baseline: dict, ves_multi: dict,
    stats_baseline: dict, stats_multi: dict, compute_ves: bool,
    baseline_models: str, multiagent_models: str,
) -> str:
    lines = ["# QueryMind — Baseline vs Multi-Agent Comparison (BIRD dev set sample)", ""]

    if compute_ves:
        lines.append("| Difficulty | Baseline EX | Multi-Agent EX | Δ EX | Baseline VES | Multi-Agent VES |")
        lines.append("|---|---|---|---|---|---|")
        for level in (*DIFFICULTIES, "overall"):
            label = level.capitalize() if level != "overall" else "**Overall**"
            delta = ex_multi[level] - ex_baseline[level]
            lines.append(
                f"| {label} | {_fmt_pct(ex_baseline[level])} | {_fmt_pct(ex_multi[level])} | "
                f"{'+' if delta >= 0 else ''}{delta * 100:.1f}pp | "
                f"{_fmt_ves(ves_baseline[level])} | {_fmt_ves(ves_multi[level])} |"
            )
    else:
        lines.append("| Difficulty | Baseline EX | Multi-Agent EX | Δ EX |")
        lines.append("|---|---|---|---|")
        for level in (*DIFFICULTIES, "overall"):
            label = level.capitalize() if level != "overall" else "**Overall**"
            delta = ex_multi[level] - ex_baseline[level]
            lines.append(
                f"| {label} | {_fmt_pct(ex_baseline[level])} | {_fmt_pct(ex_multi[level])} | "
                f"{'+' if delta >= 0 else ''}{delta * 100:.1f}pp |"
            )

    lines += [
        "",
        "## Cost / latency / retry tradeoff",
        "",
        "| Metric | Baseline | Multi-Agent |",
        "|---|---|---|",
        f"| Avg latency (ms) | {stats_baseline['avg_latency_ms']:.0f} | {stats_multi['avg_latency_ms']:.0f} |",
        f"| Avg input tokens | {stats_baseline['avg_input_tokens']:.0f} | {stats_multi['avg_input_tokens']:.0f} |",
        f"| Avg output tokens | {stats_baseline['avg_output_tokens']:.0f} | {stats_multi['avg_output_tokens']:.0f} |",
        f"| Avg est. cost/question (USD) | {stats_baseline['avg_cost_usd']:.5f} | {stats_multi['avg_cost_usd']:.5f} |",
        f"| Avg retries | {stats_baseline['avg_retries']:.2f} | {stats_multi['avg_retries']:.2f} |",
        f"| Questions scored | {stats_baseline['n']} | {stats_multi['n']} |",
        "",
        "## Methodology notes",
        "",
        "- Stratified sample from the BIRD dev set (fixed seed), not the full dev set — see "
        "`eval/common.py::load_stratified_sample`.",
        "- Both predicted and gold SQL are executed on **DuckDB** (with the BIRD SQLite database "
        "attached read-only), the same engine that powers the deployed pipeline. This makes the "
        "baseline-vs-multi-agent **delta** fully valid; absolute VES is not directly comparable "
        "to the public BIRD leaderboard (which scores on sqlite3).",
        "- Execution Accuracy (EX): exact result-set match (`set(predicted) == set(gold)`), "
        "matching BIRD's official evaluation script.",
        "- Reward-VES: correctness-gated efficiency score, matching BIRD's official "
        "`evaluation_ves.py` bucket/reward formula, with a reduced iteration count "
        "(20 vs BIRD's 100) for laptop-scale runs.",
        f"- Baseline model(s): `{baseline_models}`. Multi-agent model(s): `{multiagent_models}`. "
        "Matching models across runs isolates the comparison to architecture, not model choice — "
        "see each runner's `--model` flag and module docstring for why the default may differ "
        "from the deployed app's Gemini-based config (e.g. a temporary free-tier quota outage).",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-ves", action="store_true", help="Skip VES (EX only, faster)")
    parser.add_argument(
        "--completed-only", action="store_true",
        help="Drop questions where either side errored, instead of scoring them as 0",
    )
    args = parser.parse_args()
    compute_ves = not args.skip_ves

    if not BASELINE_PATH.exists() or not MULTIAGENT_PATH.exists():
        print("Missing result files. Run run_baseline.py and run_multiagent_eval.py first.")
        sys.exit(1)

    baseline_raw = json.loads(BASELINE_PATH.read_text())
    multi_raw = json.loads(MULTIAGENT_PATH.read_text())

    # Restrict to the question_ids common to both files, so leftover checkpoint
    # entries from a differently-sized earlier run don't skew one side's aggregates.
    common_ids = {r["question_id"] for r in baseline_raw} & {r["question_id"] for r in multi_raw}

    if args.completed_only:
        failed_ids = {
            r["question_id"] for r in baseline_raw + multi_raw
            if r.get("error") or not r.get("predicted_sql")
        }
        common_ids -= failed_ids

    dropped_baseline = len(baseline_raw) - sum(1 for r in baseline_raw if r["question_id"] in common_ids)
    dropped_multi = len(multi_raw) - sum(1 for r in multi_raw if r["question_id"] in common_ids)
    if dropped_baseline or dropped_multi:
        print(
            f"Dropping {dropped_baseline} baseline / {dropped_multi} multi-agent leftover "
            f"result(s) not in the common {len(common_ids)}-question sample."
        )
    baseline_raw = [r for r in baseline_raw if r["question_id"] in common_ids]
    multi_raw = [r for r in multi_raw if r["question_id"] in common_ids]

    if len(common_ids) < 10:
        print(
            f"\n⚠ WARNING: only {len(common_ids)} questions available for comparison. "
            "This is too small a sample to draw any conclusion from — treat the numbers "
            "below as diagnostic only, not a reportable result.\n"
        )

    print(f"Scoring {len(baseline_raw)} baseline results…")
    baseline_scored = _score_results(baseline_raw, "baseline", compute_ves)
    print(f"Scoring {len(multi_raw)} multi-agent results…")
    multi_scored = _score_results(multi_raw, "multiagent", compute_ves)

    ex_baseline = aggregate_by_difficulty(baseline_scored, "ex")
    ex_multi = aggregate_by_difficulty(multi_scored, "ex")
    ves_baseline = aggregate_by_difficulty(baseline_scored, "ves") if compute_ves else {}
    ves_multi = aggregate_by_difficulty(multi_scored, "ves") if compute_ves else {}

    stats_baseline = _secondary_stats(baseline_raw)
    stats_multi = _secondary_stats(multi_raw)

    report_md = _render_markdown(
        ex_baseline, ex_multi, ves_baseline, ves_multi, stats_baseline, stats_multi, compute_ves,
        _distinct_models(baseline_raw), _distinct_models(multi_raw),
    )
    REPORT_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD_PATH.write_text(report_md)

    report_json = {
        "execution_accuracy": {"baseline": ex_baseline, "multiagent": ex_multi},
        "valid_efficiency_score": {"baseline": ves_baseline, "multiagent": ves_multi},
        "secondary_stats": {"baseline": stats_baseline, "multiagent": stats_multi},
        "sample_size": {"baseline": len(baseline_raw), "multiagent": len(multi_raw)},
    }
    REPORT_JSON_PATH.write_text(json.dumps(report_json, indent=2))

    print(f"\nWrote {REPORT_MD_PATH}")
    print(f"Wrote {REPORT_JSON_PATH}")
    print("\n" + report_md)


if __name__ == "__main__":
    main()
