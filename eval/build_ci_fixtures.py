#!/usr/bin/env python3
"""
Build the small, git-committed CI fixture the eval-regression gate runs against.

The full BIRD dataset (eval/data/, ~1.4GB) is gitignored and downloaded on demand —
CI cannot fetch that on every run. Instead this script pulls a small, fixed,
reproducible subset of questions restricted to 4 of BIRD's smallest per-question
databases (superhero, student_club, toxicology, thrombosis_prediction — ~12.5MB
combined) and writes them to eval/ci_fixtures/, which IS committed to git.

This is a separate, smaller question set from the real 150-question benchmark that
produced the README's headline numbers — it exists purely as a fast CI regression
tripwire, not a second benchmark claim. Never cite its EX number alongside the real
comparison_report numbers.

Requires the full dataset to already be present locally (this script never runs in
CI — only the already-committed output of a local run does).

Usage:
    python eval/download_bird.py          # if eval/data/ isn't populated yet
    python eval/build_ci_fixtures.py --total 20 --seed 42
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DATA_DIR, DEV_DATABASES_DIR, DEV_JSON_PATH, DIFFICULTIES, EVAL_DIR  # noqa: E402

SMALL_DB_IDS = ("superhero", "student_club", "toxicology", "thrombosis_prediction")

CI_FIXTURES_DIR = EVAL_DIR / "ci_fixtures"
FIXTURE_DEV_JSON = CI_FIXTURES_DIR / "dev.json"
FIXTURE_DB_DIR = CI_FIXTURES_DIR / "dev_databases"


def select_ci_fixture_questions(
    dev_json_path: Path = DEV_JSON_PATH,
    db_ids: tuple[str, ...] = SMALL_DB_IDS,
    total: int = 20,
    seed: int = 42,
) -> list[dict]:
    """Deterministically sample `total` questions restricted to `db_ids`, split as
    evenly as possible across the 3 difficulty buckets."""
    data = json.loads(dev_json_path.read_text())
    pool = [item for item in data if item["db_id"] in db_ids]

    by_difficulty: dict[str, list[dict]] = defaultdict(list)
    for item in pool:
        by_difficulty[item["difficulty"]].append(item)

    base, remainder = divmod(total, len(DIFFICULTIES))
    counts = {d: base for d in DIFFICULTIES}
    for d in DIFFICULTIES[:remainder]:
        counts[d] += 1

    rng = random.Random(seed)
    selected: list[dict] = []
    for level in DIFFICULTIES:
        candidates = by_difficulty.get(level, [])
        n = min(counts[level], len(candidates))
        selected.extend(rng.sample(candidates, n))
    return selected


def copy_fixture_dbs(
    selected: list[dict],
    src_dir: Path = DEV_DATABASES_DIR,
    dest_dir: Path = FIXTURE_DB_DIR,
) -> None:
    db_ids = {item["db_id"] for item in selected}
    for db_id in db_ids:
        src = src_dir / db_id / f"{db_id}.sqlite"
        if not src.exists():
            raise FileNotFoundError(
                f"BIRD database not found: {src}. Run: python eval/download_bird.py"
            )
        dest = dest_dir / db_id
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / f"{db_id}.sqlite")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--total", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not DEV_JSON_PATH.exists():
        print(
            f"Full BIRD dataset not found at {DATA_DIR}. "
            "Run: python eval/download_bird.py"
        )
        sys.exit(1)

    selected = select_ci_fixture_questions(total=args.total, seed=args.seed)
    if len(selected) < args.total:
        print(
            f"WARNING: only found {len(selected)}/{args.total} questions across "
            f"{SMALL_DB_IDS} — the small-db pool may be smaller than requested."
        )

    CI_FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    FIXTURE_DEV_JSON.write_text(json.dumps(selected, indent=2))
    copy_fixture_dbs(selected)

    by_difficulty = Counter(item["difficulty"] for item in selected)
    by_db = Counter(item["db_id"] for item in selected)
    print(f"Wrote {len(selected)} questions to {FIXTURE_DEV_JSON}")
    print(f"By difficulty: {dict(by_difficulty)}")
    print(f"By db_id: {dict(by_db)}")
    print(f"Copied databases to {FIXTURE_DB_DIR}")


if __name__ == "__main__":
    main()
