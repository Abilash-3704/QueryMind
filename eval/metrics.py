"""
BIRD-style metrics: Execution Accuracy (EX) and Reward-based Valid Efficiency Score (R-VES).

Mirrors the official bird-bench/mini_dev evaluation logic (evaluation_ex.py /
evaluation_ves.py), adapted to run on DuckDB instead of sqlite3 so the exact same
engine that powers the deployed product also scores it. See PROJECT_SPEC.md §7.3
and the Phase 4 plan for the documented engine-choice tradeoff.
"""
from __future__ import annotations

import concurrent.futures
import math
import statistics
import time
from collections.abc import Iterable
from decimal import Decimal

import duckdb
import sqlglot

DEFAULT_TIMEOUT_S = 30
VES_ITERATIONS = 20  # BIRD's official script uses 100; reduced for laptop-scale runs

# time_ratio → reward bucket, per BIRD's official evaluation_ves.py
_REWARD_BUCKETS = (
    (2.0, 1.25),
    (1.0, 1.0),
    (0.5, 0.75),
    (0.25, 0.5),
)
_MIN_REWARD = 0.25


def _run_with_timeout(conn: duckdb.DuckDBPyConnection, sql: str, timeout_s: int) -> list[tuple]:
    def _run():
        cur = conn.execute(sql)
        return cur.fetchall()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run)
        try:
            return future.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError:
            conn.interrupt()
            raise TimeoutError(f"Query exceeded {timeout_s}s timeout")


def _exec_predicted(conn: duckdb.DuckDBPyConnection, sql: str, timeout_s: int) -> list[tuple]:
    return _run_with_timeout(conn, sql, timeout_s)


def _exec_gold(conn: duckdb.DuckDBPyConnection, gold_sql: str, timeout_s: int) -> list[tuple]:
    """Gold SQL is SQLite-dialect. Try it raw first (DuckDB accepts most SQLite syntax
    since we're reading a sqlite-attached schema); fall back to a sqlglot transpile."""
    try:
        return _run_with_timeout(conn, gold_sql, timeout_s)
    except Exception:
        transpiled = sqlglot.transpile(gold_sql, read="sqlite", write="duckdb")[0]
        return _run_with_timeout(conn, transpiled, timeout_s)


_FLOAT_TOLERANCE_DIGITS = 4


def _round_value(v):
    """Round floats/decimals to a fixed precision so two mathematically-equal expressions
    computed via different paths (e.g. SUM(CASE...) vs a CTE) don't fail exact-tuple
    comparison on a representation-only difference. Spec §7.3 explicitly calls for float
    tolerance. DuckDB returns decimal.Decimal (not float) for DECIMAL-typed columns and
    literals, so both types need handling — round() on a Decimal keeps it Decimal, which
    then compares unequal to a rounded float with the same numeric value, so normalize
    to float first."""
    if isinstance(v, (float, Decimal)):
        return round(float(v), _FLOAT_TOLERANCE_DIGITS)
    return v


def _normalize_rows(rows: Iterable[tuple]) -> set[tuple]:
    """Set-based comparison, matching BIRD's official `set(predicted) == set(gold)`,
    with float rounding so equivalent computations aren't penalized for representation noise.
    """
    return {tuple(_round_value(v) for v in row) for row in rows}


def execution_accuracy(
    conn: duckdb.DuckDBPyConnection,
    predicted_sql: str | None,
    gold_sql: str,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> int:
    """Return 1 if predicted_sql's result set matches gold_sql's, else 0.

    Any exception (invalid SQL, timeout, missing predicted SQL) scores 0 —
    matching BIRD's official evaluation_ex.py behavior.
    """
    if not predicted_sql:
        return 0
    try:
        gold_rows = _normalize_rows(_exec_gold(conn, gold_sql, timeout_s))
        pred_rows = _normalize_rows(_exec_predicted(conn, predicted_sql, timeout_s))
        return int(pred_rows == gold_rows)
    except Exception:
        return 0


def _sigma3_clip(values: list[float]) -> list[float]:
    if len(values) < 2:
        return values
    mean = statistics.mean(values)
    std = statistics.pstdev(values)
    if std == 0:
        return values
    clipped = [v for v in values if mean - 3 * std < v < mean + 3 * std]
    return clipped or values


def _bucket_reward(time_ratio: float) -> float:
    for threshold, reward in _REWARD_BUCKETS:
        if time_ratio >= threshold:
            return reward
    return _MIN_REWARD


def reward_ves(
    conn: duckdb.DuckDBPyConnection,
    predicted_sql: str | None,
    gold_sql: str,
    iterations: int = VES_ITERATIONS,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> float:
    """Reward-based Valid Efficiency Score for one question.

    0.0 if the predicted SQL is incorrect (result-set mismatch). Otherwise, times
    both queries `iterations` times, averages the gold/predicted time ratio (with
    3-sigma outlier clipping, per BIRD's official script), buckets it into a reward,
    and returns sqrt(reward) * 100.
    """
    if execution_accuracy(conn, predicted_sql, gold_sql, timeout_s) == 0:
        return 0.0

    ratios: list[float] = []
    for _ in range(iterations):
        try:
            t0 = time.perf_counter()
            _run_with_timeout(conn, gold_sql, timeout_s)
            gold_time = time.perf_counter() - t0
        except Exception:
            transpiled = sqlglot.transpile(gold_sql, read="sqlite", write="duckdb")[0]
            t0 = time.perf_counter()
            _run_with_timeout(conn, transpiled, timeout_s)
            gold_time = time.perf_counter() - t0

        t0 = time.perf_counter()
        _run_with_timeout(conn, predicted_sql, timeout_s)
        predicted_time = time.perf_counter() - t0

        if predicted_time > 0:
            ratios.append(gold_time / predicted_time)

    if not ratios:
        return 0.0

    clipped = _sigma3_clip(ratios)
    time_ratio = statistics.mean(clipped)
    reward = _bucket_reward(time_ratio)
    return math.sqrt(reward) * 100


def aggregate_by_difficulty(
    scored: list[dict],
    key: str,
    difficulties: tuple[str, ...] = ("simple", "moderate", "challenging"),
) -> dict[str, float]:
    """Average `key` (e.g. "ex" or "ves") across `scored` dicts, grouped by difficulty + overall."""
    out: dict[str, float] = {}
    for level in difficulties:
        subset = [s[key] for s in scored if s["difficulty"] == level]
        out[level] = statistics.mean(subset) if subset else 0.0
    all_values = [s[key] for s in scored]
    out["overall"] = statistics.mean(all_values) if all_values else 0.0
    return out
