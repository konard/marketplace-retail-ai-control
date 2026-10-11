"""Steps of ``features/04_deviation_detection.feature``.

Margin rates are produced with one unit a day and no cost price, so the
commission is the only cost that sets the margin (unless advertising is
named).
"""

from __future__ import annotations

from datetime import timedelta

from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy import func, insert, select

from retail_ai_control.mart import deviation, stock_daily
from tests.bdd.conftest import DEVIATION
from tests.bdd.support import METABASE_SECRET, World, day, number, put_day, records

scenarios("04_deviation_detection.feature")

WEEK = 7
STOCKOUT_REVENUE = 5000.0


def put_rate(
    world: World, sku: str, channel: str, offset: int, revenue: float, rate: float
) -> None:
    """One unit sold ``offset`` days ago at a margin rate in percent."""
    with world.pilot.engine.begin() as conn:
        put_day(
            conn,
            channel,
            sku,
            world.today - timedelta(offset),
            {"units": 1, "revenue": revenue, "commission": revenue * (1 - rate / 100)},
        )


@given(
    parsers.parse(
        '"{sku}" on "{channel}" had daily revenue of {revenue}'
        " with these margin rates:"
    )
)
def margin_rates(
    world: World, sku: str, channel: str, revenue: str, datatable: list[list[str]]
) -> None:
    for row in records(datatable):
        offset = (world.today - day(row["day"])).days
        put_rate(
            world, sku, channel, offset, number(revenue), number(row["margin_pct"])
        )


@given(
    parsers.parse(
        '"{sku}" on "{channel}" sold {units:d} units a day for the last {count:d} days'
        " with a daily margin of {margin}"
    )
)
def steady_sales(
    world: World, sku: str, channel: str, units: int, count: int, margin: str
) -> None:
    with world.pilot.engine.begin() as conn:
        for offset in range(1, count + 1):
            put_day(
                conn,
                channel,
                sku,
                world.today - timedelta(offset),
                {
                    "units": units,
                    "revenue": STOCKOUT_REVENUE,
                    "commission": STOCKOUT_REVENUE - number(margin),
                },
            )


@given(parsers.parse("the minimum stock cover is {count:d} days"))
def min_cover(world: World, count: int) -> None:
    world.config.min_cover_days = count


@given(parsers.parse('the stock of "{sku}" on "{channel}" on {on_day} was {stock:d}'))
def stock_was(world: World, sku: str, channel: str, on_day: str, stock: int) -> None:
    with world.pilot.engine.begin() as conn:
        conn.execute(
            insert(stock_daily).values(
                channel=channel, sku=sku, day=day(on_day), stock=stock
            )
        )


@given(parsers.parse("the sales drop threshold is {threshold}%"))
def drop_threshold(world: World, threshold: str) -> None:
    world.config.sales_drop_pct = number(threshold)


@given(
    parsers.parse(
        '"{sku}" on "{channel}" had revenue of {revenue} at a {rate}% margin rate'
        " in the week before last"
    )
)
def week_before_last(
    world: World, sku: str, channel: str, revenue: str, rate: str
) -> None:
    world.found[f"rate {sku} {channel}"] = number(rate)
    for offset in range(WEEK + 1, 2 * WEEK + 1):
        put_rate(world, sku, channel, offset, number(revenue) / WEEK, number(rate))


@given(
    parsers.parse('"{sku}" on "{channel}" had revenue of {revenue} in the last week')
)
def last_week(world: World, sku: str, channel: str, revenue: str) -> None:
    rate = world.found[f"rate {sku} {channel}"]
    for offset in range(1, WEEK + 1):
        put_rate(world, sku, channel, offset, number(revenue) / WEEK, rate)


@given(parsers.parse("the advertising share limit is {limit}%"))
def ad_limit(world: World, limit: str) -> None:
    world.config.ad_share_limit_pct = number(limit)


@given(
    parsers.parse(
        '"{sku}" on "{channel}" spent {share}% of revenue {revenue} on advertising'
        " on each of the last {count:d} days at a {rate}% margin rate"
    )
)
def advertising(
    world: World,
    sku: str,
    channel: str,
    share: str,
    revenue: str,
    count: int,
    rate: str,
) -> None:
    amount = number(revenue)
    spend = amount * number(share) / 100
    with world.pilot.engine.begin() as conn:
        for offset in range(1, count + 1):
            put_day(
                conn,
                channel,
                sku,
                world.today - timedelta(offset),
                {
                    "units": 1,
                    "revenue": amount,
                    "commission": amount - spend - amount * number(rate) / 100,
                    "advertising": spend,
                },
            )


@when(
    parsers.re(
        r'Metabase posts an alert for the question "(?P<question>[^"]+)"'
        r" with (?P<secret>the correct|a wrong) secret"
    )
)
def metabase_alert(world: World, question: str, secret: str) -> None:
    token = METABASE_SECRET if secret == "the correct" else "wrong"
    world.response = world.client.post(
        "/webhooks/metabase",
        json={"type": "alert", "data": {"question_name": question}},
        headers={"Authorization": f"Bearer {token}"},
    )


def open_count(world: World, rule: str, sku: str, channel: str) -> int:
    """Open deviations of a rule for a SKU on a channel."""
    with world.pilot.engine.connect() as conn:
        found: int = conn.execute(
            select(func.count()).where(
                deviation.c.rule == rule,
                deviation.c.sku == sku,
                deviation.c.channel == channel,
                deviation.c.status == "open",
            )
        ).scalar_one()
    return found


@then(parsers.re("exactly (?P<count>\\d+) " + DEVIATION.removeprefix("an? ")))
def exactly(world: World, count: str, rule: str, sku: str, channel: str) -> None:
    assert open_count(world, rule, sku, channel) == int(count)


@then(parsers.re("no " + DEVIATION.removeprefix("an? ")))
def none_open(world: World, rule: str, sku: str, channel: str) -> None:
    assert open_count(world, rule, sku, channel) == 0


@then(parsers.parse('the deviation says "{message}"'))
def deviation_says(world: World, message: str) -> None:
    assert world.deviation_row()["message"] == message


@then(parsers.parse("the deviation impact is {impact}"))
def deviation_impact(world: World, impact: str) -> None:
    assert world.deviation_row()["impact"] == number(impact)


@then(parsers.parse("the webhook answers {status:d}"))
def webhook_answers(world: World, status: int) -> None:
    assert world.response is not None
    assert world.response.status_code == status


@then("no deviations are open")
def no_deviations(world: World) -> None:
    with world.pilot.engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(deviation)).scalar() == 0
