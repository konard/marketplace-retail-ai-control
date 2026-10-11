"""Ozon: accruals by day, the financial report and stock.

API references (checked in October 2026), https://docs.ozon.ru/api/seller/:

- ``POST /v1/finance/accrual/by-day`` - accruals of one day, page by page;
- ``POST /v1/finance/cash-flow-statement/list`` - the financial report
  for half-month periods;
- ``POST /v4/product/info/stocks`` - stock per SKU.

To verify during requirements refinement: an accrual product has no
quantity, so one product entry is one unit (a return has a negative sale
amount); fees that are not tied to a SKU (``NON_ITEM``) are not spread
over SKUs.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import httpx

from retail_ai_control.connectors import amount, post_json

OZON_URL = "https://api-seller.ozon.ru"


class OzonClient:
    """Reads the seller's data with a Client-Id and an API key."""

    def __init__(self, http: httpx.Client, client_id: str, api_key: str) -> None:
        self.http = http
        self.headers = {"Client-Id": client_id, "Api-Key": api_key}

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        return post_json(self.http, f"{OZON_URL}{path}", body, self.headers).json()

    def accruals(self, first: date, last: date) -> list[dict[str, Any]]:
        """Return the accruals of every day in the range."""
        found: list[dict[str, Any]] = []
        day = first
        while day <= last:
            last_id = ""
            while True:
                page = self._post(
                    "/v1/finance/accrual/by-day",
                    {"date": day.isoformat(), "last_id": last_id},
                )
                found.extend(page.get("accruals", []))
                last_id = page.get("last_id") or ""
                if not last_id:
                    break
            day += timedelta(days=1)
        return found

    def payout_reports(self, first: date, last: date) -> list[tuple[date, date, float]]:
        """Return the financial reports: period and payout to the seller."""
        page = self._post(
            "/v1/finance/cash-flow-statement/list",
            {
                "date": {
                    "from": f"{first.isoformat()}T00:00:00.000Z",
                    "to": f"{last.isoformat()}T23:59:59.000Z",
                },
                "page": 1,
                "page_size": 100,
                "with_details": False,
            },
        )
        reports = []
        for flow in page.get("result", {}).get("cash_flows", []):
            payout = (
                amount(flow.get("orders_amount"))
                - abs(amount(flow.get("returns_amount")))
                - abs(amount(flow.get("commission_amount")))
                - abs(amount(flow.get("item_delivery_and_return_amount")))
            )
            period = flow["period"]
            reports.append(
                (
                    date.fromisoformat(str(period["begin"])[:10]),
                    date.fromisoformat(str(period["end"])[:10]),
                    payout,
                )
            )
        return reports

    def stocks(self) -> dict[str, int]:
        """Return the available stock (present minus reserved) per Ozon SKU."""
        totals: dict[str, int] = defaultdict(int)
        cursor = ""
        while True:
            page = self._post(
                "/v4/product/info/stocks",
                {"cursor": cursor, "filter": {"visibility": "ALL"}, "limit": 1000},
            )
            items = page.get("items", [])
            for item in items:
                for stock in item.get("stocks", []):
                    available = int(stock.get("present") or 0) - int(
                        stock.get("reserved") or 0
                    )
                    totals[str(stock["sku"])] += available
            cursor = page.get("cursor") or ""
            if not items or not cursor:
                return totals


def daily_facts(
    accruals: list[dict[str, Any]], sku_by_ozon_sku: dict[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert accruals to facts per SKU and day, and unmapped rows.

    Ozon books costs as negative amounts; the data mart keeps costs positive.
    """
    facts: dict[tuple[str, date], dict[str, Any]] = {}
    unmapped: dict[tuple[str, date], float] = defaultdict(float)

    def fact(ozon_sku: str, day: date) -> dict[str, Any]:
        return facts.setdefault(
            (sku_by_ozon_sku[ozon_sku], day),
            {"units": 0, "revenue": 0.0, "commission": 0.0, "logistics": 0.0},
        )

    for accrual in accruals:
        day = date.fromisoformat(str(accrual["date"])[:10])
        category = accrual.get("accrued_category")
        if category == "POSTING":
            for product in accrual.get("posting", {}).get("products", []):
                ozon_sku = str(product["sku"])
                commission = product.get("commission", {})
                sale = amount(commission.get("sale_amount"))
                if ozon_sku not in sku_by_ozon_sku:
                    unmapped[ozon_sku, day] += sale
                    continue
                target = fact(ozon_sku, day)
                target["units"] += (sale > 0) - (sale < 0)
                target["revenue"] += sale
                target["commission"] -= amount(commission.get("commission"))
                delivery = product.get("delivery", {})
                target["logistics"] -= amount(delivery.get("total_accrued"))
        elif category == "ITEM":
            for item in accrual.get("item_fees", {}).get("fees", []):
                ozon_sku = str(item["sku"])
                if ozon_sku in sku_by_ozon_sku:
                    fees = sum(
                        amount(fee.get("accrued")) for fee in item.get("fees", [])
                    )
                    fact(ozon_sku, day)["logistics"] -= fees
    return (
        [{"sku": sku, "day": day, **values} for (sku, day), values in facts.items()],
        [
            {"external_id": ozon_sku, "day": day, "revenue": revenue}
            for (ozon_sku, day), revenue in unmapped.items()
        ],
    )
