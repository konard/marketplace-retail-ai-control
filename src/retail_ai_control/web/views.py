"""What the pages show: plain data for the templates, no HTML.

The decision card answers the manager's questions in order: what happened,
why, what to do, what effect to expect, and the decision itself. Every
figure keeps a link to the query and the rows it comes from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import select

from retail_ai_control import queries
from retail_ai_control.analysis import (
    DATA_CHECK,
    GENITIVE,
    RECONCILIATION_PERIOD,
)
from retail_ai_control.config import CHANNEL_NAMES, CHANNELS
from retail_ai_control.decisions import NOT_APPROVER, PROPOSED, latest_for
from retail_ai_control.execution import checklist_item, success_criterion
from retail_ai_control.fmt import day, money, number, pct
from retail_ai_control.mart import decision, deviation, evidence, journal
from retail_ai_control.reconcile import OK, channel_status

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

    from retail_ai_control.pilot import Pilot

EDITABLE = {
    "change_price": "Изменить цену, %",
    "set_ad_share": "Доля рекламы, %",
    "restock": "Поставка, шт.",
}
DECISION_STATUS = {
    "proposed": "Ждёт решения",
    "approved": "Утверждено",
    "in progress": "В работе",
    "done": "Выполнено, ждём эффект",
    "evaluated": "Эффект измерен",
    "closed": "Цель достигнута",
    "rejected": "Отклонено",
}
DEVIATION_STATUS = {
    "open": "Ждёт решения",
    "in work": "В работе",
    "closed": "Закрыто",
    "dismissed": "Отклонено",
}
STAGES = {
    "proposed": "Предложено",
    "approved": "Утверждено",
    "rejected": "Отклонено",
    "in progress": "Задача создана",
    "done": "Задача выполнена",
    "evaluated": "Эффект измерен",
    "closed": "Закрыто",
}
WITHHELD = {
    DATA_CHECK: "Данные канала не сходятся с отчётом маркетплейса. "
    "Предложение появится после сверки.",
    RECONCILIATION_PERIOD: "Идёт сверка данных с отчётами маркетплейсов. "
    "Предложения появятся после её окончания.",
}
LIMITS_NOTE = (
    "Цифры рассчитаны SQL-запросами; AI только объясняет их "
    "и предлагает действия в заданных пределах"
)
STATUS_CLASS = {
    "Ждёт решения": "status-wait",
    "Утверждено": "status-work",
    "В работе": "status-work",
    "Выполнено, ждём эффект": "status-work",
    "Эффект измерен": "status-done",
    "Цель достигнута": "status-done",
    "Закрыто": "status-done",
    "Отклонено": "status-off",
}
SPARK_WIDTH, SPARK_HEIGHT, SPARK_PAD = 240, 48, 4


def channel_name(channel: str) -> str:
    """``ozon`` -> ``Ozon``."""
    return CHANNEL_NAMES.get(channel, channel)


def status_class(status: str) -> str:
    """The CSS class of a status; the status is always shown as text too."""
    return STATUS_CLASS.get(status, "status-off")


def figure_label(name: str) -> str:
    """The Russian name of a figure of the analysis."""
    fixed = {
        "margin before": "Маржа до",
        "margin now": "Маржа сейчас",
        "price gap": "Разница цен между каналами",
        "units per day": "Продажи в день",
        "stock": "Остаток",
        "impact": "Потери",
    }
    if name in fixed:
        return fixed[name]
    if name.startswith("price:"):
        return f"Цена на {channel_name(name.split(':', 1)[1])}"
    item, _, period = name.rpartition(" ")
    if item in GENITIVE:
        return f"Доля {GENITIVE[item]} {'до' if period == 'before' else 'сейчас'}"
    return name


def figure_value(name: str, value: float) -> str:
    """Rates as ``4,0%``, money as ``14 520 ₽``, units as ``50 шт.``."""
    if name == "impact" or name.startswith("price:"):
        return money(value)
    if name in ("units per day", "stock"):
        return f"{number(value)} шт."
    return pct(value)


def input_value(action: dict[str, Any]) -> str:
    """The value of an action as the edit field shows it: ``5.0``, ``120``."""
    value = action.get("value")
    if value is None:
        return ""
    if action["type"] == "restock":
        return str(int(value))
    return f"{float(value):.1f}"


@dataclass
class Sparkline:
    """An inline SVG chart of the daily margin rate and its text alternative."""

    points: str
    plan_y: Optional[float]
    last: tuple[float, float]
    title: str
    width: int = SPARK_WIDTH
    height: int = SPARK_HEIGHT


def sparkline(
    days: list[tuple[date, float]], plan: Optional[float]
) -> Optional[Sparkline]:
    """Scale the daily rates to the chart; ``None`` without two points."""
    if len(days) < 2:
        return None
    values = [value for _, value in days]
    scale = [*values, plan] if plan is not None else values
    low, high = min(scale), max(scale)
    span = (high - low) or 1.0
    step = (SPARK_WIDTH - 2 * SPARK_PAD) / (len(days) - 1)

    def y(value: float) -> float:
        return round(
            SPARK_PAD + (high - value) / span * (SPARK_HEIGHT - 2 * SPARK_PAD), 1
        )

    coords = [(round(SPARK_PAD + i * step, 1), y(v)) for i, v in enumerate(values)]
    title = (
        f"Маржа по дням с {day(days[0][0])} по {day(days[-1][0])}: "
        f"от {pct(values[0])} до {pct(values[-1])}"
    )
    if plan is not None:
        title += f", план {pct(plan)}"
    return Sparkline(
        " ".join(f"{x},{y_}" for x, y_ in coords),
        y(plan) if plan is not None else None,
        coords[-1],
        title,
    )


@dataclass
class Card:
    """Everything the decision card shows."""

    deviation: dict[str, Any]
    decision: Optional[dict[str, Any]]
    channel: str
    period: str
    sparkline: Optional[Sparkline]
    figures: list[dict[str, Any]] = field(default_factory=list)
    cause_evidence: Optional[int] = None
    actions: list[dict[str, Any]] = field(default_factory=list)
    criterion: str = ""
    journal: list[dict[str, Any]] = field(default_factory=list)
    withheld: str = ""
    can_decide: bool = False
    why_not: str = ""
    status: str = ""


def _evidence_ids(conn: Connection, deviation_id: int) -> dict[str, int]:
    rows = conn.execute(
        select(evidence.c.name, evidence.c.id)
        .where(evidence.c.deviation_id == deviation_id)
        .order_by(evidence.c.id)
    ).mappings()
    return {str(row["name"]): int(row["id"]) for row in rows}


def _figures(row: dict[str, Any], ids: dict[str, int]) -> list[dict[str, Any]]:
    figures = []
    for name, item in row["figures"].items():
        source = item.get("evidence", "")
        figures.append(
            {
                "name": name,
                "label": figure_label(name),
                "value": figure_value(name, float(item["value"])),
                "evidence_id": item.get("evidence_id") or ids.get(source),
                "source": source,
            }
        )
    return figures


def _journal(conn: Connection, decision_id: int) -> list[dict[str, Any]]:
    return [
        {
            "stage": STAGES.get(row["stage"], row["stage"]),
            "day": day(row["on_day"]),
            "user_id": row["user_id"],
            "note": row["note"],
        }
        for row in journal(conn, decision_id)
    ]


def build_card(pilot: Pilot, deviation_id: int, user_id: Optional[int]) -> Card:
    """Collect the card of a deviation and its newest decision."""
    config = pilot.config
    with pilot.engine.connect() as conn:
        found = (
            conn.execute(select(deviation).where(deviation.c.id == deviation_id))
            .mappings()
            .first()
        )
        if found is None:
            raise LookupError(deviation_id)
        dev = dict(found)
        row = latest_for(conn, deviation_id)
        ids = _evidence_ids(conn, deviation_id)
        first = dev["window_start"] - timedelta(config.baseline_days)
        daily = queries.run(
            conn,
            "sku_days",
            channel=dev["channel"],
            sku=dev["sku"],
            date_from=first,
            date_to=dev["window_end"],
        ).rows
        events = _journal(conn, row["id"]) if row else []
    days = [
        (date.fromisoformat(str(item["day"])[:10]), float(item["margin_pct"]))
        for item in daily
        if item["margin_pct"] is not None
    ]
    card = Card(
        deviation=dev,
        decision=row,
        channel=channel_name(dev["channel"]),
        period=f"{day(dev['window_start'])} — {day(dev['window_end'])}",
        sparkline=sparkline(days, config.margin_plan(dev["sku"], dev["channel"])),
        journal=events,
        withheld=WITHHELD.get(dev["note"], ""),
        status=DECISION_STATUS.get(row["status"], row["status"])
        if row
        else DEVIATION_STATUS.get(dev["status"], dev["status"]),
    )
    if row is None:
        return card
    card.figures = _figures(row, ids)
    cause = next((f for f in card.figures if f["name"] == f"{row['cause']} now"), None)
    first_link = next((f for f in card.figures if f["evidence_id"]), None)
    chosen = cause or first_link
    card.cause_evidence = chosen["evidence_id"] if chosen else None
    card.actions = [
        {
            "type": action["type"],
            "text": checklist_item(action),
            "label": EDITABLE.get(action["type"]),
            "value": input_value(action),
        }
        for action in row["actions"]
    ]
    card.criterion = success_criterion(pilot, row)
    is_approver = user_id is not None and user_id in config.approvers
    card.can_decide = row["status"] == PROPOSED and is_approver
    if row["status"] == PROPOSED and not is_approver:
        card.why_not = NOT_APPROVER
    return card


def home_rows(pilot: Pilot) -> list[dict[str, Any]]:
    """Open deviations and deviations in work, the largest losses first."""
    with pilot.engine.connect() as conn:
        rows = (
            conn.execute(
                select(deviation)
                .where(deviation.c.status.in_(("open", "in work")))
                .order_by(deviation.c.impact.desc(), deviation.c.id)
            )
            .mappings()
            .all()
        )
        latest = {
            int(item["deviation_id"]): str(item["status"])
            for item in conn.execute(
                select(decision.c.deviation_id, decision.c.status).order_by(
                    decision.c.id
                )
            ).mappings()
        }
    return [
        {
            "id": row["id"],
            "sku": row["sku"],
            "channel": channel_name(row["channel"]),
            "message": row["message"],
            "impact": money(row["impact"]),
            "status": DECISION_STATUS[latest[row["id"]]]
            if row["id"] in latest and row["status"] == "open"
            else DEVIATION_STATUS.get(row["status"], row["status"]),
        }
        for row in rows
    ]


def data_warnings(pilot: Pilot) -> list[str]:
    """One line per channel whose data does not match the marketplace report."""
    with pilot.engine.connect() as conn:
        statuses = {channel: channel_status(conn, channel) for channel in CHANNELS}
    return [
        f"Данные {channel_name(channel)} не сверены с отчётом маркетплейса — "
        f"рекомендации по {channel_name(channel)} приостановлены"
        for channel, status in statuses.items()
        if status is not None and status != OK
    ]


def evidence_page(pilot: Pilot, evidence_id: int) -> dict[str, Any]:
    """The query, its parameters and the rows of one piece of evidence."""
    with pilot.engine.connect() as conn:
        row = (
            conn.execute(select(evidence).where(evidence.c.id == evidence_id))
            .mappings()
            .first()
        )
    if row is None:
        raise LookupError(evidence_id)
    rows: list[dict[str, Any]] = list(row["rows"])
    return {
        "id": row["id"],
        "name": row["name"],
        "sql": row["sql"].strip(),
        "params": row["params"],
        "columns": list(rows[0]) if rows else [],
        "rows": rows,
        "deviation_id": row["deviation_id"],
    }
