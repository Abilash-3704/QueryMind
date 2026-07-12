# Project: QueryMind — Multi-Agent Text-to-SQL Analyst with Evaluation Harness

## 1. One-line description

A multi-agent system that converts natural language questions into SQL, executes them against a user-uploaded CSV/dataset, self-corrects on failure, and explains the results in plain English — with a rigorous evaluation harness (benchmarked on BIRD) that quantifies how much the multi-agent pipeline improves accuracy over a naive single-prompt baseline.

## 2. Goal of this project

This is a portfolio project for AI engineering job applications. The two things that must be true at the end:
1. It is a real, deployed, working product a stranger can use (upload a CSV, ask questions, get answers).
2. It has a defensible, quantified engineering result: "multi-agent pipeline achieves X% execution accuracy on BIRD dev set vs Y% for a naive single-prompt baseline, with the largest gains on 'challenging' difficulty queries."

Build in phases. Do not skip the eval harness — it is the most important part of the project, more important than UI polish.

---

## 3. Tech Stack (all free-tier / free / local)

- **Language:** Python 3.11+
- **Dependency management:** `uv`
- **LLM providers:**
  - Google Gemini (Gemini 1.5/2.0 Flash) via `google-genai` SDK — used for SQL generation and planning
  - Groq (`openai/gpt-oss-20b`, with `openai/gpt-oss-120b` or `qwen/qwen3.6-27b` as a stronger option if needed) via `groq` SDK — used for schema linking and lightweight classification tasks. Note: Groq deprecated `llama-3.1-8b-instant` and `llama-3.3-70b-versatile` (announced June 17, 2026, shutdown ~August 16, 2026) — do not build against those model IDs; use the GPT-OSS/Qwen models above instead. Always check `console.groq.com/docs/models` and `console.groq.com/docs/deprecations` before finalizing a model ID, since Groq's catalog rotates frequently.
  - Both accessed through a single internal `llm_client.py` abstraction so agents don't care which provider they're calling; model choice is configurable per-agent via a config file/env vars
