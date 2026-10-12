"""The pilot: settings, clients and the steps of the management loop.

One :class:`Pilot` object is shared by the CLI, the scheduler and the web
app. Every external system is reached through ``self.http``; tests pass an
``httpx.MockTransport`` and run the same code.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any, Optional

import httpx
from sqlalchemy import Engine, select

from retail_ai_control import (
    analysis,
    decisions,
    digest,
    execution,
    followup,
    metrics,
    reconcile,
    rules,
    sync,
)
from retail_ai_control.agent import UNAVAILABLE, Agent, Answer
from retail_ai_control.config import Config
from retail_ai_control.connectors.bitrix24 import Bitrix24Client
from retail_ai_control.connectors.onec import OneCClient
from retail_ai_control.connectors.ozon import OzonClient
from retail_ai_control.connectors.wildberries import WildberriesClient
from retail_ai_control.mart import create_schema, decision, deviation, make_engine

logger = logging.getLogger(__name__)
HTTP_TIMEOUT_SECONDS = 60.0


class Pilot:
    """Wires the settings to the data mart and the external systems."""

    def __init__(
        self,
        config: Config,
        transport: Optional[httpx.BaseTransport] = None,
        today: Optional[Callable[[], date]] = None,
        engine: Optional[Engine] = None,
    ) -> None:
        self.config = config
        self.http = httpx.Client(transport=transport, timeout=HTTP_TIMEOUT_SECONDS)
        self.engine = engine or make_engine(config.database_url)
        create_schema(self.engine)
        self.today: Callable[[], date] = today or date.today
        self.log: list[str] = []
        self.wb = (
            WildberriesClient(self.http, config.wb_token, config.wb_page_pause_seconds)
            if config.wb_token
            else None
        )
        self.ozon = (
            OzonClient(self.http, config.ozon_client_id, config.ozon_api_key)
            if config.ozon_client_id
            else None
        )
        self.onec = OneCClient(self.http, config.onec) if config.onec.url else None
        self.bitrix = (
            Bitrix24Client(self.http, config.bitrix_webhook_url)
            if config.bitrix_webhook_url
            else None
        )
        self.agent = Agent(self) if config.llm.base_url else None

    def note(self, message: str) -> None:
        """Keep a message for the operator and write it to the log."""
        self.log.append(message)
        logger.warning(message)

    # The loop, step by step
    def sync(self, first: date, last: date) -> list[dict[str, Any]]:
        """Load the sources for the range."""
        return sync.sync(self, first, last)

    def reconcile(self, first: date, last: date) -> list[dict[str, Any]]:
        """Compare the data mart with the marketplace financial reports."""
        return reconcile.reconcile(self, first, last)

    def run_rules(self) -> list[int]:
        """Find new deviations."""
        return rules.run_rules(self)

    def analyse(
        self,
        deviation_id: int,
        window: Optional[tuple[date, date]] = None,
        parent_id: Optional[int] = None,
        target_pct: Optional[float] = None,
    ) -> analysis.Analysis:
        """Explain a deviation and store the proposal."""
        return analysis.analyse(self, deviation_id, window, parent_id, target_pct)

    def analyse_open(self) -> list[analysis.Analysis]:
        """Analyse open deviations that have no proposal or decision in work."""
        with self.engine.connect() as conn:
            busy = select(decision.c.deviation_id).where(
                decision.c.status.in_(decisions.ACTIVE)
            )
            pending: list[int] = list(
                conn.execute(
                    select(deviation.c.id).where(
                        deviation.c.status == "open", deviation.c.id.not_in(busy)
                    )
                )
                .scalars()
                .all()
            )
        return [self.analyse(deviation_id) for deviation_id in pending]

    def approve(
        self,
        decision_id: int,
        user_id: int,
        actions: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """Approve a proposal; the task is created in Bitrix24."""
        return decisions.approve(self, decision_id, user_id, actions)

    def reject(self, decision_id: int, user_id: int, reason: str) -> dict[str, Any]:
        """Reject a proposal with a reason."""
        return decisions.reject(self, decision_id, user_id, reason)

    def retry_tasks(self) -> int:
        """Create the tasks that failed because Bitrix24 was unavailable."""
        return execution.retry_tasks(self)

    def handle_task_event(self, form: dict[str, str]) -> int:
        """Process a Bitrix24 task event; return the HTTP status."""
        return execution.handle_task_event(self, form)

    def run_followups(self) -> list[dict[str, Any]]:
        """Measure the decisions whose follow-up is due."""
        return followup.run_followups(self)

    def digest(self) -> str:
        """Build the morning digest."""
        return digest.build_digest(self)

    def send_digest(self) -> str:
        """Post the morning digest to Bitrix24."""
        return digest.send_digest(self)

    def ask(self, question: str) -> Answer:
        """Answer a question in plain language."""
        if self.agent is None:
            return Answer(
                UNAVAILABLE,
                [("Дашборд", self.config.dashboard_url or self.config.web_url)],
                "",
            )
        return self.agent.answer(question)

    def team(self) -> list[dict[str, Any]]:
        """Task execution per person."""
        return metrics.team_performance(self)

    def scorecard(self) -> metrics.Scorecard:
        """The pilot criteria and the verdict."""
        return metrics.scorecard(self)

    def morning(self) -> str:
        """The daily run: data, checks, follow-ups, deviations, proposals, digest."""
        today = self.today()
        first = today - timedelta(self.config.sync_lookback_days)
        last = today - timedelta(1)
        self.sync(first, last)
        self.reconcile(first, last)
        self.run_followups()
        self.run_rules()
        self.analyse_open()
        self.retry_tasks()
        return self.send_digest()
