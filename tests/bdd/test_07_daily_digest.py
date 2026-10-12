"""Steps of ``features/07_daily_digest.feature``."""

from __future__ import annotations

import re
from datetime import timedelta

from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy import select

from retail_ai_control.mart import deviation
from tests.bdd.support import World, add_decision, add_deviation, day, number, records

scenarios("07_daily_digest.feature")

ITEM = re.compile(r"^\d+\. (\S+) ·", re.MULTILINE)


@given(parsers.parse('the digest is sent to the Bitrix24 dialog "{dialog}"'))
def digest_dialog(world: World, dialog: str) -> None:
    world.config.digest_dialog = dialog


@given(parsers.parse("the digest shows at most {count:d} deviations"))
def digest_size(world: World, count: int) -> None:
    world.config.digest_max_items = count


@given("these deviations are open:")
def open_deviations(world: World, datatable: list[list[str]]) -> None:
    with world.pilot.engine.begin() as conn:
        for row in records(datatable):
            add_deviation(
                conn,
                rule=row["rule"],
                sku=row["sku"],
                channel=row["channel"],
                impact=number(row["impact"]),
                message=row.get("summary") or row["rule"],
            )


@given(
    parsers.parse(
        'a decision for "{sku}" on "{channel}" was evaluated as "{outcome}"'
        ' with the result "{text}"'
    )
)
def evaluated(world: World, sku: str, channel: str, outcome: str, text: str) -> None:
    with world.pilot.engine.begin() as conn:
        deviation_id = add_deviation(conn, sku=sku, channel=channel)
        add_decision(
            conn,
            deviation_id,
            status="evaluated",
            outcome=outcome,
            result_text=text,
            evaluated_on=world.today,
        )


@given(
    parsers.parse(
        'the task "{title}" of "{name}" was due on {deadline} and is not completed'
    )
)
def overdue_task(world: World, title: str, name: str, deadline: str) -> None:
    with world.pilot.engine.begin() as conn:
        deviation_id = add_deviation(
            conn, sku="SKU-3001", channel="wb", status="in work", impact=1000.0
        )
        add_decision(
            conn,
            deviation_id,
            status="in progress",
            task_id="777",
            task_title=title,
            responsible_name=name,
            deadline=day(deadline),
            decided_on=day(deadline) - timedelta(2),
        )


@when("the morning digest is built")
def digest_built(world: World) -> None:
    world.digest = world.pilot.digest()


@when("the morning digest is sent")
def digest_sent(world: World) -> None:
    world.digest = world.pilot.send_digest()


@then("the digest lists these SKUs in order:")
def skus_in_order(world: World, datatable: list[list[str]]) -> None:
    assert ITEM.findall(world.digest) == [row["sku"] for row in records(datatable)]


@then(parsers.parse('the digest contains "{text}"'))
def digest_contains(world: World, text: str) -> None:
    assert text in world.digest, world.digest


@then(
    parsers.parse('the digest links to the decision card of the deviation for "{sku}"')
)
def digest_link(world: World, sku: str) -> None:
    with world.pilot.engine.connect() as conn:
        deviation_id: int = conn.execute(
            select(deviation.c.id).where(deviation.c.sku == sku)
        ).scalar_one()
    assert f"{world.config.web_url}/deviations/{deviation_id}" in world.digest


@then(parsers.parse('Bitrix24 receives "{method}" with DIALOG_ID "{dialog}"'))
def bitrix_dialog(world: World, method: str, dialog: str) -> None:
    calls = world.net.calls(method)
    assert [call["DIALOG_ID"] for call in calls] == [dialog]
    assert calls[0]["MESSAGE"] == world.digest


@then(parsers.parse('the message starts with "{text}"'))
def message_starts(world: World, text: str) -> None:
    assert world.net.calls("im.message.add")[-1]["MESSAGE"].startswith(text)
