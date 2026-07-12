#!/usr/bin/env python3
"""
Phase 3 end-to-end verification script.

Uploads a sample CSV via POST /upload, then runs 3 questions via POST /query
using FastAPI's TestClient (no server needed — runs in-process with real LLM calls).

Usage (from repo root):
    python backend/scripts/test_phase3.py
    python backend/scripts/test_phase3.py "Your own question here"

Environment: a .env file with GEMINI_API_KEY and GROQ_API_KEY.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # type: ignore[import]

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Sample CSV — a small product sales dataset with enough variety to ask
# interesting questions about revenue, categories, and time.
# ---------------------------------------------------------------------------

SAMPLE_CSV = """\
date,product,category,revenue,units_sold
2024-01-15,Widget A,Electronics,1500.00,30
2024-01-20,Gadget B,Electronics,2200.00,44
2024-02-03,Widget A,Electronics,1800.00,36
2024-02-14,Accessory C,Accessories,450.00,90
2024-02-28,Gadget B,Electronics,1900.00,38
2024-03-05,Widget A,Electronics,2100.00,42
2024-03-12,Accessory C,Accessories,600.00,120
2024-03-20,Gadget D,Home & Office,750.00,15
2024-04-01,Widget A,Electronics,1650.00,33
2024-04-10,Gadget B,Electronics,2400.00,48
2024-04-22,Accessory C,Accessories,525.00,105
2024-04-30,Gadget D,Home & Office,900.00,18
"""

DEFAULT_QUESTIONS = [
    "What is the total revenue by category?",
    "Which product had the highest total units sold?",
    "Show me the total revenue per month.",
]

_SEP = "─" * 72


def _print_result(r: dict) -> None:
    answer = r.get("answer", "")
    sql = r.get("sql", "")
    rows = r.get("result") or []
    trace = r.get("trace") or []
    chart = r.get("chart_spec")
    retry_count = r.get("retry_count", 0)

    if sql:
        print("\n▶ GENERATED SQL")
        for line in sql.splitlines():
            print(f"  {line}")

    if r.get("execution_error"):
        print(f"\n▶ ERROR\n  {r['execution_error']}")
    elif rows is not None:
        print(f"\n▶ RESULT ({len(rows)} rows)")
        for row in rows[:10]:
            print(f"  {row}")
        if len(rows) > 10:
            print(f"  … {len(rows) - 10} more")

    print("\n▶ ANSWER")
    for line in answer.splitlines():
        print(f"  {line}")

    if chart:
        print(f"\n▶ CHART SPEC  {chart}")

    if retry_count > 0:
        print(f"\n  ⚠ retried {retry_count} time(s)")

    print("\n▶ AGENT TRACE")
    for i, step in enumerate(trace):
        print(f"\n  [{i + 1}] {step['name']}")
        print(f"       model   : {step['model_used']}")
        print(f"       latency : {step['latency_ms']:.0f} ms")
        tokens = ""
        if step.get("input_tokens"):
            tokens += f"in={step['input_tokens']}"
        if step.get("output_tokens"):
            tokens += f"  out={step['output_tokens']}"
        if tokens:
            print(f"       tokens  : {tokens}")
        if step.get("output_summary"):
            summary = textwrap.shorten(step["output_summary"], width=80, placeholder="…")
            print(f"       summary : {summary}")

    total_ms = sum(s.get("latency_ms", 0) for s in trace)
    total_in = sum(s.get("input_tokens") or 0 for s in trace)
    total_out = sum(s.get("output_tokens") or 0 for s in trace)
    print(
        f"\n  Total latency: {total_ms:.0f} ms | tokens in={total_in} out={total_out}"
    )


def main() -> None:
    questions = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_QUESTIONS

    client = TestClient(app)

    # ── 1. Upload the sample CSV ────────────────────────────────────────────
    print("Uploading sample CSV…")
    r = client.post(
        "/upload",
        files={"files": ("sales.csv", SAMPLE_CSV.encode(), "text/csv")},
    )
    if r.status_code != 200:
        print(f"[ERROR] Upload failed ({r.status_code}): {r.text}")
        sys.exit(1)

    upload_data = r.json()
    session_id = upload_data["session_id"]
    tables = upload_data["tables"]
    ttl = upload_data["expires_in_minutes"]

    print(f"  session_id : {session_id}")
    print(f"  TTL        : {ttl} minutes")
    for t in tables:
        col_names = [c["name"] for c in t["columns"]]
        print(f"  table      : {t['name']}  ({len(col_names)} cols: {', '.join(col_names)})")

    # ── 2. Run questions ────────────────────────────────────────────────────
    for i, question in enumerate(questions):
        print(f"\n{_SEP}")
        print(f"QUESTION {i + 1}: {question}")
        print(_SEP)

        r = client.post("/query", json={"session_id": session_id, "question": question})
        if r.status_code != 200:
            print(f"[ERROR] Query failed ({r.status_code}): {r.text}")
            continue

        _print_result(r.json())

    print(f"\n{_SEP}")
    print("Done.")


if __name__ == "__main__":
    main()
