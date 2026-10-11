"""Steps of ``features/02_unit_economics.feature``."""

from __future__ import annotations

from pytest_bdd import given, parsers, scenarios, then, when

from retail_ai_control import economics
from tests.bdd.support import World, daily_values, day, number, put_day, records

scenarios("02_unit_economics.feature")


@given(parsers.parse('"{sku}" sold on "{channel}" on {on_day}:'))
def sold(
    world: World, sku: str, channel: str, on_day: str, datatable: list[list[str]]
) -> None:
    with world.pilot.engine.begin() as conn:
        put_day(conn, channel, sku, day(on_day), daily_values(records(datatable)[0]))


@when(
    parsers.parse(
        'the unit economics of "{sku}" on "{channel}" on {on_day} are computed'
    )
)
def computed(world: World, sku: str, channel: str, on_day: str) -> None:
    with world.pilot.engine.connect() as conn:
        world.found["economics"] = economics.compute(conn, channel, sku, day(on_day))


@then(parsers.parse("the margin is {margin} and the margin rate is {rate}"))
def margin_is(world: World, margin: str, rate: str) -> None:
    result = world.found["economics"]
    assert result.margin == number(margin)
    if rate == "not defined":
        assert result.margin_pct is None
    else:
        assert round(result.margin_pct, 1) == number(rate)


@then("the cost shares of revenue are:")
def cost_shares(world: World, datatable: list[list[str]]) -> None:
    shares = world.found["economics"].shares()
    for row in records(datatable):
        assert round(shares[row["item"]], 1) == number(row["share"]), row["item"]
