"""Steps of ``features/01_data_collection.feature``."""

from __future__ import annotations

from typing import Any

from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy import func, select

from retail_ai_control.mart import (
    cost_price,
    day_facts,
    sales_daily,
    stock_daily,
    unmapped,
)
from tests.bdd.support import World, day, number, records

scenarios("01_data_collection.feature")

WB_NUMBERS = {"quantity": int, "nmId": int}


def wb_rows(datatable: list[list[str]]) -> list[dict[str, Any]]:
    """Rows of the Wildberries detailed report with JSON types."""
    rows = []
    for row in records(datatable):
        converted: dict[str, Any] = dict(row)
        for name in ("retailAmount", "forPay", "deliveryService"):
            converted[name] = number(row[name])
        for name, kind in WB_NUMBERS.items():
            converted[name] = kind(row[name])
        rows.append(converted)
    return rows


@given("the Wildberries sales report details contain:")
@when("the marketplace recalculates the report to:")
def wb_report(world: World, datatable: list[list[str]]) -> None:
    world.net.wb_rows = wb_rows(datatable)


@given("the Ozon accruals for the day contain:")
def ozon_accruals(world: World, datatable: list[list[str]]) -> None:
    world.net.ozon_accruals = [
        {
            "date": row["date"],
            "accrued_category": row["accrued_category"],
            "posting": {
                "posting_number": row["unit_number"],
                "products": [
                    {
                        "sku": int(row["sku"]),
                        "commission": {
                            "sale_amount": number(row["sale_amount"]),
                            "commission": number(row["commission"]),
                        },
                        "delivery": {"total_accrued": number(row["delivery_total"])},
                    }
                ],
            },
        }
        for row in records(datatable)
    ]


@given("the analytics service export contains:")
def analytics_export(world: World, datatable: list[list[str]]) -> None:
    world.net.analytics_rows = records(datatable)


@given(parsers.parse("the marketplaces report stock on {on_day}:"))
def marketplace_stock(world: World, on_day: str, datatable: list[list[str]]) -> None:
    world.today = day(on_day)
    for row in records(datatable):
        product = world.net.product(row["sku"])
        if row["channel"] == "wb":
            world.net.wb_stock[product["АртикулWB"]] = int(row["stock"])
        else:
            world.net.ozon_stock[product["SKUOzon"]] = int(row["stock"])


@given("the Ozon API answers with HTTP 503")
def ozon_down(world: World) -> None:
    world.net.ozon_down = True


@given(parsers.parse("the data was synchronized for {on_day}"))
@when(parsers.parse("the data is synchronized for {on_day}"))
def synchronized(world: World, on_day: str) -> None:
    world.sync_report = world.pilot.sync(day(on_day), day(on_day))


@then(parsers.parse('the data mart contains for "{sku}" on "{channel}" on {on_day}:'))
def mart_contains(
    world: World, sku: str, channel: str, on_day: str, datatable: list[list[str]]
) -> None:
    with world.pilot.engine.connect() as conn:
        facts = day_facts(conn, channel, sku, day(on_day))
    assert facts is not None, f"no facts for {sku} on {channel}"
    for name, expected in records(datatable)[0].items():
        assert float(facts[name]) == number(expected), name


@then(parsers.parse('the unit cost of "{sku}" on {on_day} is {cost}'))
def unit_cost_on(world: World, sku: str, on_day: str, cost: str) -> None:
    with world.pilot.engine.connect() as conn:
        found = conn.execute(
            select(cost_price.c.unit_cost)
            .where(cost_price.c.sku == sku, cost_price.c.valid_from <= day(on_day))
            .order_by(cost_price.c.valid_from.desc())
        ).scalar()
    assert found == number(cost)


@then(parsers.parse('the stock of "{sku}" on "{channel}" on {on_day} is {stock:d}'))
def stock_on(world: World, sku: str, channel: str, on_day: str, stock: int) -> None:
    with world.pilot.engine.connect() as conn:
        found = conn.execute(
            select(stock_daily.c.stock).where(
                stock_daily.c.channel == channel,
                stock_daily.c.sku == sku,
                stock_daily.c.day == day(on_day),
            )
        ).scalar()
    assert found == stock


@then(
    parsers.parse(
        'the data mart has exactly {count:d} fact for "{sku}" on "{channel}" on {on_day}'
    )
)
def fact_count(world: World, count: int, sku: str, channel: str, on_day: str) -> None:
    with world.pilot.engine.connect() as conn:
        found = conn.execute(
            select(func.count()).where(
                sales_daily.c.channel == channel,
                sales_daily.c.sku == sku,
                sales_daily.c.day == day(on_day),
            )
        ).scalar()
    assert found == count


@then(
    parsers.parse(
        'the data quality report lists unmapped ID "{external_id}" on "{channel}"'
        " with revenue {revenue}"
    )
)
def unmapped_row(world: World, external_id: str, channel: str, revenue: str) -> None:
    with world.pilot.engine.connect() as conn:
        rows = conn.execute(
            select(unmapped.c.revenue).where(
                unmapped.c.channel == channel, unmapped.c.external_id == external_id
            )
        ).all()
    assert [float(row.revenue) for row in rows] == [number(revenue)]


@then(parsers.parse('the sync report shows "{source}" as failed with "{text}"'))
def sync_failed(world: World, source: str, text: str) -> None:
    entry = next(item for item in world.sync_report if item["source"] == source)
    assert entry["status"] == "failed"
    assert text in entry["message"]


@then(parsers.parse('the sync report shows "{source}" as loaded'))
def sync_loaded(world: World, source: str) -> None:
    entry = next(item for item in world.sync_report if item["source"] == source)
    assert entry["status"] == "loaded", entry["message"]
