#!/usr/bin/env python3
"""
CI regression gate — compares a fresh CI-fixture eval run against the stored
eval/results/ci_baseline.json and fails (non-zero exit) if EX drops more than
--threshold below the baseline. Spec §7.5.

This is a separate, smaller check from the real 150-question benchmark — it exists
purely as a fast regression tripwire against a fixed ~20-question subset restricted
to 4 small BIRD databases (see build_ci_fixtures.py), not a second benchmark claim.

Also doubles as the baseline-seeding tool (--seed-baseline), so the baseline and the
gate always share the exact same scoring code path and can never silently drift apart.

Usage:
    # Normal CI use — compare a fresh run against the committed baseline:
    python eval/check_regression.py --results eval/results/ci_run_results.json \\
        --databases-dir eval/ci_fixtures/dev_databases

    # One-time (or whenever intentionally re-seeding) baseline creation:
    python eval/check_regression.py --results eval/results/ci_run_results.json \\
        --databases-dir eval/ci_fixtures/dev_databases \\
        --seed-baseline eval/results/ci_baseline.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import RESULTS_DIR, open_bird_db  # noqa: E402
from metrics import aggregate_by_difficulty, execution_accuracy  # noqa: E402

DEFAULT_REGRESSION_THRESHOLD = 0.05

DEFAULT_RESULTS_PATH = RESULTS_DIR / "ci_run_results.json"
DEFAULT_BASELINE_PATH = RESULTS_DIR / "ci_baseline.json"
DEFAULT_FIXTURE_DB_DIR = Path(__file__).resolve().parent / "ci_fixtures" / "dev_databases"


def _score_results(results: list[dict], databases_dir: Path) -> list[dict]:
    """Group by db_id (one connection per DB, reused across its questions) and score.
    Mirrors compare_report.py::_score_results, pointed at the fixture databases."""
    by_db: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_db[r["db_id"]].append(r)

    scored = []
    for db_id, questions in by_db.items():
        conn = open_bird_db(db_id, databases_dir=databases_dir)
        for q in questions:
            ex = execution_accuracy(conn, q["predicted_sql"], q["gold_sql"])
            scored.append({**q, "ex": ex})
        conn.close()
    return scored


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS_PATH)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--databases-dir", type=Path, default=DEFAULT_FIXTURE_DB_DIR)
    parser.add_argument("--threshold", type=float, default=DEFAULT_REGRESSION_THRESHOLD)
    parser.add_argument(
        "--seed-baseline", type=Path, default=None,
        help="Instead of comparing, score --results and WRITE the baseline file here.",
    )
    args = parser.parse_args()

    if not args.results.exists():
        print(f"No results file at {args.results} — nothing to score.")
        sys.exit(1)

    results = json.loads(args.results.read_text())
    scored = _score_results(results, args.databases_dir)
    ex_by_difficulty = aggregate_by_difficulty(scored, "ex")
    current_ex = ex_by_difficulty["overall"]
    hard_errors = [r for r in results if r.get("error")]

    print(f"Scored {len(scored)} question(s) from {args.results}")
    print(f"EX by difficulty: {ex_by_difficulty}")
    if hard_errors:
        print(
            f"{len(hard_errors)} question(s) hit a hard error (not just wrong SQL): "
            f"{[r['question_id'] for r in hard_errors]}"
        )

    if args.seed_baseline:
        baseline = {
            "ex": current_ex,
            "n": len(scored),
            "question_ids": sorted(r["question_id"] for r in results),
            "created": datetime.now(UTC).isoformat(),
        }
        args.seed_baseline.parent.mkdir(parents=True, exist_ok=True)
        args.seed_baseline.write_text(json.dumps(baseline, indent=2))
        print(f"Wrote baseline ({current_ex:.3f} EX, n={len(scored)}) to {args.seed_baseline}")
        return

    if not args.baseline.exists():
        print(
            f"\nNo CI baseline found at {args.baseline} — this gate isn't armed yet.\n"
            "Run this once, deliberately, when you're ready to spend the small API "
            "cost to create one:\n\n"
            f"  python eval/check_regression.py --results {args.results} "
            f"--databases-dir {args.databases_dir} --seed-baseline {args.baseline}\n"
        )
        sys.exit(1)

    baseline = json.loads(args.baseline.read_text())
    baseline_ex = baseline["ex"]
    delta = current_ex - baseline_ex

    print(f"\nCurrent EX: {current_ex:.3f}  |  Baseline EX: {baseline_ex:.3f}  |  Δ: {delta:+.3f}")

    if delta < -args.threshold:
        print(
            f"\nFAIL: EX dropped {abs(delta) * 100:.1f}pp, more than the "
            f"{args.threshold * 100:.0f}pp threshold."
        )
        sys.exit(1)

    print("\nPASS: no regression beyond threshold.")


if __name__ == "__main__":
    main()
