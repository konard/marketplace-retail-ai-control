"""Proposals and the decisions people make on them.

A proposal is a decision in the ``proposed`` status. Only an approver may
approve or reject it, only once, and a rejection needs a reason. Edits are
allowed; an edit that removes an action or changes a value by more than half
is significant and counts against the pilot criterion "decisions accepted
without significant edits".

Statuses: proposed -> approved -> in progress -> done -> evaluated | closed,
or proposed -> rejected.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from retail_ai_control.config import Config
from retail_ai_control.fmt import pct
from retail_ai_control.mart import decision, deviation, log_event, new_id

if TYPE_CHECKING:
    from retail_ai_control.analysis import Analysis
    from retail_ai_control.pilot import Pilot

PROPOSED = "proposed"
APPROVED = "approved"
REJECTED = "rejected"
ACTIVE = (PROPOSED, APPROVED, "in progress", "done")
SIGNIFICANT_CHANGE = 0.5
NOT_APPROVER = "Утверждать могут только назначенные руководители"
NO_REASON = "Укажите причину отклонения"
ALREADY_DECIDED = "Решение уже принято"


class DecisionError(Exception):
    """A request that cannot be carried out, with an HTTP status.

    ``field`` names the input the message is about: an action type or
    ``reason``.
    """

    def __init__(self, status: int, message: str, field: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.field = field


def create_decision(
    conn: Connection, analysis: Analysis, today: date, parent_id: Optional[int] = None
) -> int:
    """Store the proposal of an analysis and start its journal."""
    result = conn.execute(
        insert(decision).values(
            deviation_id=analysis.deviation["id"],
            parent_id=parent_id,
            status=PROPOSED,
            proposed_actions=analysis.actions,
            actions=analysis.actions,
            explanation=analysis.explanation,
            label=analysis.label,
            cause=analysis.cause,
            figures=analysis.figures,
            target_pct=analysis.target_pct,
            guardrail_pct=analysis.guardrail_pct,
            created_on=today,
        )
    )
    decision_id = new_id(result)
    log_event(conn, decision_id, PROPOSED, today)
    return decision_id


def get(conn: Connection, decision_id: int) -> dict[str, Any]:
    """Return a decision; raise 404 if it does not exist."""
    row = (
        conn.execute(select(decision).where(decision.c.id == decision_id))
        .mappings()
        .first()
    )
    if row is None:
        msg = "Решение не найдено"
        raise DecisionError(404, msg)
    return dict(row)


def latest_for(conn: Connection, deviation_id: int) -> Optional[dict[str, Any]]:
    """Return the newest decision of a deviation, if any."""
    row = (
        conn.execute(
            select(decision)
            .where(decision.c.deviation_id == deviation_id)
            .order_by(decision.c.id.desc())
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def is_significant(
    proposed: list[dict[str, Any]], actions: list[dict[str, Any]]
) -> bool:
    """An action was removed or added, or a value changed by more than half."""
    before = {item["type"]: item.get("value") for item in proposed}
    after = {item["type"]: item.get("value") for item in actions}
    if set(before) != set(after):
        return True
    for kind, old in before.items():
        new = after[kind]
        if old is None or new is None:
            continue
        if not old:
            if new:
                return True
            continue
        if abs(float(new) - float(old)) / abs(float(old)) > SIGNIFICANT_CHANGE:
            return True
    return False


def limit_error(action: dict[str, Any], config: Config) -> Optional[str]:
    """Explain in Russian why an edited action breaks a limit, or ``None``."""
    kind, value = action.get("type"), action.get("value")
    if value is None:
        return None
    if kind == "change_price" and abs(value) > config.price_change_max_pct:
        return f"Изменение цены — не больше {pct(config.price_change_max_pct)}"
    if kind == "set_ad_share" and not 0 <= value <= config.ad_share_limit_pct:
        return f"Доля рекламы — от 0 до {pct(config.ad_share_limit_pct)}"
    if kind == "restock" and value < 0:
        return "Поставка не может быть отрицательной"
    return None


def _check(
    pilot: Pilot, conn: Connection, decision_id: int, user_id: int
) -> dict[str, Any]:
    if user_id not in pilot.config.approvers:
        raise DecisionError(403, NOT_APPROVER)
    row = get(conn, decision_id)
    if row["status"] != PROPOSED:
        raise DecisionError(409, ALREADY_DECIDED)
    return row


def approve(
    pilot: Pilot,
    decision_id: int,
    user_id: int,
    actions: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Approve a proposal, possibly edited, and create the Bitrix24 task."""
    today = pilot.today()
    with pilot.engine.begin() as conn:
        row = _check(pilot, conn, decision_id, user_id)
        chosen = row["actions"] if actions is None else actions
        for action in chosen:
            error = limit_error(action, pilot.config)
            if error:
                raise DecisionError(422, error, action["type"])
        conn.execute(
            update(decision)
            .where(decision.c.id == decision_id)
            .values(
                status=APPROVED,
                actions=chosen,
                significant_edit=is_significant(row["proposed_actions"], chosen),
                approved_by=user_id,
                decided_on=today,
            )
        )
        log_event(conn, decision_id, APPROVED, today, user_id)
    from retail_ai_control.execution import create_task  # noqa: PLC0415 - cycle

    create_task(pilot, decision_id)
    with pilot.engine.connect() as conn:
        return get(conn, decision_id)


def reject(pilot: Pilot, decision_id: int, user_id: int, reason: str) -> dict[str, Any]:
    """Reject a proposal with a reason; the deviation is dismissed."""
    today = pilot.today()
    with pilot.engine.begin() as conn:
        row = _check(pilot, conn, decision_id, user_id)
        if not reason.strip():
            raise DecisionError(422, NO_REASON, "reason")
        conn.execute(
            update(decision)
            .where(decision.c.id == decision_id)
            .values(
                status=REJECTED,
                reject_reason=reason.strip(),
                approved_by=None,
                decided_on=today,
            )
        )
        conn.execute(
            update(deviation)
            .where(deviation.c.id == row["deviation_id"])
            .values(status="dismissed")
        )
        log_event(conn, decision_id, REJECTED, today, user_id, reason.strip())
        return get(conn, decision_id)
