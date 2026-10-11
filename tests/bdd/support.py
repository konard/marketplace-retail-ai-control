"""The world of a scenario and the helpers the step definitions share.

Every scenario gets a fresh pilot: an in-memory data mart, the real
connectors over :class:`~tests.bdd.fakes.FakeNetwork` and the web app in a
``TestClient``. Steps change the world through the same entry points the
production code uses: the sync, the rules, the web forms and the webhooks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from sqlalchemy import delete, insert, select

from retail_ai_control.agent import Agent
from retail_ai_control.analysis import Analysis
from retail_ai_control.config import Config, OneCSettings
from retail_ai_control.decisions import latest_for
from retail_ai_control.mart import (
    ad_spend_daily,
    decision,
    days,
    deviation,
    make_engine,
    new_id,
    sales_daily,
)
from retail_ai_control.pilot import Pilot
from retail_ai_control.web import create_app
from retail_ai_control.web.app import USER_HEADER
from tests.bdd.fakes import (
    ANALYTICS_URL,
    BITRIX_URL,
    LLM_URL,
    ONEC_URL,
    FakeNetwork,
)

APPLICATION_TOKEN = "app-token"
METABASE_SECRET = "mb-secret"
ACTIONS = {
    "set ad share": "set_ad_share",
    "change price": "change_price",
    "restock": "restock",
}
FACTS = ("units", "revenue", "commission", "logistics", "advertising")
CONCEPT_MESSAGE = "Маржа 4,0% при плане 15,0% — 3 дня подряд"
CONCEPT_EXPLANATION = (
    "Маржа упала с 16,0% до 4,0%: доля рекламы выросла с 9,0% до 21,0% выручки."
)


def number(text: str) -> float:
    """Read a figure as the specs write it: ``−6,0%``, ``+7.8 pp``, ``14 520 ₽``."""
    cleaned = text.strip().replace("−", "-").replace(",", ".")
    for unit in ("pp", "%", "₽", " ", " "):
        cleaned = cleaned.replace(unit, "")
    return float(cleaned)


def day(text: str) -> date:
    """Read an ISO date."""
    return date.fromisoformat(text.strip())


def records(datatable: list[list[str]]) -> list[dict[str, str]]:
    """Turn a Gherkin data table into dictionaries keyed by its header."""
    header, *rows = datatable
    return [dict(zip(header, (cell.strip() for cell in row))) for row in rows]


def actions_of(datatable: list[list[str]]) -> list[dict[str, Any]]:
    """Read an ``| action | value |`` table into decision actions."""
    return [
        {"type": ACTIONS[row["action"]], "value": number(row["value"])}
        for row in records(datatable)
    ]


def text_of(soup: Any) -> str:
    """The visible text of an element with whitespace collapsed."""
    return " ".join(soup.get_text(" ").split())


@dataclass
class World:
    """Everything a scenario sets up, does and then checks."""

    net: FakeNetwork = field(default_factory=FakeNetwork)
    today: date = date(2026, 10, 12)
    config: Config = field(
        default_factory=lambda: Config(
            wb_token="t",
            wb_page_pause_seconds=0,
            ozon_client_id="c",
            ozon_api_key="k",
            onec=OneCSettings(url=ONEC_URL),
            analytics_csv=ANALYTICS_URL,
            bitrix_webhook_url=BITRIX_URL,
            bitrix_application_token=APPLICATION_TOKEN,
            metabase_secret=METABASE_SECRET,
            database_url="sqlite://",
        )
    )
    pilot: Pilot = field(init=False)
    client: TestClient = field(init=False)
    deviation_id: Optional[int] = None
    decision_id: Optional[int] = None
    response: Any = None  # the TestClient response of the last request
    page: Optional[BeautifulSoup] = None
    analysis: Optional[Analysis] = None
    sync_report: list[dict[str, Any]] = field(default_factory=list)
    digest: str = ""
    outcome: str = ""
    found: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.pilot = Pilot(
            self.config,
            httpx.MockTransport(self.net.handler),
            lambda: self.today,
            make_engine(self.config.database_url),
        )
        self.client = TestClient(create_app(self.pilot), follow_redirects=False)

    # Users act through the web app, like in production
    def get(self, url: str, user: Optional[int] = None) -> BeautifulSoup:
        """Open a page as a user and keep it for the checks."""
        headers = {USER_HEADER: str(user)} if user is not None else {}
        self.response = self.client.get(url, headers=headers)
        self.page = BeautifulSoup(self.response.text, "html.parser")
        return self.page

    def post(self, url: str, user: int, form: dict[str, str]) -> Any:
        """Submit a form as a user; a re-rendered page is kept for the checks."""
        self.response = self.client.post(
            url, data=form, headers={USER_HEADER: str(user)}
        )
        self.page = BeautifulSoup(self.response.text, "html.parser")
        return self.response

    def enable_ai(self) -> None:
        """Point the pilot at the fake OpenAI-compatible endpoint."""
        self.config.llm.base_url = LLM_URL
        self.config.llm.model = "test"
        self.pilot.agent = Agent(self.pilot)

    # The deviation and the decision a scenario talks about
    def current_deviation(self) -> int:
        """The deviation of the scenario: the one named last or the largest open."""
        if self.deviation_id is not None:
            return self.deviation_id
        with self.pilot.engine.connect() as conn:
            found = conn.execute(
                select(deviation.c.id)
                .where(deviation.c.status == "open")
                .order_by(deviation.c.impact.desc(), deviation.c.id)
            ).scalar()
        assert found is not None, "no open deviation"
        self.deviation_id = int(found)
        return self.deviation_id

    def current_decision(self) -> int:
        """The decision of the scenario: the one named last or the newest one."""
        if self.decision_id is not None:
            return self.decision_id
        with self.pilot.engine.connect() as conn:
            row = latest_for(conn, self.current_deviation())
        assert row is not None, "no decision"
        self.decision_id = int(row["id"])
        return self.decision_id

    def decision_row(self) -> dict[str, Any]:
        """The current decision as stored."""
        with self.pilot.engine.connect() as conn:
            row = (
                conn.execute(
                    select(decision).where(decision.c.id == self.current_decision())
                )
                .mappings()
                .one()
            )
        return dict(row)

    def deviation_row(self) -> dict[str, Any]:
        """The current deviation as stored."""
        with self.pilot.engine.connect() as conn:
            row = (
                conn.execute(
                    select(deviation).where(deviation.c.id == self.current_deviation())
                )
                .mappings()
                .one()
            )
        return dict(row)


def put_day(
    conn: Any,
    channel: str,
    sku: str,
    on_day: date,
    values: dict[str, float],
) -> None:
    """Store the facts of one SKU-day, replacing earlier ones."""
    for table in (sales_daily, ad_spend_daily):
        conn.execute(
            delete(table).where(
                table.c.channel == channel, table.c.sku == sku, table.c.day == on_day
            )
        )
    conn.execute(
        insert(sales_daily).values(
            channel=channel,
            sku=sku,
            day=on_day,
            units=int(values.get("units", 0)),
            revenue=values.get("revenue", 0.0),
            commission=values.get("commission", 0.0),
            logistics=values.get("logistics", 0.0),
        )
    )
    if values.get("advertising"):
        conn.execute(
            insert(ad_spend_daily).values(
                channel=channel, sku=sku, day=on_day, spend=values["advertising"]
            )
        )


def add_deviation(conn: Any, **values: Any) -> int:
    """Store a deviation; the defaults are the concept's example."""
    row = {
        "rule": "margin below plan",
        "sku": "SKU-1001",
        "channel": "ozon",
        "window_start": date(2026, 10, 9),
        "window_end": date(2026, 10, 11),
        "message": CONCEPT_MESSAGE,
        "impact": 14520.0,
        "status": "open",
        "detected_on": date(2026, 10, 12),
    }
    row.update(values)
    return new_id(conn.execute(insert(deviation).values(**row)))


def add_decision(conn: Any, deviation_id: int, **values: Any) -> int:
    """Store a decision; the defaults are a fresh proposal with no actions."""
    row = {
        "deviation_id": deviation_id,
        "status": "proposed",
        "proposed_actions": [],
        "actions": [],
        "explanation": CONCEPT_EXPLANATION,
        "figures": {},
        "target_pct": 12.0,
        "guardrail_pct": 10.0,
        "created_on": date(2026, 10, 12),
    }
    row.update(values)
    return new_id(conn.execute(insert(decision).values(**row)))


def load_sales(conn: Any, rows: list[dict[str, str]]) -> None:
    """Store a ``| from | to | sku | channel | units | ... |`` table, per day."""
    for row in rows:
        values = daily_values(row)
        for on_day in days(day(row["from"]), day(row["to"])):
            put_day(conn, row["channel"], row["sku"], on_day, values)


def daily_values(row: dict[str, str]) -> dict[str, float]:
    """The daily figures of a sales table row."""
    return {name: number(row[name]) for name in FACTS}
