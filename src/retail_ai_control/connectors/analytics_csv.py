"""Advertising spend from the analytics service (MPStats, Moneyplace, ...).

The pilot takes a CSV export with the columns ``date,channel,sku,spend``
from a URL or a file; the exact export format of the chosen service is
mapped during requirements refinement.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path
from typing import Any

import httpx


def read_spend(
    http: httpx.Client, source: str, first: date, last: date
) -> list[dict[str, Any]]:
    """Return the spend rows in the date range from a URL or a CSV file."""
    if source.startswith(("http://", "https://")):
        response = http.get(source)
        response.raise_for_status()
        content = response.text
    else:
        content = Path(source).read_text(encoding="utf-8")
    rows = []
    for row in csv.DictReader(io.StringIO(content)):
        day = date.fromisoformat(row["date"])
        if first <= day <= last:
            rows.append(
                {
                    "channel": row["channel"],
                    "sku": row["sku"],
                    "day": day,
                    "spend": float(row["spend"]),
                }
            )
    return rows
