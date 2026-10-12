"""Wildberries: sales report details, financial reports and stock.

API references (checked in October 2026):

- https://dev.wildberries.ru/docs/openapi/financial-reports-and-accounting
  ``POST /api/finance/v1/sales-reports/detailed`` and ``.../list``;
- https://dev.wildberries.ru/docs/openapi/analytics
  ``POST /api/analytics/v1/stocks-report/wb-warehouses``.

The sales report allows one request a minute, so the client waits between
pages (``page_pause_seconds``).
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import date
from typing import Any, Callable

import httpx

from retail_ai_control.connectors import amount, post_json

FINANCE_URL = "https://finance-api.wildberries.ru"
ANALYTICS_URL = "https://seller-analytics-api.wildberries.ru"
PAGE_LIMIT = 100000
SALE = "Продажа"
RETURN = "Возврат"


class WildberriesClient:
    """Reads the seller's data with a token of the Finance and Analytics scopes."""

    def __init__(
        self,
        http: httpx.Client,
        token: str,
        page_pause_seconds: float = 61.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.http = http
        self.headers = {"Authorization": token}
        self.page_pause_seconds = page_pause_seconds
        self.sleep = sleep

    def sales_rows(self, first: date, last: date) -> list[dict[str, Any]]:
        """Return the rows of the daily sales reports, page by page."""
        rows: list[dict[str, Any]] = []
        rrd_id = 0
        while True:
            response = post_json(
                self.http,
                f"{FINANCE_URL}/api/finance/v1/sales-reports/detailed",
                {
                    "dateFrom": first.isoformat(),
                    "dateTo": last.isoformat(),
                    "limit": PAGE_LIMIT,
                    "rrdId": rrd_id,
                    "period": "daily",
                },
                self.headers,
            )
            page = (
                []
                if response.status_code == httpx.codes.NO_CONTENT
                else response.json()
            )
            rows.extend(page)
            if len(page) < PAGE_LIMIT:
                return rows
            rrd_id = int(page[-1]["rrdId"])
            self.sleep(self.page_pause_seconds)

    def payout_reports(self, first: date, last: date) -> list[tuple[date, date, float]]:
        """Return the financial reports: period and payout to the seller."""
        response = post_json(
            self.http,
            f"{FINANCE_URL}/api/finance/v1/sales-reports/list",
            {
                "dateFrom": first.isoformat(),
                "dateTo": last.isoformat(),
                "period": "daily",
                "limit": 1000,
            },
            self.headers,
        )
        reports = (
            [] if response.status_code == httpx.codes.NO_CONTENT else response.json()
        )
        return [
            (
                date.fromisoformat(str(report["dateFrom"])[:10]),
                date.fromisoformat(str(report["dateTo"])[:10]),
                amount(report.get("forPaySum"))
                - amount(report.get("deliveryServiceSum")),
            )
            for report in reports
        ]

    def stocks(self, nm_ids: list[str]) -> dict[str, int]:
        """Return the current stock per nmId over all WB warehouses."""
        response = post_json(
            self.http,
            f"{ANALYTICS_URL}/api/analytics/v1/stocks-report/wb-warehouses",
            {
                "nmIds": [int(n) for n in nm_ids],
                "chrtIds": [],
                "limit": 250000,
                "offset": 0,
            },
            self.headers,
        )
        totals: dict[str, int] = defaultdict(int)
        if response.status_code == httpx.codes.NO_CONTENT:
            return totals
        for item in response.json().get("data", {}).get("items", []):
            totals[str(item["nmId"])] += int(item.get("quantity") or 0)
        return totals


def daily_facts(
    rows: list[dict[str, Any]], sku_by_nm_id: dict[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert report rows to facts per SKU and day, and unmapped rows.

    A sale adds units, revenue and the marketplace fee (retail price minus
    the payout to the seller); a return subtracts them. Delivery is a cost
    for every row type.
    """
    facts: dict[tuple[str, date], dict[str, Any]] = {}
    unmapped: dict[tuple[str, date], float] = defaultdict(float)
    for row in rows:
        day = date.fromisoformat(str(row["rrDate"])[:10])
        nm_id = str(row["nmId"])
        sign = {SALE: 1, RETURN: -1}.get(str(row.get("docTypeName")), 0)
        revenue = amount(row.get("retailAmount"))
        if nm_id not in sku_by_nm_id:
            unmapped[nm_id, day] += sign * revenue
            continue
        fact = facts.setdefault(
            (sku_by_nm_id[nm_id], day),
            {"units": 0, "revenue": 0.0, "commission": 0.0, "logistics": 0.0},
        )
        fact["units"] += sign * int(row.get("quantity") or 0)
        fact["revenue"] += sign * revenue
        fact["commission"] += sign * (revenue - amount(row.get("forPay")))
        fact["logistics"] += amount(row.get("deliveryService"))
    return (
        [{"sku": sku, "day": day, **fact} for (sku, day), fact in facts.items()],
        [
            {"external_id": nm_id, "day": day, "revenue": revenue}
            for (nm_id, day), revenue in unmapped.items()
        ],
    )
