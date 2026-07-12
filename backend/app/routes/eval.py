"""GET /eval-report — return latest eval results (Phase 4 placeholder)."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

_RESULTS_PATH = Path(__file__).resolve().parents[3] / "eval" / "results" / "comparison_report.json"


@router.get("/eval-report")
def get_eval_report() -> dict:
    """Return the latest eval comparison results JSON.

    Returns an empty dict until Phase 4 populates eval/results/.
    """
    if _RESULTS_PATH.exists():
        return json.loads(_RESULTS_PATH.read_text())
    return {}
