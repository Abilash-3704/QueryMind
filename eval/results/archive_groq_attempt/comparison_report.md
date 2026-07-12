# QueryMind — Baseline vs Multi-Agent Comparison (BIRD dev set sample)

| Difficulty | Baseline EX | Multi-Agent EX | Δ EX | Baseline VES | Multi-Agent VES |
|---|---|---|---|---|---|
| Simple | 0.0% | 0.0% | +0.0pp | 0.0 | 0.0 |
| Moderate | 100.0% | 100.0% | +0.0pp | 100.0 | 100.0 |
| Challenging | 0.0% | 0.0% | +0.0pp | 0.0 | 0.0 |
| **Overall** | 16.7% | 16.7% | +0.0pp | 16.7 | 16.7 |

## Cost / latency / retry tradeoff

| Metric | Baseline | Multi-Agent |
|---|---|---|
| Avg latency (ms) | 42868 | 35977 |
| Avg input tokens | 1404 | 3276 |
| Avg output tokens | 480 | 1584 |
| Avg est. cost/question (USD) | 0.00038 | 0.00112 |
| Avg retries | 0.00 | 0.17 |
| Questions scored | 6 | 6 |

## Methodology notes

- Stratified sample from the BIRD dev set (fixed seed), not the full dev set — see `eval/common.py::load_stratified_sample`.
- Both predicted and gold SQL are executed on **DuckDB** (with the BIRD SQLite database attached read-only), the same engine that powers the deployed pipeline. This makes the baseline-vs-multi-agent **delta** fully valid; absolute VES is not directly comparable to the public BIRD leaderboard (which scores on sqlite3).
- Execution Accuracy (EX): exact result-set match (`set(predicted) == set(gold)`), matching BIRD's official evaluation script.
- Reward-VES: correctness-gated efficiency score, matching BIRD's official `evaluation_ves.py` bucket/reward formula, with a reduced iteration count (20 vs BIRD's 100) for laptop-scale runs.
- Baseline model(s): `openai/gpt-oss-20b`. Multi-agent model(s): `openai/gpt-oss-20b`. Matching models across runs isolates the comparison to architecture, not model choice — see each runner's `--model` flag and module docstring for why the default may differ from the deployed app's Gemini-based config (e.g. a temporary free-tier quota outage).
