"""One fake network for every external system of the pilot.

The production clients run unchanged against an ``httpx.MockTransport``:
Wildberries, Ozon, 1C OData, the analytics CSV export, the Bitrix24 webhook
and an OpenAI-compatible chat completions endpoint. The answers follow the
shapes documented in ``src/retail_ai_control/connectors``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

import httpx

WB_FINANCE = "finance-api.wildberries.ru"
WB_ANALYTICS = "seller-analytics-api.wildberries.ru"
OZON = "api-seller.ozon.ru"
ONEC = "1c.test"
ANALYTICS = "analytics.test"
BITRIX = "b24.test"
LLM = "llm.test"

ONEC_URL = f"https://{ONEC}/odata/standard.odata"
ANALYTICS_URL = f"https://{ANALYTICS}/export.csv"
BITRIX_URL = f"https://{BITRIX}/rest/1/x"
LLM_URL = f"https://{LLM}/v1"
MATCH_SALES = "match loaded sales"


@dataclass
class Reply:
    """One scripted answer of the AI model: a tool call or the final text."""

    content: str = ""
    tool: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


def _split(total: float, units: int) -> list[float]:
    """Split an amount over units in kopecks, so the parts add up exactly."""
    if units <= 0:
        return []
    part = round(total / units, 2)
    return [part] * (units - 1) + [round(total - part * (units - 1), 2)]


def _in(day: str, first: str, last: str) -> bool:
    return first[:10] <= day[:10] <= last[:10]


@dataclass
class FakeNetwork:
    """The state of every fake system; ``handler`` is the transport."""

    onec_products: list[dict[str, Any]] = field(default_factory=list)
    onec_costs: list[dict[str, Any]] = field(default_factory=list)
    wb_rows: list[dict[str, Any]] = field(default_factory=list)
    wb_stock: dict[str, int] = field(default_factory=dict)
    ozon_accruals: list[dict[str, Any]] = field(default_factory=list)
    ozon_stock: dict[str, int] = field(default_factory=dict)
    ozon_down: bool = False
    analytics_rows: list[dict[str, Any]] = field(default_factory=list)
    # (channel, sku, day) -> units, revenue, commission, logistics, advertising
    daily: dict[tuple[str, str, date], dict[str, float]] = field(default_factory=dict)
    # channel -> explicit reports [(first, last, payout)] or MATCH_SALES
    reports: dict[str, Any] = field(default_factory=lambda: {"wb": [], "ozon": []})
    bitrix_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    bitrix_fail: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    next_task: int = 501
    llm_replies: list[Reply] = field(default_factory=list)
    llm_requests: list[dict[str, Any]] = field(default_factory=list)
    llm_down: bool = False

    # Test helpers
    def product(self, sku: str) -> dict[str, Any]:
        """The 1C catalog row of a SKU."""
        return next(row for row in self.onec_products if row["Артикул"] == sku)

    def add_daily(
        self, channel: str, sku: str, first: date, last: date, values: dict[str, float]
    ) -> None:
        """Report the same daily figures for every day of the range."""
        day = first
        while day <= last:
            self.daily[channel, sku, day] = dict(values)
            day += timedelta(1)

    def calls(self, method: str) -> list[dict[str, Any]]:
        """The bodies of the Bitrix24 calls of one method."""
        return [body for name, body in self.bitrix_calls if name == method]

    # Data the marketplaces serve
    def _wb_detail(self) -> list[dict[str, Any]]:
        rows = list(self.wb_rows)
        for (channel, sku, day), values in sorted(self.daily.items()):
            if channel != "wb" or not values["units"]:
                continue
            revenue = values["revenue"]
            rows.append(
                {
                    "rrDate": day.isoformat(),
                    "nmId": int(self.product(sku)["АртикулWB"]),
                    "docTypeName": "Продажа",
                    "quantity": int(values["units"]),
                    "retailAmount": revenue,
                    "forPay": round(revenue - values["commission"], 2),
                    "deliveryService": values["logistics"],
                }
            )
        return rows

    def _ozon_day(self, day: str) -> list[dict[str, Any]]:
        found = [row for row in self.ozon_accruals if row["date"] == day]
        for (channel, sku, when), values in sorted(self.daily.items()):
            if channel != "ozon" or when.isoformat() != day:
                continue
            units = int(values["units"])
            products = [
                {
                    "sku": int(self.product(sku)["SKUOzon"]),
                    "commission": {"sale_amount": sale, "commission": -commission},
                    "delivery": {"total_accrued": -delivery},
                }
                for sale, commission, delivery in zip(
                    _split(values["revenue"], units),
                    _split(values["commission"], units),
                    _split(values["logistics"], units),
                )
            ]
            found.append(
                {
                    "date": day,
                    "accrued_category": "POSTING",
                    "posting": {"products": products},
                }
            )
        return found

    def _analytics_csv(self) -> str:
        lines = ["date,channel,sku,spend"]
        lines += [
            f"{row['date']},{row['channel']},{row['sku']},{row['spend']}"
            for row in self.analytics_rows
        ]
        lines += [
            f"{day.isoformat()},{channel},{sku},{values['advertising']}"
            for (channel, sku, day), values in sorted(self.daily.items())
            if values["advertising"]
        ]
        return "\n".join(lines) + "\n"

    def _wb_reports(self, first: str, last: str) -> list[dict[str, Any]]:
        mode = self.reports["wb"]
        if mode == MATCH_SALES:
            rows = [r for r in self._wb_detail() if _in(r["rrDate"], first, last)]
            sign = {"Продажа": 1, "Возврат": -1}
            return [
                {
                    "dateFrom": first,
                    "dateTo": last,
                    "forPaySum": sum(
                        sign[r["docTypeName"]] * r["forPay"] for r in rows
                    ),
                    "deliveryServiceSum": sum(r["deliveryService"] for r in rows),
                }
            ]
        return [
            {
                "dateFrom": begin.isoformat(),
                "dateTo": end.isoformat(),
                "forPaySum": payout,
                "deliveryServiceSum": 0,
            }
            for begin, end, payout in mode
        ]

    def _ozon_reports(self, first: str, last: str) -> list[dict[str, Any]]:
        mode = self.reports["ozon"]
        if mode == MATCH_SALES:
            sales = commission = delivery = 0.0
            day = date.fromisoformat(first[:10])
            while day <= date.fromisoformat(last[:10]):
                for accrual in self._ozon_day(day.isoformat()):
                    for item in accrual["posting"]["products"]:
                        sales += item["commission"]["sale_amount"]
                        commission += item["commission"]["commission"]
                        delivery += item["delivery"]["total_accrued"]
                day += timedelta(1)
            flows = [(first[:10], last[:10], sales, commission, delivery)]
        else:
            flows = [
                (begin.isoformat(), end.isoformat(), payout, 0.0, 0.0)
                for begin, end, payout in mode
            ]
        return [
            {
                "period": {"begin": f"{begin}T00:00:00Z", "end": f"{end}T23:59:59Z"},
                "orders_amount": orders,
                "returns_amount": 0,
                "commission_amount": commission,
                "item_delivery_and_return_amount": delivery,
            }
            for begin, end, orders, commission, delivery in flows
        ]

    # The transport
    def handler(self, request: httpx.Request) -> httpx.Response:
        """Answer a request like the real system would."""
        host, path = request.url.host, request.url.path
        body = json.loads(request.content) if request.content else {}
        if host == WB_FINANCE and path.endswith("/sales-reports/detailed"):
            rows = [
                row
                for row in self._wb_detail()
                if _in(row["rrDate"], body["dateFrom"], body["dateTo"])
            ]
            return httpx.Response(200, json=rows) if rows else httpx.Response(204)
        if host == WB_FINANCE and path.endswith("/sales-reports/list"):
            return httpx.Response(
                200, json=self._wb_reports(body["dateFrom"], body["dateTo"])
            )
        if host == WB_ANALYTICS:
            items = [
                {"nmId": int(nm), "quantity": q} for nm, q in self.wb_stock.items()
            ]
            return httpx.Response(200, json={"data": {"items": items}})
        if host == OZON:
            return self._ozon(path, body)
        if host == ONEC:
            entity = path.rsplit("/", 1)[-1]
            rows = (
                self.onec_products if entity.startswith("Catalog") else self.onec_costs
            )
            return httpx.Response(200, json={"value": rows})
        if host == ANALYTICS:
            return httpx.Response(200, text=self._analytics_csv())
        if host == BITRIX:
            return self._bitrix(path.rsplit("/", 1)[-1].removesuffix(".json"), body)
        if host == LLM:
            return self._llm(body)
        return httpx.Response(404, json={"error": f"unexpected {request.url}"})

    def _ozon(self, path: str, body: dict[str, Any]) -> httpx.Response:
        if self.ozon_down:
            return httpx.Response(503, json={"message": "Service Unavailable"})
        if path == "/v1/finance/accrual/by-day":
            return httpx.Response(
                200, json={"accruals": self._ozon_day(body["date"]), "last_id": ""}
            )
        if path == "/v1/finance/cash-flow-statement/list":
            flows = self._ozon_reports(body["date"]["from"], body["date"]["to"])
            return httpx.Response(200, json={"result": {"cash_flows": flows}})
        if path == "/v4/product/info/stocks":
            stocks = [
                {"sku": int(sku), "present": q, "reserved": 0}
                for sku, q in self.ozon_stock.items()
            ]
            return httpx.Response(
                200, json={"items": [{"stocks": stocks}], "cursor": ""}
            )
        return httpx.Response(404)

    def _bitrix(self, method: str, body: dict[str, Any]) -> httpx.Response:
        if self.bitrix_fail[method] > 0:
            self.bitrix_fail[method] -= 1
            return httpx.Response(503, json={"error": "SERVICE_UNAVAILABLE"})
        self.bitrix_calls.append((method, body))
        result: Any = True
        if method == "tasks.task.add":
            task_id = str(self.next_task)
            self.next_task += 1
            self.tasks[task_id] = {"id": task_id, "status": "2", "closedDate": None}
            result = {"task": {"id": task_id}}
        elif method == "tasks.task.get":
            result = {"task": self.tasks[str(body["taskId"])]}
        return httpx.Response(200, json={"result": result})

    def _llm(self, body: dict[str, Any]) -> httpx.Response:
        self.llm_requests.append(body)
        if self.llm_down or not self.llm_replies:
            return httpx.Response(503, json={"error": {"message": "unavailable"}})
        reply = self.llm_replies.pop(0)
        message: dict[str, Any] = {"role": "assistant", "content": reply.content}
        finish = "stop"
        if reply.tool:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call_{len(self.llm_requests)}",
                        "type": "function",
                        "function": {
                            "name": reply.tool,
                            "arguments": json.dumps(reply.arguments),
                        },
                    }
                ],
            }
            finish = "tool_calls"
        return httpx.Response(
            200,
            json={
                "id": f"chatcmpl-{len(self.llm_requests)}",
                "object": "chat.completion",
                "created": 0,
                "model": body.get("model", "test"),
                "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            },
        )

    def tool_results(self, name: str) -> list[str]:
        """The tool answers the agent sent back to the model for a tool."""
        ids: dict[str, str] = {}
        found: list[str] = []
        for request in self.llm_requests:
            for message in request.get("messages", []):
                for call in message.get("tool_calls") or []:
                    ids[call["id"]] = call["function"]["name"]
        last: Optional[dict[str, Any]] = (
            self.llm_requests[-1] if self.llm_requests else None
        )
        for message in (last or {}).get("messages", []):
            if (
                message.get("role") == "tool"
                and ids.get(message["tool_call_id"]) == name
            ):
                found.append(message["content"])
        return found
