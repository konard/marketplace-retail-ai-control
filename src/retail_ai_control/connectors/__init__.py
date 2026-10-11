"""Clients of the external systems. Each one is a thin layer over ``httpx``.

The clients only call the documented APIs and convert the answers to daily
facts. Tests replace the network with ``httpx.MockTransport``; the clients
run unchanged.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx


def post_json(
    http: httpx.Client,
    url: str,
    body: Any,
    headers: Optional[dict[str, str]] = None,
) -> httpx.Response:
    """POST a JSON body; raise ``httpx.HTTPStatusError`` on 4xx and 5xx."""
    response = http.post(url, json=body, headers=headers or {})
    response.raise_for_status()
    return response


def amount(money: Any) -> float:
    """Read a money value: a number, a string or ``{"amount": ...}``."""
    if isinstance(money, dict):
        money = money.get("amount")
    return float(money or 0)
