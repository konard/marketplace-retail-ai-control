"""Approved decisions become Bitrix24 tasks; Bitrix24 reports when they are done.

The task gets the actions as a checklist, the channel manager as the
responsible person, a deadline in business days and the success criterion.
The task ID is stored right after the task is created, so a retry after a
Bitrix24 outage never creates a second task.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select, update

from retail_ai_control import rules
from retail_ai_control.config import CHANNEL_NAMES
from retail_ai_control.connectors.bitrix24 import COMPLETED
from retail_ai_control.decisions import APPROVED, get
from retail_ai_control.fmt import pct, signed_pct
from retail_ai_control.mart import decision, deviation, log_event
from retail_ai_control.workdays import add_business_days

if TYPE_CHECKING:
    from retail_ai_control.pilot import Pilot

logger = logging.getLogger(__name__)
IN_PROGRESS = "in progress"
DONE = "done"
TITLE_PREFIX = {
    rules.MARGIN: "Маржа",
    rules.ADVERTISING: "Реклама",
    rules.STOCKOUT: "Остатки",
    rules.SALES_DROP: "Продажи",
}


def short_label(action: dict[str, Any]) -> str:
    """A few words for the task title: ``реклама 9,0%``."""
    kind, value = action["type"], action.get("value") or 0
    if kind == "set_ad_share":
        return f"реклама {pct(float(value))}"
    if kind == "change_price":
        return f"цена {signed_pct(float(value))}"
    if kind == "restock":
        return f"поставка {int(value)} шт."
    return "проверка причин"


def checklist_item(action: dict[str, Any]) -> str:
    """One instruction per action: ``Снизить долю рекламы до 9,0%``."""
    kind, value = action["type"], action.get("value") or 0
    if kind == "set_ad_share":
        return f"Снизить долю рекламы до {pct(float(value))}"
    if kind == "change_price":
        return f"Изменить цену на {signed_pct(float(value))}"
    if kind == "restock":
        return f"Заказать поставку {int(value)} шт."
    return "Проверить причины отклонения и предложить действие"


def task_title(row: dict[str, Any], dev: dict[str, Any]) -> str:
    """``Маржа SKU-1001 на Ozon: реклама 9,0%, цена +5,0%``."""
    prefix = TITLE_PREFIX.get(dev["rule"], "Отклонение")
    labels = ", ".join(short_label(action) for action in row["actions"])
    return f"{prefix} {dev['sku']} на {CHANNEL_NAMES[dev['channel']]}: {labels}"


def success_criterion(pilot: Pilot, row: dict[str, Any]) -> str:
    """The measurable target the follow-up checks."""
    return (
        f"Критерий успеха: маржа ≥ {pct(row['target_pct'])} при падении продаж "
        f"≤ {pct(row['guardrail_pct'])} за {pilot.config.followup_days} дней"
    )


def deadline(pilot: Pilot, today: date) -> datetime:
    """The end of the working day ``task_business_days`` business days later."""
    config = pilot.config
    day = add_business_days(today, config.task_business_days, config.holidays)
    return datetime.combine(
        day, time(config.task_hour), tzinfo=ZoneInfo(config.timezone)
    )


def _description(pilot: Pilot, row: dict[str, Any], dev: dict[str, Any]) -> str:
    lines = [row["explanation"], "", "Действия:"]
    lines += [f"- {checklist_item(action)}" for action in row["actions"]]
    lines += [
        "",
        success_criterion(pilot, row),
        f"Карточка решения: {pilot.config.web_url.rstrip('/')}/deviations/{dev['id']}",
    ]
    return "\n".join(lines)


def create_task(pilot: Pilot, decision_id: int) -> bool:
    """Create the task of an approved decision; ``False`` if Bitrix24 failed."""
    if pilot.bitrix is None:
        return False
    today = pilot.today()
    with pilot.engine.connect() as conn:
        row = get(conn, decision_id)
        dev = dict(
            conn.execute(select(deviation).where(deviation.c.id == row["deviation_id"]))
            .mappings()
            .one()
        )
    if row["status"] != APPROVED or row["task_id"]:
        return False
    person = pilot.config.manager(dev["channel"])
    due = deadline(pilot, today)
    title = task_title(row, dev)
    fields = {
        "TITLE": title,
        "DESCRIPTION": _description(pilot, row, dev),
        "RESPONSIBLE_ID": person.user_id,
        "CREATED_BY": row["approved_by"],
        "DEADLINE": due.isoformat(),
    }
    try:
        task_id = pilot.bitrix.add_task(fields)
    except httpx.HTTPError as error:
        pilot.note(f"task of decision {decision_id} not created: {error}")
        return False
    with pilot.engine.begin() as conn:
        conn.execute(
            update(decision)
            .where(decision.c.id == decision_id)
            .values(
                status=IN_PROGRESS,
                task_id=task_id,
                task_title=title,
                responsible_id=person.user_id,
                responsible_name=person.name,
                deadline=due.date(),
            )
        )
        conn.execute(
            update(deviation)
            .where(deviation.c.id == dev["id"])
            .values(status="in work")
        )
        log_event(conn, decision_id, IN_PROGRESS, today, note=f"task {task_id}")
    for action in row["actions"]:
        try:
            pilot.bitrix.add_checklist_item(task_id, checklist_item(action))
        except httpx.HTTPError as error:
            pilot.note(f"checklist of task {task_id} incomplete: {error}")
            break
    return True


def retry_tasks(pilot: Pilot) -> int:
    """Create the tasks that failed earlier; return how many were created."""
    with pilot.engine.connect() as conn:
        pending: list[int] = list(
            conn.execute(
                select(decision.c.id).where(
                    decision.c.status == APPROVED, decision.c.task_id.is_(None)
                )
            )
            .scalars()
            .all()
        )
    return sum(create_task(pilot, decision_id) for decision_id in pending)


def handle_task_event(pilot: Pilot, form: dict[str, str]) -> int:
    """Process an ``ONTASKUPDATE`` event; return the HTTP status to answer.

    The event carries only the task ID, so the task is read back with
    ``tasks.task.get``. A completed task moves the decision to ``done`` and
    schedules the follow-up.
    """
    token = pilot.config.bitrix_application_token
    if not token or form.get("auth[application_token]") != token:
        return 401
    task_id = form.get("data[FIELDS_AFTER][ID]", "")
    with pilot.engine.connect() as conn:
        row = (
            conn.execute(
                select(decision).where(
                    decision.c.task_id == task_id, decision.c.status == IN_PROGRESS
                )
            )
            .mappings()
            .first()
        )
    if row is None or pilot.bitrix is None:
        return 200
    try:
        task = pilot.bitrix.get_task(task_id)
    except httpx.HTTPError as error:
        pilot.note(f"task {task_id} not read: {error}")
        return 503
    if str(task.get("status")) != COMPLETED:
        return 200
    closed = task.get("closedDate") or pilot.today().isoformat()
    completed = date.fromisoformat(str(closed)[:10])
    with pilot.engine.begin() as conn:
        conn.execute(
            update(decision)
            .where(decision.c.id == row["id"])
            .values(
                status=DONE,
                completed_on=completed,
                followup_due=completed + timedelta(pilot.config.followup_days),
            )
        )
        log_event(conn, row["id"], DONE, completed, note=f"task {task_id} completed")
    return 200
