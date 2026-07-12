# QueryMind — Session Handoff

This file exists because the previous session's context window filled up. It's written for
a **fresh Claude session with zero prior context** to pick up exactly where things left off.
Read `PROJECT_SPEC.md` first (the full spec), then this file (current state + gotchas), then
`/Users/abilashkm/.claude/plans/indexed-zooming-bird.md` if you need implementation-level
detail on any phase already built (it has the full approved plan for every phase below).

---

## 1. What's done (verified, not just written)

Mapping to `PROJECT_SPEC.md` §11's phase numbers:

| Spec Phase | Status | What it is |
|---|---|---|
| 1 | ✅ Done | Core pipeline: schema linker → planner → SQL generator → explainer, hardcoded Chinook DB |
| 2 | ✅ Done | Validator agent (pure code, no LLM) + sqlglot SELECT-only guardrail + conditional retry loop (max 3) |
| 3 | ✅ Done | `POST /upload` (CSV → session DuckDB), `POST /query`, in-memory session TTL |
| 4 | ✅ Done | BIRD eval harness — **real numbers exist**, see §3 below, don't re-run casually (costs money/time) |
| 5 | ✅ Done | Langfuse tracing — verified live, real trace fetched back via Langfuse's API and confirmed correctly nested |
| 6 (partial) | 🟡 Partial | React frontend — functional 3-pane workspace + full Tailwind/Framer Motion styling pass, **verified live in browser**. Eval Dashboard route NOT built (spec says build it last). SSE streaming NOT built (spec's own "Phase 6b", separate from anything I called "6a/6b" below — see gotcha in §4). |
| 7 | ❌ Not started | Docker, GitHub Actions CI, deploy to HF Spaces/Render + Vercel |
| 8 | 🟡 Partial | `README.md` has real eval numbers + full failure analysis written. Missing: architecture diagram, screenshot/GIF, setup instructions, live demo link (deployment doesn't exist yet) |

**Important naming disambiguation:** within this session I informally called the frontend
work "Phase 6a" (functional, no styling) and "Phase 6b" (Tailwind + Framer Motion). **This is
not the same as spec's own "Phase 6b"**, which is the SSE/WebSocket real-time streaming
stretch goal — that is still **not built**. Don't confuse the two if continuing frontend work.

---

## 2. How to run everything

```bash
# Backend (port 8000 was occupied by an unrelated process on this machine — used 8010 instead)
.venv/bin/uvicorn app.main:app --reload --app-dir backend --port 8010

# Frontend (separate terminal)
cd frontend && npm run dev   # port 5173; frontend/.env.local already points VITE_API_BASE_URL at :8010
```

Or via the Claude Preview MCP tool: `.claude/launch.json` already has `backend` (port 8010)
and `frontend` (port 5173) configured — just call `preview_start` with those names.

**Tests/lint:**
```bash
.venv/bin/pytest backend/tests/ -v          # 32 tests, all passing
.venv/bin/ruff check backend/app backend/tests eval --config backend/pyproject.toml
cd frontend && npm run build                 # tsc --noEmit && vite build
```

**Env vars needed** (all already set in root `.env`): `GEMINI_API_KEY`, `GROQ_API_KEY`,
`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`. `frontend/.env.local` has
`VITE_API_BASE_URL=http://localhost:8010`.

---

## 3. Eval results — already done, don't blindly re-run

Full methodology + analysis is in `README.md`. The short version, because it shapes any
future "improve the pipeline" work:

**The multi-agent pipeline underperformed the naive baseline** on a 150-question stratified
BIRD sample: Baseline EX 55.3% vs Multi-agent EX 45.3% (**-10pp**), and the gap is *worst* on
challenging questions, not best. Root-caused into three separable failure modes (see
README's "Failure analysis" section for detail and evidence):
1. SQL generator adds unrequested extra columns (most common) — not fixed by prompt tweaks
   or a stronger model.
2. Decomposing into CTEs introduces logic bugs a direct query wouldn't have — **is** partly
   a model-capability gap (stronger model fixed this pattern in a targeted test).
3. Schema linker sometimes drops a table the SQL generator needs — independent of model
   strength, confirmed by testing.

A stronger-model test on the 15 known-bad regressions recovered only 3/15 (20%) — real but
not enough to close the gap. **Do not casually re-run the full eval** — it burns real API
calls/cost and took significant iteration to get a clean run (see README's "note on running
this eval" — Gemini free-tier model deprecation + Groq instability were both real blockers
before landing on `gemini-2.5-flash-lite` on a paid-tier key). If asked to improve the
pipeline, the README's "What I'd do differently at scale" section already has the concrete,
reasoned next steps (schema-fallback-to-full-schema, explicit column-count constraint from
planner, stronger model for SQL gen specifically) — read that before proposing new ideas.

Raw results: `eval/results/{baseline,multiagent}_results.json`,
`eval/results/comparison_report.{md,json}` (the JSON is served live by `GET /eval-report`).

---

## 4. Gotchas / non-obvious decisions (read before touching related code)

- **`gemini-2.0-flash-lite` is dead** (Google discontinued it, 404 NOT_FOUND). All configs
  now use `gemini-2.5-flash-lite`. If you see the old name anywhere, it's a regression.
- **`graph.invoke()` returns a plain `dict`, not a `PipelineState` object** — LangGraph
  behavior, not a bug. `routes/query.py` was fixed to use `.get(...)` instead of attribute
  access; if a new call site accesses trace/result fields, use dict access.
- **Langfuse env var naming**: the app reads `LANGFUSE_HOST` (matches `.env`/`.env.example`),
  but the SDK's own auto-detection env var is `LANGFUSE_BASE_URL` (v4 SDK). `tracing.py`
  deliberately passes `host=settings.langfuse_host` explicitly to the `Langfuse()`
  constructor rather than relying on the SDK's env-var auto-read — don't "fix" this by
  renaming to `LANGFUSE_BASE_URL`, it's intentional.
- **The Validator agent never appears in `trace_log`** — it's pure code, no LLM call. Retries
  are visible only via `retry_count` + a second `sql_generator` entry in the trace. The
  frontend's `AgentPipelineViz.tsx` has a documented workaround for this; any new
  trace-consuming code needs to know this too.
- **`infer_provider(model)`** in `llm_client.py` derives Groq vs Gemini from whether the
  model string contains `/` (Groq IDs are namespaced like `openai/gpt-oss-20b`). Don't
  hardcode `Provider.GEMINI`/`Provider.GROQ` in new agent code — use `infer_provider`.
  Deployed app's default per-agent models still differ (Groq for schema_linker, Gemini for
  the rest) — this is intentional (spec's original design), the eval scripts override all
  four to one model for a fair comparison, which is eval-only, not a config to "fix".
- **`llm_client.py`'s retry logic retries on 429 and 503**, not other 4xx (like 404 for a
  dead model — that's a permanent failure, retrying is pointless and correctly doesn't
  happen).
- **Port 8000 is occupied by an unrelated process on this dev machine** (some other local
  service, not ours) — backend runs on 8010 instead. If port 8000 frees up later this is
  cosmetic, not a bug to fix.
- **Two `npm audit` moderate/high findings exist** (esbuild dev-server-only issue, prismjs
  DOM-clobbering irrelevant since we never render untrusted HTML through it) — both need
  breaking major-version bumps to fix. Deliberately deferred; revisit before public
  deployment (Phase 7).
- **Frontend bundle is ~1.3MB** (mostly fonts + framer-motion + react-syntax-highlighter's
  full language bundle) — a `(!) chunk larger than 500kB` build warning exists. Not fixed;
  code-splitting/lazy-loading the syntax highlighter would be the fix if it matters later.
- **`framer-motion`'s gesture props collide with native DOM event prop names** (`onDrag`,
  `onAnimationStart`, etc.) when spreading HTML attrs onto a `motion.*` component — see the
  `Omit<...>` workaround in `frontend/src/components/ui/Button.tsx` if this bites again
  elsewhere.
- **Tailwind is v4** (CSS-first config, no `tailwind.config.js` content array needed) — the
  theme tokens live in `frontend/src/styles/globals.css`'s `@theme` block, not in
  `tailwind.config.ts` (which is deliberately left empty with an explanatory comment).
- **Accent color is electric cyan `#00e5ff`**, confirmed with the user — don't change without
  asking, it's a deliberate brand choice for the whole app (spec §8.1 required "avoid
  rainbow UI, pick one accent").

---

## 5. Recommended next step

In spec's own build order, Phase 7 (Docker + CI/CD + deploy) is next, but there are a few
reasonable alternate entry points depending on priority:

1. **Finish Phase 6 properly**: build the Eval Dashboard route (spec says build it last —
   this is "last" now) using the already-live `GET /eval-report` endpoint and the real
   numbers in §3 above. Relatively contained, reuses existing patterns.
2. **Phase 7 (Docker/CI/deploy)**: makes the project actually demoable by a stranger, which
   is one of the two explicit project goals (spec §2). Backend Dockerfile + frontend
   Dockerfile already exist as empty placeholders in the repo tree.
3. **Phase 8 (README polish)**: architecture diagram + screenshots are still missing; the
   substantive eval content is already written. Lower priority than actually deploying,
   since a demo link matters more than diagrams for a portfolio piece.

My recommendation: **Phase 7 (deployment) before more frontend polish** — a working live
demo link is one of the two explicitly-stated project success criteria (spec §2), and
everything currently works locally but nothing is deployed yet. The Eval Dashboard route is
a nice-to-have that can follow once there's something real to point people at.

Ask the user which they'd like before starting — don't assume.
