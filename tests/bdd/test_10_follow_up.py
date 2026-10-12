"""Steps of ``features/10_follow_up.feature``."""

from __future__ import annotations

from datetime import timedelta

from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy import select, update

from retail_ai_control import followup
from retail_ai_control.followup import Window
from retail_ai_control.mart import decision, deviation
from tests.bdd.support import (
    ACTIONS,
    World,
    add_decision,
    add_deviation,
    day,
    number,
    records,
)

scenarios("10_follow_up.feature")

CONCEPT_ACTIONS = [
    {"type": ACTIONS["set ad share"], "value": 9.0},
    {"type": ACTIONS["change price"], "value": 5.0},
]


@given(
    parsers.parse(
        'a decision for "{sku}" on "{channel}" with the target margin rate {target}%'
        " and the guardrail sales drop {guardrail}%"
    )
)
def approved_decision(
    world: World, sku: str, channel: str, target: str, guardrail: str
) -> None:
    with world.pilot.engine.begin() as conn:
        world.deviation_id = add_deviation(
            conn, sku=sku, channel=channel, status="in work"
        )
        world.decision_id = add_decision(
            conn,
            world.deviation_id,
            status="approved",
            proposed_actions=CONCEPT_ACTIONS,
            actions=CONCEPT_ACTIONS,
            target_pct=number(target),
            guardrail_pct=number(guardrail),
            approved_by=1,
            decided_on=world.today,
        )


@given(parsers.parse("the deviation of the decision started on {on_day}"))
def started(world: World, on_day: str) -> None:
    with world.pilot.engine.begin() as conn:
        conn.execute(
            update(deviation)
            .where(deviation.c.id == world.current_deviation())
            .values(window_start=day(on_day))
        )


@given(
    parsers.parse(
        "the Bitrix24 task {task_id} of the decision was completed on {on_day}"
    )
)
def completed(world: World, task_id: str, on_day: str) -> None:
    done = day(on_day)
    with world.pilot.engine.begin() as conn:
        conn.execute(
            update(decision)
            .where(decision.c.id == world.current_decision())
            .values(
                status="done",
                task_id=task_id,
                completed_on=done,
                followup_due=done + timedelta(world.config.followup_days),
            )
        )
    world.net.tasks[task_id] = {
        "id": task_id,
        "status": "5",
        "closedDate": f"{on_day}T18:00:00+03:00",
    }


@when("the follow-ups run")
def followups_run(world: World) -> None:
    world.found["followups"] = world.pilot.run_followups()
    if world.found["followups"]:
        world.outcome = world.found["followups"][0]["outcome"]


@when(
    parsers.parse(
        "the outcome is classified for a margin rate of {margin},"
        " a sales change of {sales} and an effect of {effect}"
    )
)
def classified(world: World, margin: str, sales: str, effect: str) -> None:
    world.outcome = followup.classify(
        number(margin), number(sales), number(effect), 12.0, 10.0
    )


def _result(world: World) -> followup.Result:
    result: followup.Result = world.found["followups"][0]["result"]
    return result


def _margin(window: Window | None) -> float:
    assert window is not None
    assert window.margin_pct is not None
    return round(window.margin_pct, 1)


@then("the follow-up compares:")
def compares(world: World, datatable: list[list[str]]) -> None:
    result = _result(world)
    found = {
        "margin rate": (
            _margin(result.before),
            _margin(result.after),
            round(_margin(result.after) - _margin(result.before), 1),
        ),
        "units per day": (
            result.before.units_per_day,
            result.after.units_per_day,
            result.sales_change_pct,
        ),
        "control margin rate": (
            _margin(result.control_before),
            _margin(result.control_after),
            round(_margin(result.control_after) - _margin(result.control_before), 1),
        ),
    }
    for row in records(datatable):
        expected = (number(row["before"]), number(row["after"]), number(row["change"]))
        assert found[row["metric"]] == expected, row["metric"]


@then(parsers.parse("the effect against the control group is {effect}"))
def effect(world: World, effect: str) -> None:
    assert _result(world).effect_pp == number(effect)


@then(parsers.parse("the incremental margin is {amount}"))
def incremental(world: World, amount: str) -> None:
    assert _result(world).incremental_margin == number(amount)
    assert world.decision_row()["incremental_margin"] == number(amount)


@then(parsers.parse('the outcome is "{outcome}"'))
def outcome(world: World, outcome: str) -> None:
    assert world.outcome == outcome


@then(parsers.parse('the result says "{text}"'))
def result_says(world: World, text: str) -> None:
    assert world.decision_row()["result_text"] == text


@then(parsers.parse('Bitrix24 receives "{method}" for task {task_id} with "{text}"'))
def task_comment(world: World, method: str, task_id: str, text: str) -> None:
    assert world.net.calls(method) == [
        {"TASKID": task_id, "FIELDS": {"POST_MESSAGE": text}}
    ]


@then(parsers.parse('Bitrix24 receives no "{method}" call'))
def no_call(world: World, method: str) -> None:
    assert world.net.calls(method) == []


def next_steps(world: World) -> list[dict[str, object]]:
    """Open proposals that continue the current decision."""
    with world.pilot.engine.connect() as conn:
        rows = conn.execute(
            select(decision).where(
                decision.c.parent_id == world.current_decision(),
                decision.c.status == "proposed",
            )
        ).mappings()
        return [dict(row) for row in rows]


@then("a next-step proposal linked to the decision is open")
def next_step_open(world: World) -> None:
    assert len(next_steps(world)) == 1


@then("no next-step proposal is open")
def no_next_step(world: World) -> None:
    assert next_steps(world) == []