- **Orchestration:** LangGraph (`langgraph`) — model the pipeline as an explicit state graph with conditional edges (for the validator retry loop)
- **Database engine:** DuckDB (`duckdb` python package) — used both for the demo (loading uploaded CSVs) and can run SQLite files too for BIRD eval where needed
- **Backend:** FastAPI + `uvicorn`
- **Data validation:** Pydantic v2 (also used to force structured LLM outputs where possible)
- **Frontend:** React (Vite + TypeScript) — a standalone SPA calling the FastAPI backend over REST. Styling and animation stack:
  - **Tailwind CSS** for styling (utility-first, fast to iterate, pairs well with a dark "data console" aesthetic)
  - **shadcn/ui** for base components (dialogs, tabs, inputs) so you're not hand-building primitives
  - **Framer Motion** for animations — panel transitions, agent-step reveal animations, typing/streaming text effect for the answer, animated progress through the pipeline stages
  - **Recharts** or **Visx** for charts (bar/line/pie based on Chart Selector Agent's output)
  - **react-syntax-highlighter** or **Shiki** for animated/highlighted SQL display in the "Show SQL" panel
  - **Zustand** (lightweight) or React Context for client-side session/chat state — no need for Redux at this scale
- **Tracing/Observability:** Langfuse (free cloud tier) — instrument every agent call (input, output, latency, token usage, cost)
- **Testing:** `pytest`
- **Linting:** `ruff`
- **Containerization:** Docker + `docker-compose.yml` (backend + frontend services)
- **CI/CD:** GitHub Actions — run `pytest` + the eval suite on every push to `main`, fail if execution accuracy drops below a stored baseline threshold
- **Deployment target:** Hugging Face Spaces (Docker SDK) for the live demo; GitHub Actions for CI
- **Eval benchmark:** BIRD dataset (dev set) — download the dev databases + question/gold-SQL JSON files

---

## 4. Repository structure

```
querymind/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app entrypoint
│   │   ├── config.py                # Pydantic settings, env vars, model config per agent
│   │   ├── llm_client.py            # Unified interface over Gemini + Groq
│   │   ├── db/
│   │   │   ├── session_db.py        # In-memory DuckDB session management for uploaded CSVs
│   │   │   └── sandbox.py           # Read-only execution guardrails (block DROP/DELETE/UPDATE/INSERT/ALTER)
│   │   ├── agents/
│   │   │   ├── schema_linker.py
│   │   │   ├── query_planner.py
│   │   │   ├── sql_generator.py
│   │   │   ├── validator.py
│   │   │   ├── explainer.py
│   │   │   └── chart_selector.py
│   │   ├── graph/
│   │   │   └── pipeline.py          # LangGraph state graph wiring all agents together
│   │   ├── models/
│   │   │   └── schemas.py           # Pydantic models: QueryRequest, QueryResponse, AgentTrace, etc.
│   │   ├── routes/
│   │   │   ├── query.py             # POST /query
│   │   │   ├── upload.py            # POST /upload (CSV → session DuckDB)
│   │   │   └── eval.py              # GET /eval-report
│   │   └── tracing.py               # Langfuse setup/wrapper
│   ├── tests/
│   │   ├── test_agents.py
│   │   ├── test_pipeline.py
│   │   └── test_guardrails.py
│   ├── Dockerfile
│   └── pyproject.toml
│
├── eval/
│   ├── data/                        # BIRD dev set (databases + questions) — gitignored, downloaded via script
│   ├── download_bird.py             # Script to fetch BIRD dev set
│   ├── run_baseline.py              # Naive single-prompt baseline pipeline for comparison
│   ├── run_multiagent_eval.py       # Runs full multi-agent pipeline over BIRD questions
│   ├── metrics.py                   # Execution accuracy, Valid Efficiency Score (VES), exact match
│   ├── results/                     # JSON/CSV output of eval runs, committed to repo for the README
│   └── compare_report.py            # Generates baseline vs multi-agent comparison table, broken down by difficulty
│
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/
│   │   │   └── client.ts            # fetch wrappers for /upload, /query, /eval-report
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.tsx      # session info, uploaded tables, schema preview
│   │   │   │   └── TopBar.tsx
│   │   │   ├── upload/
│   │   │   │   └── CsvDropzone.tsx  # animated drag-and-drop upload
│   │   │   ├── chat/
│   │   │   │   ├── ChatWindow.tsx
│   │   │   │   ├── MessageBubble.tsx        # streaming/typing text animation for answers
│   │   │   │   └── ClarificationPrompt.tsx
│   │   │   ├── pipeline/
│   │   │   │   ├── AgentPipelineViz.tsx     # animated node graph showing live agent progress
│   │   │   │   ├── AgentStepCard.tsx        # per-agent trace: latency, tokens, model, expandable I/O
│   │   │   │   └── RetryLoopIndicator.tsx   # visualizes validator→generator retry loop when it fires
│   │   │   ├── sql/
│   │   │   │   └── SqlPanel.tsx             # syntax-highlighted, animated reveal
│   │   │   ├── charts/
│   │   │   │   └── ResultChart.tsx          # Recharts wrapper, animated transitions between chart types
│   │   │   └── eval/
│   │   │       ├── EvalDashboard.tsx        # baseline vs multi-agent comparison view
│   │   │       └── DifficultyBarChart.tsx
│   │   ├── hooks/
│   │   │   └── useQuerySession.ts   # session state, query lifecycle, polling/streaming
│   │   ├── store/
│   │   │   └── sessionStore.ts      # Zustand store
│   │   └── styles/
│   │       └── globals.css          # Tailwind base + custom theme tokens
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── package.json
│   └── Dockerfile
│
├── .github/
│   └── workflows/
│       ├── ci.yml                   # pytest + lint on every push
│       └── eval-regression.yml      # Run mini eval set, fail if accuracy regresses below threshold
│
├── docker-compose.yml
├── .env.example
├── README.md                        # Architecture diagram, setup instructions, eval results table, demo link
└── PROJECT_SPEC.md                  # This file
```

---

## 5. Agent pipeline — detailed behavior

Model as a LangGraph `StateGraph`. Shared state object passed between nodes includes: `user_question`, `schema_info`, `query_plan`, `generated_sql`, `execution_result`, `execution_error`, `retry_count`, `final_answer`, `chart_spec`, `trace_log`.

### 5.1 Schema Linker Agent
- **Input:** full schema of the active DuckDB session (table names, column names, types, a few sample rows per table)
- **Task:** identify which tables/columns are relevant to the user's question; if the schema is large, this narrows context for downstream agents
- **Model:** Groq `openai/gpt-oss-20b` (fast, cheap — this is a classification-flavored task, doesn't need the strongest model)
- **Output:** structured list of relevant tables + columns (Pydantic model), plus a confidence/ambiguity flag

### 5.2 Query Planner Agent
- **Input:** user question + linked schema subset
- **Task:** break the question into a step-by-step logical plan in plain English (e.g., "1. Filter orders to 2023. 2. Join with customers on customer_id. 3. Group by region. 4. Sum revenue.")
- **Model:** Gemini Flash
- **Output:** ordered list of plan steps (string list)
- **Note:** if the question is ambiguous (e.g., missing a time range with no reasonable default), this agent should raise a `clarification_needed` flag with a suggested clarifying question instead of guessing — return this to the user via the API rather than proceeding

### 5.3 SQL Generator Agent
- **Input:** query plan + linked schema subset (with column types)
- **Task:** write a single valid DuckDB SQL query implementing the plan
- **Model:** Gemini Flash
- **Output:** raw SQL string
- **Constraint:** must only reference tables/columns from the linked schema; system prompt must explicitly forbid DDL/DML (SELECT-only)

### 5.4 Validator Agent (with tool access)
- **Task:**
  1. Static check: does the SQL parse? Does it reference only SELECT statements? (regex/sqlglot-based check before execution — belt-and-suspenders alongside prompt instructions)
  2. Execute the query against the sandboxed DuckDB connection (read-only role/permissions if possible; at minimum, reject any non-SELECT statement in code, not just via prompting)
  3. Sanity checks on result: zero rows returned unexpectedly? Column count/types roughly matching what the plan implies?
- **On failure (syntax error, execution error, or failed sanity check):** construct a feedback message with the specific error and route back to SQL Generator Agent with the error appended to context. Max 3 retries, tracked via `retry_count` in state. If still failing after 3 retries, return a graceful failure message to the user (do not hallucinate an answer).
- **On success:** pass `execution_result` (as a dataframe/list of dicts) forward

### 5.5 Explainer Agent
- **Input:** original question + execution result (actual data, capped/sampled if very large)
- **Task:** write a plain-English answer summarizing the result, grounded strictly in the returned data (explicitly instruct the model not to state numbers not present in the result set)
- **Model:** Gemini Flash
- **Output:** natural language answer string

### 5.6 Chart Selector Agent (can be a deterministic function, not necessarily an LLM call)
- **Task:** inspect result shape (number of columns, types, row count) and pick a chart type: line chart for time-series-like results, bar chart for categorical comparisons, table for anything else
- **Output:** chart spec (type + which columns map to x/y) for the frontend to render (e.g., via Plotly/Altair in Streamlit)

### 5.7 Guardrails (code-level, not prompt-level)
- Implement an actual SQL statement type check before execution (e.g., using `sqlglot` to parse and confirm the top-level statement is `SELECT`) — reject anything else regardless of what the LLM generated. This must be enforced in code, not just requested via system prompt, and should be called out explicitly in the README as a security decision.
- Session-scoped DuckDB connections only — never touch a shared/persistent database from user uploads.
- Timeout on query execution (e.g., 10 seconds) to prevent runaway queries on large uploaded CSVs.

---

## 6. Backend API

### `POST /upload`
- Accepts a CSV file (or multiple files → multiple tables)
- Loads into a new in-memory DuckDB session, returns a `session_id` and inferred schema
- Sessions expire after N minutes of inactivity (simple in-memory TTL dict is fine, no external cache needed)

### `POST /query`
- Body: `{ session_id: str, question: str }`
- Runs the LangGraph pipeline against the session's DuckDB instance
- Returns: `{ answer: str, sql: str, result: list[dict], chart_spec: dict | null, trace: list[AgentStep], clarification_needed: bool, clarification_question: str | null }`
- `trace` includes per-agent: name, input summary, output summary, latency_ms, model_used, tokens_used (pulled from Langfuse-instrumented calls)

### `GET /eval-report`
- Returns the latest committed eval results JSON (baseline vs multi-agent accuracy, broken down by BIRD difficulty level) for the frontend to render as a dashboard

---

## 7. Evaluation harness — detailed methodology

This is the most important deliverable. Build it as its own standalone module, independent of the demo app, but reusing the same agent code.

### 7.1 Dataset
- Download BIRD dev set (databases as SQLite files + `dev.json` with question/gold-SQL/difficulty triples)
- Use the full dev set if feasible, or a stratified random sample (e.g., 150-200 questions, stratified across simple/moderate/challenging) if API rate limits or time are a constraint — clearly document which was used

### 7.2 Baseline to compare against
- Implement `run_baseline.py`: a single LLM call given the full schema + question, asked to directly output SQL — no schema linking, no planning, no validation/retry loop. This is the "naive" comparison point.

### 7.3 Metrics (implement in `eval/metrics.py`)
- **Execution Accuracy (EX):** execute both predicted SQL and gold SQL against the corresponding BIRD database; compare result sets (order-insensitive, handle floating point tolerance) — this is the primary metric
- **Valid Efficiency Score (VES):** BIRD's official metric, rewards correct AND efficient queries — implement per BIRD's published formula (reference their eval scripts if needed, do not need to be byte-identical, but should follow the same intent: correctness first, efficiency as a secondary weighting)
- Break results down by BIRD's difficulty labels: simple / moderate / challenging
- Also track: average retries needed (multi-agent only), average latency per question, average tokens/cost per question — these numbers support the "we made a deliberate cost/accuracy tradeoff" narrative

### 7.4 Output
- `eval/results/baseline_results.json` and `eval/results/multiagent_results.json` — raw per-question results
- `eval/results/comparison_report.md` — auto-generated markdown table, something like:

| Difficulty | Baseline EX | Multi-Agent EX | Δ |
|---|---|---|---|
| Simple | ... | ... | ... |
| Moderate | ... | ... | ... |
| Challenging | ... | ... | ... |
| **Overall** | ... | ... | ... |

This table (with real numbers) goes directly into the README.

### 7.5 CI regression gate
- `.github/workflows/eval-regression.yml`: on every push, run the multi-agent pipeline against a small fixed subset (e.g., 20 questions) and fail the build if EX drops more than a defined threshold (e.g., 5 percentage points) below the last committed baseline number stored in `eval/results/ci_baseline.json`

---

## 8. Frontend (React) — design brief

The goal is a "tech/data-savvy" console feel — think a hybrid of a terminal, a BI tool, and an agent-observability dashboard. Not a generic chatbot UI. This is also a legitimate differentiator versus other portfolio projects, which almost always ship a plain Streamlit or bare chat box.

### 8.1 Visual direction
- Dark theme by default (near-black background, e.g. `#0a0a0f`), with a single accent color used consistently for active/live states (e.g. electric cyan or violet) — avoid rainbow UI, pick one accent
- Monospace font (e.g. `JetBrains Mono` or `Space Mono`) for anything data/SQL/schema-related; a clean sans (e.g. `Inter`) for prose/answers — the contrast between the two reinforces the "data console" feel
- Subtle grid/scanline or dot-grid background texture, very low opacity — reinforces the technical aesthetic without being distracting
- Use glassmorphism sparingly (translucent panel backgrounds with blur) for cards like the agent trace panel, not everywhere

### 8.2 Core screens/panels
1. **Upload screen (empty state):** animated drag-and-drop CSV zone, subtle particle/grid animation in the background, once a file is dropped show an animated schema-inference preview (tables/columns fading in one by one as they're detected)
2. **Main workspace (3-pane layout):**
   - **Left sidebar:** session's tables/schema (collapsible tree), sample rows on hover/click
   - **Center:** chat thread — user question bubbles + answer bubbles with a typing/streaming reveal effect for the plain-English answer, inline chart rendered directly under the relevant answer
   - **Right panel (the standout feature):** **live Agent Pipeline Visualizer** — an animated horizontal/vertical node graph (Schema Linker → Planner → SQL Generator → Validator → Explainer) that lights up node-by-node as the pipeline actually executes for the current question, using real timing from the backend (not faked). If the Validator triggers a retry loop, animate an actual loop-back edge from Validator to SQL Generator with a "retry 1/3" badge. Each node is clickable to expand and show that agent's actual input/output/latency/tokens/model used.
3. **SQL panel:** collapsible, syntax-highlighted SQL block with a subtle "typewriter" reveal animation the first time it appears for a given answer, plus a copy button
4. **Eval Dashboard (separate route/tab):** baseline vs multi-agent comparison table with animated count-up numbers for the accuracy percentages, and an animated grouped bar chart broken down by BIRD difficulty level (simple/moderate/challenging)

### 8.3 Animation principles (Framer Motion)
- Use animation to communicate real system state, not just decoration — the agent pipeline visualizer's animation timing should be driven by actual backend latency per step, not a fixed fake duration
- Staggered fade/slide-in for lists (schema tables, trace steps)
- Layout animations (`layoutId`) for smooth transitions when panels expand/collapse (e.g., SQL panel, agent step cards)
- Micro-interactions: button hover/press states, a subtle pulse on the active pipeline node, a satisfying "settle" animation when the final chart renders
- Keep animations fast (150–300ms) — this should feel snappy/technical, not slow or gimmicky; slow animations undercut the "professional tool" feel

### 8.4 API integration
- REST calls to FastAPI backend (`/upload`, `/query`, `/eval-report`) via a small typed `api/client.ts` fetch wrapper
- If time allows, upgrade `/query` to stream agent-step events via Server-Sent Events (SSE) or WebSocket so the pipeline visualizer animates in real time as each agent completes, rather than waiting for the full response and animating it after the fact — this is a nice-to-have (Phase 6b), not required for v1. If not implemented, animate optimistically based on typical per-agent latency from the trace once the full response arrives.
- Store `session_id` and chat history in a Zustand store, not local component state, so it survives tab/panel navigation within the SPA

### 8.5 Responsiveness
- Optimize for desktop/laptop widths first (this is a demo tool, primarily used at a desk) — a working mobile layout is a nice-to-have, not a priority

---

## 9. Observability

- Wrap every agent's LLM call in a Langfuse trace/span (`@observe` decorator or manual `langfuse.trace()`), tagging with agent name, model used, and session_id
- Capture: prompt, completion, latency, token counts, estimated cost
- Link a sample Langfuse trace URL in the README

---

## 10. Deployment steps to document in README

1. `docker-compose up` for local dev (backend + React frontend as two services, Vite dev server proxying to FastAPI)
2. GitHub Actions runs backend tests + eval regression, and frontend build/lint, on push
3. Backend Dockerfile deployed to Hugging Face Spaces (Docker SDK) or Render free tier
4. Frontend: `npm run build` produces a static bundle — deploy to **Vercel free tier** (best fit for a Vite/React SPA), pointing its API calls at the deployed backend URL via an env var (`VITE_API_BASE_URL`)
5. Environment variables needed: backend — `GEMINI_API_KEY`, `GROQ_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`; frontend — `VITE_API_BASE_URL`. Documented in `.env.example` files for both, never committed
6. Configure CORS explicitly on the FastAPI backend to allow the deployed Vercel origin

---

## 11. Build order (phases — build and verify each before moving to the next)

1. **Phase 1:** Core pipeline working end-to-end on a hardcoded local CSV (Chinook or similar), no retry loop yet, no eval — just prove schema linking → plan → SQL → execute → explain works
2. **Phase 2:** Add Validator retry loop + guardrails (sqlglot SELECT-only check, timeouts)
3. **Phase 3:** Add CSV upload + session management (in-memory DuckDB per session)
4. **Phase 4:** Build the eval harness (baseline + multi-agent runners, metrics, comparison report) against a BIRD sample — get real numbers
5. **Phase 5:** Add Langfuse tracing throughout
6. **Phase 6:** Build the React frontend — start with the 3-pane workspace (upload, chat, agent pipeline visualizer) using real (not mocked) API calls, then layer in Framer Motion animations once the functional version works. Build the Eval Dashboard route last.
   - **Phase 6b (optional stretch):** convert `/query` to stream agent-step events (SSE/WebSocket) so the pipeline visualizer animates in real time
7. **Phase 7:** Dockerize both services, set up GitHub Actions (backend tests + eval regression gate + frontend build/lint), deploy backend to Hugging Face Spaces/Render and frontend to Vercel
8. **Phase 8:** Write the README (architecture diagram, screenshot/GIF of the animated pipeline visualizer, setup steps, real eval numbers table, live demo link, one detailed failure-case writeup, "what I'd do differently at scale" section)

---

## 12. Non-goals (explicitly out of scope, to keep this shippable)

- No user authentication/accounts
- No persistent multi-user data storage — sessions are ephemeral and in-memory only
- No support for write/mutating SQL — read-only analyst tool only
- No fine-tuning of models — this project is about orchestration and evaluation, not model training
- No support for databases other than DuckDB/SQLite in v1