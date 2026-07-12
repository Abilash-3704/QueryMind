# QueryMind

A multi-agent system that converts natural language questions into SQL, executes them
against a database, self-corrects on failure, and explains the results in plain English —
evaluated against the [BIRD benchmark](https://bird-bench.github.io/) with a rigorous,
reproducible comparison against a naive single-prompt baseline.

**Project status:** Phases 1-4 complete (core pipeline, guardrails/retry loop, CSV
upload/session API, BIRD evaluation harness). Frontend, observability, containerization,
and deployment (Phases 5-8) are still in progress — this README will be extended with
setup instructions, an architecture diagram, and a live demo link as those land.

---

## Architecture

LangGraph state machine: `Schema Linker → Query Planner → SQL Generator → Validator
(conditional retry loop, max 3 attempts) → Explainer`. The Validator is pure code, not
an LLM call — it statically confirms the SQL is SELECT-only via `sqlglot` (rejecting
anything else in code, not just via prompting), executes it against a sandboxed DuckDB
connection with a timeout, and on failure routes back to the SQL Generator with the
specific error appended to context.

- **LLM providers:** Google Gemini + Groq, behind a single `LLMClient` abstraction
  (`backend/app/llm_client.py`) so agents never touch a provider SDK directly.
- **Database:** DuckDB — for the live app (per-session, in-memory, loaded from uploaded
  CSVs) and for the eval harness (BIRD's SQLite databases attached read-only).
- **Backend:** FastAPI (`POST /upload`, `POST /query`, `GET /eval-report`).

---

## Evaluation results

Methodology (spec §7): a **stratified random sample of 150 questions** (50 per BIRD
difficulty tier — simple/moderate/challenging, fixed seed) from the BIRD dev set, run
through both a naive single-prompt baseline and the full multi-agent pipeline. Both
systems' predicted SQL is executed against the corresponding BIRD SQLite database
(attached read-only into DuckDB — the same engine that powers the deployed app) and
scored against gold SQL using:

- **Execution Accuracy (EX):** exact result-set match, `set(predicted) == set(gold)`,
  matching BIRD's official evaluation script.
- **Reward-VES:** correctness-gated efficiency score, matching BIRD's official
  `evaluation_ves.py` bucket/reward formula (20 timing iterations instead of BIRD's 100,
  for laptop-scale runs).

Both systems used the same model (`gemini-2.5-flash-lite`) for SQL generation, so the
comparison isolates **architecture**, not model choice.

| Difficulty | Baseline EX | Multi-Agent EX | Δ EX | Baseline VES | Multi-Agent VES |
|---|---|---|---|---|---|
| Simple | 68.0% | 56.0% | -12.0pp | 64.0 | 53.9 |
| Moderate | 50.0% | 44.0% | -6.0pp | 47.3 | 41.9 |
| Challenging | 48.0% | 36.0% | -12.0pp | 45.9 | 33.1 |
| **Overall** | **55.3%** | **45.3%** | **-10.0pp** | 52.4 | 42.9 |

| Cost/latency | Baseline | Multi-Agent |
|---|---|---|
| Avg latency/question | 1.4s | 8.1s |
| Avg cost/question (est.) | $0.00026 | $0.00056 |
| Avg retries | 0.00 | 0.36 |

**The multi-agent pipeline underperformed the naive baseline** on this sample, and the
gap is largest on challenging questions rather than smallest — the opposite of what a
schema-linking + planning + retry architecture is generally expected to deliver. It also
costs ~2x more and takes ~5.7x longer per question. This is the headline finding of this
phase, and the rest of this section is the root-cause investigation, not a rationalization
of it.

### Failure analysis

I inspected every question where the baseline answered correctly but the multi-agent
pipeline did not (22 of 150) and categorized the root cause by reading the actual
predicted SQL side by side with gold. Three distinct, separable failure modes emerged —
this is not one bug, it's three:

**1. The SQL generator adds columns the question never asked for (most common — 3+ of 22).**
E.g. for *"Provide list of patients and their diagnosis with triglyceride (TG) index
greater than 100 of the normal range"* (gold: `SELECT ID, Diagnosis`), the multi-agent
SQL also selected `TG` — the underlying data is correct, but BIRD's exact-match scoring
fails it, since the result columns don't match. The baseline's single, direct prompt
never exhibits this; the multi-agent's plan-then-generate flow appears to encourage
"thorough" answers that break strict-match scoring. I tested whether this was a prompt
wording issue by explicitly instructing the SQL generator not to do this — it recurred
anyway, even after the instruction was added and even when I swapped in a stronger model
(`gemini-2.5-flash` instead of `-lite`) for the SQL-generation step alone. This looks like
a genuine behavioral tendency at this model tier for this prompting pattern, not
something a prompt tweak or a "bigger" lite-tier model reliably fixes.

**2. Decomposing a query into CTEs introduces logic bugs a direct query wouldn't have.**
For *"highest"/"lowest"* questions, the multi-agent frequently builds a `MAX()`/`MIN()`
CTE and joins back on equality, instead of `ORDER BY ... LIMIT 1` like the baseline and
gold. These aren't equivalent: the CTE approach can silently return the wrong number of
rows on ties, and independently computing `MIN()` across two unrelated criteria (e.g.
"oldest, then lowest salary among ties") breaks correct multi-column tie-breaking
semantics entirely. Unlike failure mode #1, this one **is** partly a capability gap — the
stronger model (`gemini-2.5-flash`) fixed this pattern on the one case I isolated it on.

**3. The schema linker sometimes drops a table the SQL generator actually needs.**
For *"Which state special schools have the highest number of enrollees from grades 1
through 12?"*, gold joins `frpm` (which holds `Enrollment (K-12)`) with `schools`. The
schema linker's output included only `schools`, so the SQL generator — never having seen
`frpm` — tried to reference `Enrollment (K-12)` on the wrong table and failed a hard
`Binder Error`, exhausting all 3 validator retries. I confirmed this is independent of
SQL-generation capability: re-running with the stronger model reproduced the identical
failure, because the missing table never reached the SQL generator in the first place —
no amount of SQL-writing skill fixes a reference to a table you were never told about.

**A quantified test of the "is it capability or architecture" question:** I re-ran the
15 confirmed regression questions with `gemini-2.5-flash` for SQL generation only
(schema linking, planning, and explanation stayed on `-flash-lite`). 3 of 15 (20%) now
passed — the ones with logic bugs (mode #2). The extra-column tendency (mode #1) and the
schema-linker omission (mode #3) were unaffected. Extrapolated across all 22 regressions,
this would move overall multi-agent EX from ~45% to roughly ~48-49% — a real but modest
improvement, not enough to close a 10-point gap. I did not run this at full scale (150
questions × 2 systems again) to validate it precisely, because at that point the marginal
information gained didn't justify the additional API cost given the diagnosis was already
conclusive: this is not a single fixable bug, it's three separable failure modes with
different roots, not fixable by any single lever tested so far.

### What I'd do differently at scale

- **Give the SQL generator the full schema as a fallback, not just the linked subset.**
  Schema linking should narrow *focus* for cost/context reasons, but should never be the
  sole source of truth — if the linked subset is missing a table the plan references, the
  SQL generator should be able to fall back to the complete schema rather than hard-failing.
  This directly targets failure mode #3 without touching the linker itself.
- **Constrain the SQL generator's output columns explicitly from the plan**, rather than
  leaving column selection to the model's judgment. E.g. have the Query Planner name the
  exact output columns as a structured field, and pass that as a hard constraint (or a
  post-generation check) rather than a soft prompt instruction — prompt wording alone
  didn't fix mode #1 twice.
  - Add a **column-set post-check** in the Validator: if the result has more columns than
    the plan implies, treat it as a soft failure and retry, the same way the existing
    zero-rows sanity check works.
- **Use a stronger model specifically for SQL generation**, keeping schema linking (a
  cheap classification task) on a small/fast model. The cost delta is small (~$0.0003/query
  extra at these token volumes) and the capability gap is real, even if it isn't the whole
  story.
- **Run a full-scale eval of each fix in isolation**, not combined, so the report can
  attribute the accuracy delta to each specific change — I only had budget to test one
  hypothesis at small scale this round.
- **Widen the sample or run the full BIRD dev set (1,534 questions)** once the above are
  in place, since a 150-question sample has real variance — a handful of tie-breaks or
  edge-case databases visibly move the difficulty-level numbers by several points.

### A note on running this eval

Getting a clean 150-question run took several iterations, and that process is itself
worth documenting since it reflects real operational constraints, not just model quality:

- Gemini's free tier was fully exhausted (`limit: 0`) for `gemini-2.0-flash-lite` on this
  project, and even after switching models and enabling billing, one Gemini API key
  remained stuck on a stale free-tier quota (`RPD: 20`) — a fresh key resolved it.
- Groq's free tier (used as a fallback provider) was unpredictably unstable during testing,
  with individual requests occasionally stalling for hours — not a rate limit our own
  retry/backoff logic could reasonably absorb.
- `llm_client.py`'s retry logic now handles both `429` (rate limit) and `503` (provider
  overload) with exponential backoff, for both providers — this closed a real gap where
  transient infrastructure noise was being scored as an architectural failure.
- The harness checkpoints after every single question and supports a `--retry-failed`
  mode that clears only errored entries for re-attempt, so a multi-hour outage mid-run
  never requires re-spending tokens on already-successful questions.

See `eval/` for the full harness: `download_bird.py`, `common.py` (shared runner +
checkpointing), `metrics.py` (EX/VES), `run_baseline.py`, `run_multiagent_eval.py`,
`compare_report.py`.
