"""Steps of ``features/15_decision_journal.feature``."""

from __future__ import annotations

from typing import Any

from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy import select

from retail_ai_control.mart import deviation
from tests.bdd.support import (
    ACTIONS,
    World,
    add_decision,
    add_deviation,
    day,
    labelled_field,
    number,
    page,
    plain,
    records,
)

scenarios("15_decision_journal.feature")

OWNER = 1
JOURNAL = "/decisions"


def action_of(text: str) -> dict[str, Any]:
    """Read ``change price +3.0%`` into a decision action."""
    name = next(name for name in ACTIONS if text.startswith(name))
    return {"type": ACTIONS[name], "value": number(text[len(name) :])}


@given("these decisions were made:")
def decisions_made(world: World, datatable: list[list[str]]) -> None:
    with world.pilot.engine.begin() as conn:
        for row in records(datatable):
            decided = day(row["decided on"])
            actions = [action_of(row["actions"])]
            add_decision(
                conn,
                add_deviation(conn, sku=row["sku"], channel=row["channel"]),
                status=row["status"],
                proposed_actions=actions,
                actions=actions,
                approved_by=int(row["approved by"]),
                decided_on=decided,
                created_on=decided,
                outcome=row["outcome"] or None,
                incremental_margin=number(row["incremental margin"])
                if row["incremental margin"]
                else None,
            )


@when("the owner opens the decision journal")
def opens_journal(world: World) -> None:
    world.get(JOURNAL, OWNER)
    assert world.response is not None
    assert world.response.status_code == 200


@when(parsers.parse("the owner opens the decision journal from {first} to {last}"))
def opens_period(world: World, first: str, last: str) -> None:
    world.get(f"{JOURNAL}?from={first}&to={last}", OWNER)


@then(parsers.parse("the period is {first} to {last}"))
def period(world: World, first: str, last: str) -> None:
    assert labelled_field(world, "С").get("value") == first
    assert labelled_field(world, "По").get("value") == last


def journal_rows(world: World) -> list[list[str]]:
    """The cells of the journal table, row by row."""
    return [
        [plain(cell) for cell in row.find_all(["th", "td"])]
        for row in page(world).select("table#journal tbody tr")
    ]


@then("the journal lists:")
def journal_lists(world: World, datatable: list[list[str]]) -> None:
    headers = [plain(th) for th in page(world).select("table#journal thead th")]
    columns = [headers.index(name) for name in datatable[0]]
    found = [[row[index] for index in columns] for row in journal_rows(world)]
    assert found == datatable[1:]


@then(parsers.parse('the journal lists the SKUs "{skus}"'))
def journal_skus(world: World, skus: str) -> None:
    headers = [plain(th) for th in page(world).select("table#journal thead th")]
    column = headers.index("Товар")
    assert [row[column] for row in journal_rows(world)] == skus.split(", ")


@then(parsers.parse('the journal summary is "{text}"'))
def journal_summary(world: World, text: str) -> None:
    summary = page(world).select_one("#journal-summary")
    assert summary is not None, "the journal has no summary"
    assert plain(summary) == text


@then(parsers.parse('the row of "{sku}" links to its decision card'))
def row_link(world: World, sku: str) -> None:
    link = next(
        item
        for item in page(world).select("table#journal tbody a")
        if plain(item) == sku
    )
    with world.pilot.engine.connect() as conn:
        deviation_id: int = conn.execute(
            select(deviation.c.id).where(deviation.c.sku == sku)
        ).scalar_one()
    assert link["href"] == f"/deviations/{deviation_id}"


@then("the journal is empty")
def journal_empty(world: World) -> None:
    assert journal_rows(world) == []
