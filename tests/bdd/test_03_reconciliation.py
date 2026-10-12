"""Steps of ``features/03_reconciliation.feature``."""

from __future__ import annotations

from pytest_bdd import given, parsers, scenarios, then, when

from tests.bdd.support import World, day, number, put_day

scenarios("03_reconciliation.feature")


@given(parsers.parse("the reconciliation tolerance is {tolerance}%"))
def tolerance(world: World, tolerance: str) -> None:
    world.config.reconciliation_tolerance_pct = number(tolerance)


@given(
    parsers.parse(
        'the data mart has a computed "{channel}" payout of {payout}'
        " for {first} to {last}"
    )
)
def computed_payout(
    world: World, channel: str, payout: str, first: str, last: str
) -> None:
    del last  # one sale on the first day carries the whole payout
    with world.pilot.engine.begin() as conn:
        put_day(
            conn,
            channel,
            "SKU-1001",
            day(first),
            {"units": 1, "revenue": number(payout)},
        )


@given(
    parsers.parse(
        "the Ozon financial report shows a payout of {payout} for {first} to {last}"
    )
)
def reported_payout(world: World, payout: str, first: str, last: str) -> None:
    world.net.reports["ozon"] = [(day(first), day(last), number(payout))]


@given(parsers.parse("recommendations are enabled from {on_day}"))
def recommendations_from(world: World, on_day: str) -> None:
    world.config.recommendations_from = day(on_day)


@when(parsers.parse("the data is reconciled for {first} to {last}"))
def reconciled(world: World, first: str, last: str) -> None:
    world.found["reconciliation"] = world.pilot.reconcile(day(first), day(last))


@then(
    parsers.parse(
        'the "{channel}" reconciliation difference is {difference}'
        ' and the status is "{status}"'
    )
)
def difference(world: World, channel: str, difference: str, status: str) -> None:
    result = next(
        item for item in world.found["reconciliation"] if item["channel"] == channel
    )
    assert result["diff_pct"] == number(difference)
    assert result["status"] == status


@then(parsers.parse('no proposal is made and the deviation is marked "{note}"'))
def withheld(world: World, note: str) -> None:
    assert world.analysis is not None
    assert world.analysis.decision_id is None
    assert world.deviation_row()["note"] == note
