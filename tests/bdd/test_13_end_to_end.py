"""Steps of ``features/13_end_to_end.feature``.

Here nothing is put into the data mart directly: the marketplaces, 1C and
the analytics service serve the data, the morning run loads it, and the
users act through the web app and Bitrix24, like in production.
"""

from __future__ import annotations

import re

from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy import select

from retail_ai_control.config import Person
from retail_ai_control.mart import deviation
from tests.bdd.conftest import journal_of
from tests.bdd.fakes import MATCH_SALES
from tests.bdd.support import (
    APPLICATION_TOKEN,
    World,
    daily_values,
    day,
    number,
    records,
    text_of,
)

scenarios("13_end_to_end.feature")

MANAGER = re.compile(r'(?P<user>\d+) "(?P<name>[^"]+)"')


@given("the pilot is configured:")
def configured(world: World, datatable: list[list[str]]) -> None:
    config = world.config
    for row in records(datatable):
        setting, value = row["setting"], row["value"]
        if setting == "approvers":
            config.approvers = [int(user) for user in value.split(",")]
        elif setting.endswith(" manager"):
            found = MANAGER.fullmatch(value)
            assert found is not None, value
            config.channel_managers[setting.removesuffix(" manager")] = Person(
                int(found["user"]), found["name"]
            )
        elif setting == "digest dialog":
            config.digest_dialog = value
        elif setting.startswith("margin plan "):
            config.margin_plan_pct[setting.removeprefix("margin plan ")] = number(value)
        elif setting == "web app":
            config.web_url = value
        else:
            raise AssertionError(f"unknown setting {setting!r}")


@given("the marketplaces and the analytics service report these daily sales:")
@when("the marketplaces and the analytics service report these daily sales:")
def marketplaces_report(world: World, datatable: list[list[str]]) -> None:
    for row in records(datatable):
        world.net.add_daily(
            row["channel"],
            row["sku"],
            day(row["from"]),
            day(row["to"]),
            daily_values(row),
        )


@given("the marketplace financial reports match the loaded sales")
def reports_match(world: World) -> None:
    world.net.reports = {"wb": MATCH_SALES, "ozon": MATCH_SALES}


@when("the morning run happens")
def morning_run(world: World) -> None:
    world.digest = world.pilot.morning()


@then(parsers.parse('the digest in "{dialog}" contains "{text}"'))
def digest_in_dialog(world: World, dialog: str, text: str) -> None:
    messages = [
        call["MESSAGE"]
        for call in world.net.calls("im.message.add")
        if call["DIALOG_ID"] == dialog
    ]
    assert messages, f"no message in {dialog}"
    assert text in messages[-1], messages[-1]


@when(parsers.parse("user {user:d} approves the proposal in the web app"))
def approves_in_web_app(world: World, user: int) -> None:
    with world.pilot.engine.connect() as conn:
        world.deviation_id = conn.execute(
            select(deviation.c.id).where(
                deviation.c.rule == "margin below plan",
                deviation.c.sku == "SKU-1001",
                deviation.c.channel == "ozon",
            )
        ).scalar_one()
    card = world.get(f"/deviations/{world.deviation_id}", user)
    form = card.select_one("form#approve-form")
    assert form is not None, "the card has no approve form"
    response = world.post(str(form["action"]), user, {})
    assert response.status_code == 303


@then(parsers.parse('a Bitrix24 task for user {user:d} is due "{deadline}"'))
def task_due(world: World, user: int, deadline: str) -> None:
    fields = world.net.calls("tasks.task.add")[-1]["fields"]
    assert (fields["RESPONSIBLE_ID"], fields["DEADLINE"]) == (user, deadline)


@when(parsers.parse("the manager completes the Bitrix24 task on {on_day}"))
def manager_completes(world: World, on_day: str) -> None:
    task_id = world.decision_row()["task_id"]
    world.net.tasks[task_id].update(status="5", closedDate=f"{on_day}T18:00:00+03:00")
    world.response = world.client.post(
        "/webhooks/bitrix24",
        data={
            "event": "ONTASKUPDATE",
            "data[FIELDS_AFTER][ID]": task_id,
            "auth[application_token]": APPLICATION_TOKEN,
        },
    )
    assert world.response.status_code == 200


@then(parsers.parse('the Bitrix24 task has the comment "{text}"'))
def task_comment(world: World, text: str) -> None:
    task_id = world.decision_row()["task_id"]
    assert {"TASKID": task_id, "FIELDS": {"POST_MESSAGE": text}} in world.net.calls(
        "task.commentitem.add"
    )


@then(parsers.parse('the decision journal shows the stages "{stages}"'))
def journal_stages(world: World, stages: str) -> None:
    assert ", ".join(str(event["stage"]) for event in journal_of(world)) == stages


@then(parsers.parse('the pilot scorecard shows the incremental margin "{amount}"'))
def scorecard_margin(world: World, amount: str) -> None:
    page = world.get("/scorecard", 1)
    assert amount in text_of(page).replace(" ", " ")
