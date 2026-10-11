"""Steps of ``features/11_team_performance.feature``."""

from __future__ import annotations

from pytest_bdd import given, parsers, scenarios, then, when

from tests.bdd.support import World, add_decision, add_deviation, day, records, text_of

scenarios("11_team_performance.feature")

OWNER = 1


@given("these decision tasks exist:")
def decision_tasks(world: World, datatable: list[list[str]]) -> None:
    with world.pilot.engine.begin() as conn:
        for number, row in enumerate(records(datatable), start=1):
            completed = day(row["completed"]) if row["completed"] else None
            add_decision(
                conn,
                add_deviation(conn, sku=f"SKU-{9000 + number}", status="in work"),
                status="evaluated" if completed else "in progress",
                task_id=str(number),
                responsible_name=row["responsible"],
                deadline=day(row["deadline"]),
                completed_on=completed,
                outcome=row["outcome"] or None,
            )


@when("the team performance is calculated")
def calculated(world: World) -> None:
    world.found["team"] = world.pilot.team()


@when("the owner opens the team page")
def owner_opens(world: World) -> None:
    world.get("/team", OWNER)


@then("the team performance is:")
def performance(world: World, datatable: list[list[str]]) -> None:
    found = [
        [
            row["responsible"],
            str(row["tasks"]),
            f"{row['on_time_pct']}%",
            str(row["overdue"]),
            f"{row['achieved_pct']}%",
        ]
        for row in world.found["team"]
    ]
    assert found == datatable[1:]


@then(parsers.parse('the page shows a table with the caption "{caption}"'))
def caption(world: World, caption: str) -> None:
    assert world.page is not None
    assert [text_of(item) for item in world.page.select("table caption")] == [caption]


@then(parsers.parse('the row of "{name}" shows "{column}: {value}"'))
def row_shows(world: World, name: str, column: str, value: str) -> None:
    assert world.page is not None
    headers = [text_of(th) for th in world.page.select("thead th")]
    row = next(
        th.parent
        for th in world.page.select("tbody th[scope=row]")
        if text_of(th) == name
    )
    assert row is not None
    cells = [text_of(cell) for cell in row.find_all(["th", "td"])]
    assert cells[headers.index(column)] == value
