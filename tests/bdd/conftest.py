"""Shared fixtures and the steps that several features use.

Feature-specific steps live in the ``test_NN_*.py`` module of the feature.
Steps change the world through the production entry points; the checks read
the data mart, the pages and the calls the fake network received.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from bs4 import Tag
from pytest_bdd import given, parsers, then, when
from sqlalchemy import insert, select

from retail_ai_control.config import Person
from retail_ai_control.mart import (
    deviation,
    journal,
    log_event,
    put_cost,
    reconciliation,
)
from retail_ai_control.reconcile import channel_status
from tests.bdd.fakes import Reply
from tests.bdd.support import (
    World,
    actions_of,
    add_decision,
    add_deviation,
    day,
    labelled_field,
    load_sales,
    number,
    page,
    plain,
    records,
)

DEVIATION = (
    r'an? "(?P<rule>[^"]+)" deviation is open for "(?P<sku>[^"]+)"'
    r' on "(?P<channel>[^"]+)"'
)
RULE_MESSAGES = {
    "margin below plan": "Маржа 4,0% при плане 15,0% — 3 дня подряд",
    "stockout risk": "Остатка хватит на 8 дн. при норме 14 дн.",
    "sales drop": "Выручка за 7 дней −30,0% к прошлой неделе",
    "advertising above limit": "Доля рекламы 18,0% при лимите 15,0%",
}


@pytest.fixture
def world() -> Iterator[World]:
    """A fresh pilot with an empty data mart and quiet external systems."""
    found = World()
    yield found
    found.client.close()
    found.pilot.http.close()


# Time and settings
@given(parsers.parse("today is {on_day}"))
@when(parsers.parse("today is {on_day}"))
def today_is(world: World, on_day: str) -> None:
    world.today = day(on_day)


@given(parsers.parse('the margin plan of "{sku}" on "{channel}" is {plan}%'))
def margin_plan(world: World, sku: str, channel: str, plan: str) -> None:
    world.config.margin_plan_pct[f"{sku}:{channel}"] = number(plan)


@given(parsers.parse("the approvers are users {first:d} and {second:d}"))
def approvers(world: World, first: int, second: int) -> None:
    world.config.approvers = [first, second]


@given(parsers.parse('the "{channel}" channel manager is user {user_id:d} "{name}"'))
def channel_manager(world: World, channel: str, user_id: int, name: str) -> None:
    world.config.channel_managers[channel] = Person(user_id, name)


@given(parsers.parse('the web app runs at "{url}"'))
def web_url(world: World, url: str) -> None:
    world.config.web_url = url


# Data in the data mart and in 1C
@given(parsers.parse('"{sku}" has a unit cost of {cost} from {valid_from}'))
def unit_cost(world: World, sku: str, cost: str, valid_from: str) -> None:
    with world.pilot.engine.begin() as conn:
        put_cost(conn, sku, day(valid_from), number(cost))


@given("these daily sales were loaded:")
def daily_sales(world: World, datatable: list[list[str]]) -> None:
    with world.pilot.engine.begin() as conn:
        load_sales(conn, records(datatable))


@given("the product catalog in 1C maps articles to marketplace IDs:")
def catalog(world: World, datatable: list[list[str]]) -> None:
    world.net.onec_products = [
        {
            "Ref_Key": f"ref-{row['sku']}",
            "Артикул": row["sku"],
            "Description": row["name"],
            "АртикулWB": row["wb_nm_id"],
            "SKUOzon": row["ozon_sku"],
        }
        for row in records(datatable)
    ]


@given("1C publishes these cost prices:")
def onec_costs(world: World, datatable: list[list[str]]) -> None:
    world.net.onec_costs = [
        {
            "Номенклатура_Key": f"ref-{row['sku']}",
            "Period": f"{row['valid_from']}T00:00:00",
            "Себестоимость": number(row["unit_cost"]),
        }
        for row in records(datatable)
    ]


# Reconciliation
@given(parsers.parse('the "{channel}" reconciliation status is "{status}"'))
def reconciliation_given(world: World, channel: str, status: str) -> None:
    with world.pilot.engine.begin() as conn:
        conn.execute(
            insert(reconciliation).values(
                channel=channel,
                date_from=world.today - timedelta(7),
                date_to=world.today - timedelta(1),
                computed=0.0,
                status=status,
                checked_on=world.today,
            )
        )


@then(parsers.parse('the "{channel}" reconciliation status is "{status}"'))
def reconciliation_then(world: World, channel: str, status: str) -> None:
    with world.pilot.engine.connect() as conn:
        assert channel_status(conn, channel) == status


# Deviations and their analysis
@given(parsers.re(DEVIATION))
def deviation_given(world: World, rule: str, sku: str, channel: str) -> None:
    with world.pilot.engine.begin() as conn:
        world.deviation_id = add_deviation(
            conn, rule=rule, sku=sku, channel=channel, message=RULE_MESSAGES[rule]
        )


@then(parsers.re(DEVIATION))
def deviation_then(world: World, rule: str, sku: str, channel: str) -> None:
    with world.pilot.engine.connect() as conn:
        found: list[int] = list(
            conn.execute(
                select(deviation.c.id).where(
                    deviation.c.rule == rule,
                    deviation.c.sku == sku,
                    deviation.c.channel == channel,
                    deviation.c.status == "open",
                )
            )
            .scalars()
            .all()
        )
    assert found, f"no open {rule!r} deviation for {sku} on {channel}"
    world.deviation_id = int(found[0])


@given("the deviation rules have run")
@when("the deviation rules run")
def rules_run(world: World) -> None:
    world.pilot.run_rules()


@when("the deviation is analysed")
def analysed(world: World) -> None:
    world.analysis = world.pilot.analyse(world.current_deviation())


# The AI model
@given(parsers.parse('the AI model first calls the tool "{tool}" and then answers:'))
def ai_tool_then_answer(world: World, tool: str, docstring: str) -> None:
    world.enable_ai()
    world.net.llm_replies = [Reply(tool=tool), Reply(content=docstring)]


@given("the AI model answers:")
def ai_answers(world: World, docstring: str) -> None:
    world.enable_ai()
    world.net.llm_replies = [Reply(content=docstring)]


@given("the AI model is unavailable")
def ai_unavailable(world: World) -> None:
    world.enable_ai()
    world.net.llm_down = True


# Proposals and decisions
@given(parsers.parse('a proposal for "{sku}" on "{channel}" contains the actions:'))
def proposal(world: World, sku: str, channel: str, datatable: list[list[str]]) -> None:
    actions = actions_of(datatable)
    with world.pilot.engine.begin() as conn:
        world.deviation_id = add_deviation(conn, sku=sku, channel=channel)
        world.decision_id = add_decision(
            conn,
            world.deviation_id,
            proposed_actions=actions,
            actions=actions,
            created_on=world.today,
        )
        log_event(conn, world.decision_id, "proposed", world.today)


@given(parsers.parse("user {user:d} approved the proposal"))
@when(parsers.parse("user {user:d} approves the proposal"))
def approves(world: World, user: int) -> None:
    world.post(f"/decisions/{world.current_decision()}/approve", user, {})


@then(parsers.parse('the decision status is "{status}"'))
def decision_status(world: World, status: str) -> None:
    assert world.decision_row()["status"] == status


@then(parsers.parse('Bitrix24 receives "{method}" with the fields:'))
def bitrix_fields(world: World, method: str, datatable: list[list[str]]) -> None:
    calls = world.net.calls(method)
    assert calls, f"no {method} call"
    fields = calls[-1]["fields"]
    for row in records(datatable):
        assert str(fields[row["field"]]) == row["value"], row["field"]


def journal_of(world: World) -> list[dict[str, object]]:
    """The journal entries of the current decision."""
    with world.pilot.engine.connect() as conn:
        return journal(conn, world.current_decision())


@then(parsers.parse('the page shows the error "{error}" linked to the field "{label}"'))
def field_error(world: World, error: str, label: str) -> None:
    field = labelled_field(world, label)
    assert field.get("aria-invalid") == "true"
    described = [
        page(world).find(id=ref) for ref in str(field["aria-describedby"]).split()
    ]
    assert error in [plain(item) for item in described if isinstance(item, Tag)]
