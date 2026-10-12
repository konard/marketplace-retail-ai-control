"""Steps of ``features/12_pilot_scorecard.feature``."""

from __future__ import annotations

from datetime import date

from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy import delete, insert

from retail_ai_control.mart import reconciliation
from retail_ai_control.metrics import Scorecard
from retail_ai_control.workdays import add_business_days
from tests.bdd.support import World, add_decision, add_deviation, number, records

scenarios("12_pilot_scorecard.feature")

DECIDED_ON = date(2026, 10, 12)
MET = {True: "да", False: "нет"}


def plain(text: str) -> str:
    """Collapse spaces, including the no-break spaces of formatted numbers."""
    return " ".join(text.replace(" ", " ").split())


@given(parsers.parse("the pilot costs {cost}"))
def pilot_cost(world: World, cost: str) -> None:
    world.config.pilot_cost = number(cost)


@given(
    parsers.parse("the largest reconciliation difference of the pilot is {difference}")
)
def largest_difference(world: World, difference: str) -> None:
    with world.pilot.engine.begin() as conn:
        conn.execute(delete(reconciliation))
        conn.execute(
            insert(reconciliation).values(
                channel="ozon",
                date_from=DECIDED_ON,
                date_to=DECIDED_ON,
                computed=0.0,
                diff_pct=number(difference),
                status="ok",
                checked_on=DECIDED_ON,
            )
        )


@given("these decisions were made during the pilot:")
def pilot_decisions(world: World, datatable: list[list[str]]) -> None:
    holidays = world.config.holidays
    with world.pilot.engine.begin() as conn:
        for row in records(datatable):
            approved = row["status"] == "approved"
            lead = row["lead time"]
            add_decision(
                conn,
                add_deviation(conn),
                status="closed" if approved else "rejected",
                decided_on=DECIDED_ON,
                approved_by=1 if approved else None,
                significant_edit=row["significant edit"] == "yes",
                completed_on=(
                    add_business_days(DECIDED_ON, int(lead), holidays) if lead else None
                ),
                incremental_margin=(
                    number(row["incremental margin"])
                    if row["incremental margin"]
                    else None
                ),
            )


@when("the pilot scorecard is calculated")
def calculated(world: World) -> None:
    world.found["scorecard"] = world.pilot.scorecard()


def _scorecard(world: World) -> Scorecard:
    found: Scorecard = world.found["scorecard"]
    return found


@then("the scorecard is:")
def scorecard_is(world: World, datatable: list[list[str]]) -> None:
    found = [
        [item.name, plain(item.target), plain(item.actual), MET[item.met]]
        for item in _scorecard(world).criteria
    ]
    assert found == [[plain(cell) for cell in row] for row in datatable[1:]]


@then(parsers.parse('the criterion "{name}" is not met'))
def not_met(world: World, name: str) -> None:
    assert [item.met for item in _scorecard(world).criteria if item.name == name] == [
        False
    ]


@then(parsers.parse('the verdict is "{verdict}"'))
def verdict(world: World, verdict: str) -> None:
    assert _scorecard(world).verdict == verdict
