# QueryMind — Baseline vs Multi-Agent Comparison (BIRD dev set sample)

| Difficulty | Baseline EX | Multi-Agent EX | Δ EX | Baseline VES | Multi-Agent VES |
|---|---|---|---|---|---|
| Simple | 68.0% | 56.0% | -12.0pp | 64.0 | 53.9 |
| Moderate | 50.0% | 44.0% | -6.0pp | 47.3 | 41.9 |
| Challenging | 48.0% | 36.0% | -12.0pp | 45.9 | 33.1 |
| **Overall** | 55.3% | 45.3% | -10.0pp | 52.4 | 42.9 |

## Cost / latency / retry tradeoff

| Metric | Baseline | Multi-Agent |
|---|---|---|
| Avg latency (ms) | 1407 | 8076 |
| Avg input tokens | 2303 | 3703 |
| Avg output tokens | 83 | 475 |
| Avg est. cost/question (USD) | 0.00026 | 0.00056 |
| Avg retries | 0.00 | 0.36 |
| Questions scored | 150 | 150 |

## Methodology notes

- Stratified sample from the BIRD dev set (fixed seed), not the full dev set — see `eval/common.py::load_stratified_sample`.
- Both predicted and gold SQL are executed on **DuckDB** (with the BIRD SQLite database attached read-only), the same engine that powers the deployed pipeline. This makes the baseline-vs-multi-agent **delta** fully valid; absolute VES is not directly comparable to the public BIRD leaderboard (which scores on sqlite3).
- Execution Accuracy (EX): exact result-set match (`set(predicted) == set(gold)`), matching BIRD's official evaluation script.
- Reward-VES: correctness-gated efficiency score, matching BIRD's official `evaluation_ves.py` bucket/reward formula, with a reduced iteration count (20 vs BIRD's 100) for laptop-scale runs.
- Baseline model(s): `gemini-2.5-flash-lite`. Multi-agent model(s): `gemini-2.5-flash-lite`. Matching models across runs isolates the comparison to architecture, not model choice — see each runner's `--model` flag and module docstring for why the default may differ from the deployed app's Gemini-based config (e.g. a temporary free-tier quota outage).
