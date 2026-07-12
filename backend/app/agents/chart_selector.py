"""
Chart Selector — deterministic function, no LLM.

Inspects the result shape and returns a minimal chart spec for the frontend,
or None if the data doesn't fit a simple chart (frontend falls back to a table).
"""
from __future__ import annotations

import re


def select_chart(rows: list[dict]) -> dict | None:
    """Return a chart spec dict or None if no chart is appropriate.

    Spec shape: {"type": "bar"|"line"|"pie", "x": col_name, "y": col_name}
    """
    if not rows or len(rows) < 2:
        return None

    cols = list(rows[0].keys())

    # Only attempt a chart when we have exactly 2 columns (x + y)
    if len(cols) != 2:
        return None

    x_col, y_col = cols[0], cols[1]
    y_val = rows[0][y_col]

    # y must be numeric
    if not isinstance(y_val, (int, float)):
        return None

    # If x looks like a date/month → line chart; otherwise → bar
    first_x = str(rows[0][x_col])
    chart_type = "line" if re.search(r"\d{4}[-/]\d{2}", first_x) else "bar"

    return {"type": chart_type, "x": x_col, "y": y_col}
