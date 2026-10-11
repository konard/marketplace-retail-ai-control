"""Measure the effect of an executed decision after the follow-up period.

The effect is a difference-in-differences: the change of the margin rate of
the SKU after the change date minus the change for a control group (SKUs on
the same channel without decisions). The incremental margin is the effect
times the revenue of the period after the change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Optional

import httpx
from sqlalchemy import select, update
from sqlalchemy.engine import Connection

from retail_ai_control import queries
from retail_ai_control.fmt import pct, signed_pct
from retail_ai_control.mart import decision, deviation, log_event, sales_daily

if TYPE_CHECKING:
    from retail_ai_control.pilot import Pilot

ACHIEVED = "achieved"
PARTIAL = "partially achieved"
NOT_ACHIEVED = "not achieved"
VERDICTS = {
    ACHIEVED: "цель достигнута",
    PARTIAL: "цель достигнута частично",
    NOT_ACHIEVED: "цель не достигнута",
}


@dataclass
class Window:
    """Totals of a group of SKUs for a period."""

    days: int
    units: float
    revenue: float
    margin: float
    margin_pct: Optional[float]

    @property
    def units_per_day(self) -> float:
        """Units sold per calendar day of the period."""
        return round(self.units / self.days, 1) if self.days else 0.0


@dataclass
class Result:
    """The comparison and the outcome of one decision."""

    before: Window
    after: Window
    control_before: Optional[Window]
    control_after: Optional[Window]
    sales_change_pct: float
    effect_pp: float
    incremental_margin: float
    outcome: str
    text: str


def classify(
    margin_pct: float,
    sales_change_pct: float,
    effect_pp: float,
    target_pct: float,
    guardrail_pct: float,
) -> str:
    """No effect: not achieved; target and guardrail met: achieved; else partial."""
    if effect_pp <= 0:
        return NOT_ACHIEVED
    if margin_pct >= target_pct and sales_change_pct >= -guardrail_pct:
        return ACHIEVED
    return PARTIAL


def result_text(
    margin_pct: float, before_pct: float, sales_change_pct: float, outcome: str
) -> str:
    """``Маржа 11,8% (было 4,0%), продажи −6,0%: цель достигнута частично``."""
    return (
        f"Маржа {pct(margin_pct)} (было {pct(before_pct)}), "
        f"продажи {signed_pct(sales_change_pct)}: {VERDICTS[outcome]}"
    )


def _window(
    conn: Connection, channel: str, skus: list[str], first: date, last: date
) -> Window:
    row = queries.run(
        conn, "window_totals", channel=channel, skus=skus, date_from=first, date_to=last
    ).rows[0]
    return Window(
        (last - first).days + 1,
        float(row["units"] or 0),
        float(row["revenue"] or 0),
        float(row["margin"] or 0),
        row["margin_pct"],
    )


def _control_skus(conn: Connection, channel: str, sku: str) -> list[str]:
    with_decisions = select(deviation.c.sku).where(
        deviation.c.channel == channel,
        deviation.c.id.in_(select(decision.c.deviation_id)),
    )
    rows = conn.execute(
        select(sales_daily.c.sku)
        .where(
            sales_daily.c.channel == channel,
            sales_daily.c.sku != sku,
            sales_daily.c.sku.not_in(with_decisions),
        )
        .distinct()
    )
    return sorted(rows.scalars())


def evaluate(conn: Connection, row: dict[str, Any], dev: dict[str, Any]) -> Result:
    """Compare the period before the change with the period after it."""
    completed = row["completed_on"]
    after_last = row["followup_due"] - timedelta(1)
    before_first = min(dev["window_start"], completed - timedelta(1))
    channel, sku = dev["channel"], dev["sku"]
    before = _window(conn, channel, [sku], before_first, completed - timedelta(1))
    after = _window(conn, channel, [sku], completed, after_last)
    control = _control_skus(conn, channel, sku)
    control_before = control_after = None
    control_change = 0.0
    if control:
        control_before = _window(
            conn, channel, control, before_first, completed - timedelta(1)
        )
        control_after = _window(conn, channel, control, completed, after_last)
        if (
            control_before.margin_pct is not None
            and control_after.margin_pct is not None
        ):
            control_change = control_after.margin_pct - control_before.margin_pct
    before_pct, after_pct = before.margin_pct or 0.0, after.margin_pct or 0.0
    effect = round(after_pct - before_pct - control_change, 1)
    sales = before.units_per_day
    change = round(100 * (after.units_per_day - sales) / sales, 1) if sales else 0.0
    outcome = classify(
        after_pct, change, effect, row["target_pct"], row["guardrail_pct"]
    )
    return Result(
        before,
        after,
        control_before,
        control_after,
        change,
        effect,
        round(effect / 100 * after.revenue, 2),
        outcome,
        result_text(after_pct, before_pct, change, outcome),
    )


def run_followups(pilot: Pilot) -> list[dict[str, Any]]:
    """Evaluate every done decision whose follow-up is due and decide the next step."""
    today = pilot.today()
    with pilot.engine.connect() as conn:
        due = [
            dict(row)
            for row in conn.execute(
                select(decision).where(
                    decision.c.status == "done", decision.c.followup_due <= today
                )
            ).mappings()
        ]
    done = []
    for row in due:
        with pilot.engine.connect() as conn:
            dev = dict(
                conn.execute(
                    select(deviation).where(deviation.c.id == row["deviation_id"])
                )
                .mappings()
                .one()
            )
            result = evaluate(conn, row, dev)
        if pilot.bitrix is not None and row["task_id"]:
            try:
                pilot.bitrix.comment(row["task_id"], result.text)
            except httpx.HTTPError as error:
                pilot.note(
                    f"result of decision {row['id']} not posted, will retry: {error}"
                )
                continue
        _store(pilot, row, dev, result)
        done.append(
            {"decision_id": row["id"], "outcome": result.outcome, "text": result.text}
        )
    return done


def _store(
    pilot: Pilot, row: dict[str, Any], dev: dict[str, Any], result: Result
) -> None:
    today = pilot.today()
    achieved = result.outcome == ACHIEVED
    with pilot.engine.begin() as conn:
        conn.execute(
            update(decision)
            .where(decision.c.id == row["id"])
            .values(
                status="closed" if achieved else "evaluated",
                outcome=result.outcome,
                result_text=result.text,
                incremental_margin=result.incremental_margin,
                evaluated_on=today,
            )
        )
        log_event(conn, row["id"], "evaluated", today, note=result.text)
        if achieved:
            log_event(conn, row["id"], "closed", today)
        conn.execute(
            update(deviation)
            .where(deviation.c.id == dev["id"])
            .values(status="closed" if achieved else "open")
        )
    if not achieved:
        after = (row["completed_on"], row["followup_due"] - timedelta(1))
        pilot.analyse(
            dev["id"], window=after, parent_id=row["id"], target_pct=row["target_pct"]
        )
