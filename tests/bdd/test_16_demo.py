"""Steps of ``features/16_demo.feature``."""

from __future__ import annotations

from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy import select

from retail_ai_control.demo import load_demo
from retail_ai_control.mart import decision, deviation
from retail_ai_control.metrics import NO_DATA
from tests.bdd.support import World, page, plain

scenarios("16_demo.feature")

VISITOR = 1
PAGES = {
    "decision journal": "/decisions",
    "team page": "/team",
    "scorecard page": "/scorecard",
}


@given("the demo data is loaded")
def demo_loaded(world: World) -> None:
    load_demo(world.pilot)


@then("every open deviation has a proposal")
def every_proposal(world: World) -> None:
    with world.pilot.engine.connect() as conn:
        open_ids: set[int] = set(
            conn.execute(
                select(deviation.c.id).where(deviation.c.status == "open")
            ).scalars()
        )
        proposed: set[int] = set(
            conn.execute(
                select(decision.c.deviation_id).where(decision.c.status == "proposed")
            ).scalars()
        )
    assert open_ids
    assert open_ids <= proposed


def decisions_of(world: World, sku: str) -> list[dict[str, object]]:
    """The decisions of a SKU, oldest first."""
    with world.pilot.engine.connect() as conn:
        rows = conn.execute(
            select(decision)
            .join(deviation, deviation.c.id == decision.c.deviation_id)
            .where(deviation.c.sku == sku)
            .order_by(decision.c.id)
        )
        return [dict(row) for row in rows.mappings()]


@then(
    parsers.parse(
        'the decision for "{sku}" on "{channel}" is "{status}"'
        ' with the outcome "{outcome}"'
    )
)
def decision_outcome(
    world: World, sku: str, channel: str, status: str, outcome: str
) -> None:
    first = decisions_of(world, sku)[0]
    assert (first["status"], first["outcome"]) == (status, outcome)


@then(parsers.parse('the new proposal for "{sku}" follows the evaluated decision'))
def proposal_follows(world: World, sku: str) -> None:
    evaluated, proposal = decisions_of(world, sku)
    assert proposal["status"] == "proposed"
    assert proposal["parent_id"] == evaluated["id"]
    assert proposal["deviation_id"] == evaluated["deviation_id"]


@when(parsers.parse("the visitor opens the {name}"))
def visitor_opens(world: World, name: str) -> None:
    world.get(PAGES[name], VISITOR)
    assert world.response is not None
    assert world.response.status_code == 200


@then(parsers.parse('the journal summary is "{text}"'))
def journal_summary(world: World, text: str) -> None:
    summary = page(world).select_one("#journal-summary")
    assert summary is not None, "the journal has no summary"
    assert plain(summary) == text


@then("the team table lists:")
def team_table(world: World, datatable: list[list[str]]) -> None:
    rows = [
        [plain(cell) for cell in row.find_all(["th", "td"])]
        for row in page(world).select("table tr")
    ]
    assert rows == datatable


@then("every criterion of the scorecard has a measured value")
def scorecard_measured(world: World) -> None:
    actual = [
        plain(row.find_all("td")[1]) for row in page(world).select("table tbody tr")
    ]
    assert len(actual) == 4
    assert NO_DATA not in actual, actual
