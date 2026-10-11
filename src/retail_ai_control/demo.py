"""The example from the concept as demo data.

SKU-1001 sells on Ozon and Wildberries. For the last 3 days the advertising
share on Ozon rose from 9% to 21% of revenue, so the margin fell from 16% to
4% at a plan of 15%; the Wildberries stock lasts 8 days at a norm of 14.
``retail-ai-control demo`` loads it into an empty data mart together with
four weeks of decisions that the loop has already executed and measured, so
the journal, the team page and the scorecard have something to show.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Connection, insert

from retail_ai_control.analysis import RULES_LABEL
from retail_ai_control.decisions import APPROVED, PROPOSED
from retail_ai_control.execution import DONE, IN_PROGRESS
from retail_ai_control.followup import ACHIEVED, NOT_ACHIEVED, result_text
from retail_ai_control.mart import (
    ad_spend_daily,
    days,
    decision,
    deviation,
    log_event,
    new_id,
    product,
    put_cost,
    reconciliation,
    replace_channel_facts,
    sales_daily,
    stock_daily,
)
from retail_ai_control.reconcile import OK
from retail_ai_control.rules import ADVERTISING, MARGIN, SALES_DROP, STOCKOUT

if TYPE_CHECKING:
    from retail_ai_control.pilot import Pilot

SKU = "SKU-1001"
BASELINE = (7, 3960.00)
RECENT = (3, 9240.00)
STOCK_WINDOW = 14
# Past decisions: SKU, channel, rule, message, action, days ago, task title,
# and the measured result (margin after and before, sales change, outcome and
# incremental margin) or None while the task is open.
HISTORY: list[tuple[Any, ...]] = [
    ("SKU-1002", "wb", MARGIN, "Маржа 12,0% при плане 20,0% — 3 дня подряд",
     {"type": "change_price", "value": 3.0}, 26, "Поднять цену SKU-1002 на WB на 3%",
     (21.0, 12.0, -4.0, ACHIEVED, 6400.0)),
    ("SKU-1003", "ozon", ADVERTISING, "Доля рекламы 19,0% при лимите 15,0%",
     {"type": "set_ad_share", "value": 9.0}, 19, "Снизить долю рекламы SKU-1003 на Ozon до 9%",
     (11.0, 12.0, -18.0, NOT_ACHIEVED, -1200.0)),
    ("SKU-1004", "wb", STOCKOUT, "Остатка хватит на 6 дн. при норме 14 дн.",
     {"type": "restock", "value": 300.0}, 12, "Заказать поставку SKU-1004 на WB: 300 шт.",
     (18.0, 17.5, 6.0, ACHIEVED, 2900.0)),
    ("SKU-1005", "ozon", SALES_DROP, "Продажи упали на 32% к прошлой неделе",
     {"type": "change_price", "value": -5.0}, 5, "Снизить цену SKU-1005 на Ozon на 5%",
     None),
]  # fmt: skip
TASK_DAYS = 2
FOLLOWUP_DAYS = 7
TARGET_PCT = 15.0
# What the loop proposes after a decision missed its goal.
RETRY = (
    {"type": "set_ad_share", "value": 12.0},
    "Доля рекламы снизилась до 9,0%, но продажи упали на 18%, и маржа не выросла. "
    "Вернуть долю рекламы к 12,0% и измерить эффект ещё раз.",
)
RETRY_IMPACT = 3600.0


def load_demo(pilot: Pilot) -> list[int]:
    """Load the example up to yesterday, run the rules and analyse them."""
    today = pilot.today()
    last = today - timedelta(1)
    recent_from = last - timedelta(RECENT[0] - 1)
    first = recent_from - timedelta(BASELINE[0])
    stock_from = last - timedelta(STOCK_WINDOW - 1)
    ozon = [
        {
            "sku": SKU,
            "day": d,
            "units": 50,
            "revenue": 44000.0,
            "commission": 6600.0,
            "logistics": 4400.0,
        }
        for d in days(first, last)
    ]
    wb = [
        {
            "sku": SKU,
            "day": d,
            "units": 50,
            "revenue": 50000.0,
            "commission": 7500.0,
            "logistics": 5000.0,
        }
        for d in days(stock_from, last)
    ]
    spend = [
        {"sku": SKU, "day": d, "spend": RECENT[1] if d >= recent_from else BASELINE[1]}
        for d in days(first, last)
    ]
    with pilot.engine.begin() as conn:
        conn.execute(
            insert(product).values(
                sku=SKU, name="Кофемолка ручная", wb_nm_id="1001", ozon_sku="9001"
            )
        )
        put_cost(conn, SKU, stock_from.replace(day=1), 440.0)
        replace_channel_facts(conn, sales_daily, "ozon", first, last, ozon)
        replace_channel_facts(conn, sales_daily, "wb", stock_from, last, wb)
        replace_channel_facts(conn, ad_spend_daily, "ozon", first, last, spend)
        replace_channel_facts(
            conn,
            stock_daily,
            "wb",
            last,
            last,
            [{"sku": SKU, "day": last, "stock": 400}],
        )
    found = pilot.run_rules()
    pilot.analyse_open()
    with pilot.engine.begin() as conn:
        load_history(pilot, conn, today)
    return found


def load_history(pilot: Pilot, conn: Connection, today: date) -> None:
    """Store the past decisions with their journal and a clean reconciliation."""
    for item in HISTORY:
        _past_decision(pilot, conn, today, *item)
    for channel, diff in (("wb", 0.4), ("ozon", 1.1)):
        conn.execute(
            insert(reconciliation).values(
                channel=channel,
                date_from=today - timedelta(14),
                date_to=today - timedelta(8),
                computed=100000.0,
                reported=100000.0 * (1 + diff / 100),
                diff_pct=diff,
                status=OK,
                checked_on=today - timedelta(1),
            )
        )


def _past_decision(
    pilot: Pilot,
    conn: Connection,
    today: date,
    sku: str,
    channel: str,
    rule: str,
    message: str,
    action: dict[str, Any],
    ago: int,
    title: str,
    result: Optional[tuple[float, float, float, str, float]],
) -> None:
    """Store one decision the way the loop leaves it: in work, closed, or
    evaluated and reopened with a new proposal when the goal was missed."""
    approver = pilot.config.approvers[0] if pilot.config.approvers else 1
    detected = today - timedelta(ago)
    deadline = detected + timedelta(TASK_DAYS)
    achieved = result is not None and result[3] == ACHIEVED
    manager = pilot.config.manager(channel)
    deviation_id = new_id(
        conn.execute(
            insert(deviation).values(
                rule=rule,
                sku=sku,
                channel=channel,
                window_start=detected - timedelta(3),
                window_end=detected - timedelta(1),
                message=message,
                impact=0.0 if achieved else RETRY_IMPACT,
                status="in work"
                if result is None
                else "closed"
                if achieved
                else "open",
                detected_on=detected,
            )
        )
    )
    values: dict[str, Any] = {
        "deviation_id": deviation_id,
        "status": IN_PROGRESS,
        "proposed_actions": [action],
        "actions": [action],
        "explanation": message,
        "label": RULES_LABEL,
        "figures": {},
        "target_pct": pilot.config.margin_plan(sku, channel) or TARGET_PCT,
        "guardrail_pct": pilot.config.guardrail_drop_pct,
        "significant_edit": False,
        "approved_by": approver,
        "decided_on": detected,
        "task_id": str(500 + ago),
        "task_title": title,
        "responsible_id": manager.user_id,
        "responsible_name": manager.name,
        "deadline": deadline,
        "created_on": detected,
    }
    evaluated = deadline + timedelta(FOLLOWUP_DAYS)
    if result is not None:
        after, before, sales, outcome, margin = result
        values.update(
            status="closed" if achieved else "evaluated",
            completed_on=deadline,
            followup_due=evaluated,
            outcome=outcome,
            result_text=result_text(after, before, sales, outcome),
            incremental_margin=margin,
            evaluated_on=evaluated,
        )
    decision_id = new_id(conn.execute(insert(decision).values(**values)))
    log_event(conn, decision_id, PROPOSED, detected)
    log_event(conn, decision_id, APPROVED, detected, approver)
    log_event(
        conn, decision_id, IN_PROGRESS, detected, note=f"task {values['task_id']}"
    )
    if result is None:
        return
    log_event(conn, decision_id, DONE, deadline)
    log_event(conn, decision_id, "evaluated", evaluated, note=values["result_text"])
    if achieved:
        log_event(conn, decision_id, "closed", evaluated)
        return
    retry, explanation = RETRY
    proposal_id = new_id(
        conn.execute(
            insert(decision).values(
                deviation_id=deviation_id,
                parent_id=decision_id,
                status=PROPOSED,
                proposed_actions=[retry],
                actions=[retry],
                explanation=explanation,
                label=RULES_LABEL,
                figures={},
                target_pct=values["target_pct"],
                guardrail_pct=values["guardrail_pct"],
                created_on=evaluated,
            )
        )
    )
    log_event(conn, proposal_id, PROPOSED, evaluated)
