"""Team performance and the pilot scorecard.

The scorecard checks the four criteria fixed before the pilot: data matches
the marketplace reports, decisions are accepted without significant edits,
tasks are done quickly, and the measured extra margin pays for the pilot.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import func, select

from retail_ai_control.fmt import money, pct
from retail_ai_control.mart import decision, reconciliation
from retail_ai_control.workdays import business_days_between

if TYPE_CHECKING:
    from retail_ai_control.pilot import Pilot

PAYS_OFF = "Пилот окупается: продолжать"
NO_PAYBACK = "Пилот не окупился: остановить или сузить"
PROCESS_NOT_READY = "Эффект есть, процесс не готов: продлить пилот и устранить причины"
DATA_CRITERION = "Расхождение с отчётом маркетплейса"
EDITS_CRITERION = "Решения приняты без существенных правок"
LEAD_CRITERION = "Медианный срок исполнения"
MARGIN_CRITERION = "Дополнительная маржа"
NO_DATA = "—"


def share(part: int, whole: int) -> int:
    """A whole percentage; 0 when there is nothing to count."""
    return round(100 * part / whole) if whole else 0


def team_performance(pilot: Pilot) -> list[dict[str, Any]]:
    """Tasks, on-time share, overdue tasks and achieved share per person."""
    today = pilot.today()
    with pilot.engine.connect() as conn:
        rows = (
            conn.execute(
                select(decision)
                .where(decision.c.task_id.is_not(None))
                .order_by(decision.c.responsible_name)
            )
            .mappings()
            .all()
        )
    people: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        people[row["responsible_name"] or str(row["responsible_id"])].append(row)
    table = []
    for name, tasks in people.items():
        on_time = sum(
            1 for t in tasks if t["completed_on"] and t["completed_on"] <= t["deadline"]
        )
        overdue = sum(
            1 for t in tasks if not t["completed_on"] and t["deadline"] < today
        )
        achieved = sum(1 for t in tasks if t["outcome"] == "achieved")
        table.append(
            {
                "responsible": name,
                "tasks": len(tasks),
                "on_time_pct": share(on_time, len(tasks)),
                "overdue": overdue,
                "achieved_pct": share(achieved, len(tasks)),
            }
        )
    return table


@dataclass
class Criterion:
    """One row of the scorecard."""

    name: str
    target: str
    actual: str
    met: bool


@dataclass
class Scorecard:
    """The criteria, the measured extra margin and the verdict."""

    criteria: list[Criterion]
    incremental_margin: float
    verdict: str


def _days(value: float) -> str:
    return f"{value:g} раб. дн.".replace(".", ",")


def scorecard(pilot: Pilot) -> Scorecard:
    """Measure the pilot against its criteria and give the verdict."""
    config = pilot.config
    with pilot.engine.connect() as conn:
        worst: Optional[float] = conn.execute(
            select(func.max(reconciliation.c.diff_pct))
        ).scalar()
        rows = (
            conn.execute(select(decision).where(decision.c.decided_on.is_not(None)))
            .mappings()
            .all()
        )
    accepted = sum(
        1
        for row in rows
        if row["approved_by"] is not None and not row["significant_edit"]
    )
    lead_times = [
        business_days_between(row["decided_on"], row["completed_on"], config.holidays)
        for row in rows
        if row["completed_on"] is not None
    ]
    median = statistics.median(lead_times) if lead_times else None
    margin = round(sum(float(row["incremental_margin"] or 0) for row in rows), 2)
    tolerance = config.reconciliation_tolerance_pct
    criteria = [
        Criterion(
            DATA_CRITERION,
            f"≤ {pct(tolerance)}",
            NO_DATA if worst is None else pct(worst),
            worst is not None and worst <= tolerance,
        ),
        Criterion(
            EDITS_CRITERION,
            f"≥ {config.approval_share_target_pct:g}%",
            f"{share(accepted, len(rows))}%" if rows else NO_DATA,
            bool(rows)
            and share(accepted, len(rows)) >= config.approval_share_target_pct,
        ),
        Criterion(
            LEAD_CRITERION,
            f"≤ {_days(config.lead_time_target_days)}",
            NO_DATA if median is None else _days(median),
            median is not None and median <= config.lead_time_target_days,
        ),
        Criterion(
            MARGIN_CRITERION,
            f"≥ {money(config.pilot_cost)}",
            money(margin),
            margin >= config.pilot_cost,
        ),
    ]
    if not criteria[-1].met:
        verdict = NO_PAYBACK
    elif all(item.met for item in criteria):
        verdict = PAYS_OFF
    else:
        verdict = PROCESS_NOT_READY
    return Scorecard(criteria, margin, verdict)
