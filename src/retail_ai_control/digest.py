"""The morning digest in a Bitrix24 chat (BB codes).

Order of the message: data problems first (they make the rest unreliable),
then the open deviations by money at stake, then the results of decisions
evaluated today and the overdue tasks. A quiet day still gets a message, so
the reader knows the loop ran.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from retail_ai_control.config import CHANNEL_NAMES, CHANNELS
from retail_ai_control.fmt import day, money, plural
from retail_ai_control.mart import decision, deviation
from retail_ai_control.reconcile import OK, channel_status

if TYPE_CHECKING:
    from retail_ai_control.pilot import Pilot


def build_digest(pilot: Pilot) -> str:
    """Build the digest text for today."""
    config = pilot.config
    today = pilot.today()
    web = config.web_url.rstrip("/")
    lines = [f"[B]Сводка на {day(today)}[/B]"]
    with pilot.engine.connect() as conn:
        for channel in CHANNELS:
            status = channel_status(conn, channel)
            if status is not None and status != OK:
                name = CHANNEL_NAMES[channel]
                lines.append(
                    f"Данные {name} не сверены с отчётом маркетплейса — рекомендации по {name} приостановлены"
                )
        open_rows = (
            conn.execute(
                select(deviation)
                .where(deviation.c.status == "open")
                .order_by(deviation.c.impact.desc(), deviation.c.id)
            )
            .mappings()
            .all()
        )
        evaluated = (
            conn.execute(
                select(decision, deviation.c.sku, deviation.c.channel)
                .join(deviation, deviation.c.id == decision.c.deviation_id)
                .where(decision.c.evaluated_on == today)
                .order_by(decision.c.id)
            )
            .mappings()
            .all()
        )
        overdue = (
            conn.execute(
                select(decision)
                .where(decision.c.status == "in progress", decision.c.deadline < today)
                .order_by(decision.c.deadline)
            )
            .mappings()
            .all()
        )
    if not open_rows:
        lines.append("Отклонений нет.")
    shown = open_rows[: config.digest_max_items]
    for number, row in enumerate(shown, start=1):
        lines.append(
            f"{number}. {row['sku']} · {CHANNEL_NAMES[row['channel']]} — {row['message']}"
        )
        lines.append(
            f"Потери ≈ {money(row['impact'])} · [URL={web}/deviations/{row['id']}]Открыть карточку[/URL]"
        )
    rest = len(open_rows) - len(shown)
    if rest > 0:
        word = plural(rest, "отклонение", "отклонения", "отклонений")
        lines.append(f"Ещё {rest} {word} — в журнале решений")
    if evaluated:
        lines.append("[B]Результаты решений[/B]")
        lines += [
            f"{row['sku']} · {CHANNEL_NAMES[row['channel']]}: {row['result_text']}"
            for row in evaluated
        ]
    lines += [
        f"Просрочено: {row['task_title']} — {row['responsible_name']}, срок {day(row['deadline'])}"
        for row in overdue
    ]
    return "\n".join(lines)


def send_digest(pilot: Pilot) -> str:
    """Post the digest to the configured Bitrix24 dialog and return it."""
    text = build_digest(pilot)
    if pilot.bitrix is not None and pilot.config.digest_dialog:
        pilot.bitrix.message(pilot.config.digest_dialog, text)
    return text
