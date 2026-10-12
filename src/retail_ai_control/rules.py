"""Deviation rules: margin below plan, stockout risk, sales drop, advertising.

Rules look at full days up to yesterday. Each deviation keeps its window,
a message in Russian, the impact in rubles and the SQL evidence. An open
deviation is not raised again until it is closed or dismissed.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from retail_ai_control import queries
from retail_ai_control.config import Config
from retail_ai_control.fmt import pct, plural, signed_pct
from retail_ai_control.mart import as_date, days, deviation, new_id

if TYPE_CHECKING:
    from retail_ai_control.pilot import Pilot

MARGIN = "margin below plan"
STOCKOUT = "stockout risk"
SALES_DROP = "sales drop"
ADVERTISING = "advertising above limit"
ACTIVE = ("open", "in work")
STOCK_DAYS = 14

Series = dict[date, dict[str, Any]]


class Finding:
    """A deviation found by a rule, before it is stored."""

    def __init__(
        self,
        rule: str,
        key: tuple[str, str],
        window: tuple[date, date],
        message: str,
        impact: float,
    ) -> None:
        self.rule = rule
        self.channel, self.sku = key
        self.window_start, self.window_end = window
        self.message = message
        self.impact = round(impact, 2)


def _totals(series: Series, window: list[date]) -> Optional[dict[str, float]]:
    """Sum a window; ``None`` if a day has no revenue."""
    rows = [series.get(day) for day in window]
    if any(row is None or not row["revenue"] for row in rows):
        return None
    return {
        name: sum(float(row[name]) for row in rows if row is not None)
        for name in ("units", "revenue", "advertising", "margin")
    }


def margin_below_plan(
    config: Config, key: tuple[str, str], series: Series, yesterday: date
) -> Optional[Finding]:
    """The margin rate is below plan on each of the last ``margin_days`` days."""
    channel, sku = key
    plan = config.margin_plan(sku, channel)
    window = days(yesterday - timedelta(config.margin_days - 1), yesterday)
    totals = _totals(series, window)
    if plan is None or totals is None:
        return None
    rates = [100 * series[day]["margin"] / series[day]["revenue"] for day in window]
    if any(rate >= plan for rate in rates):
        return None
    rate = round(100 * totals["margin"] / totals["revenue"], 1)
    count = config.margin_days
    message = (
        f"Маржа {pct(rate)} при плане {pct(plan)} — "
        f"{count} {plural(count, 'день', 'дня', 'дней')} подряд"
    )
    impact = plan / 100 * totals["revenue"] - totals["margin"]
    return Finding(MARGIN, key, (window[0], yesterday), message, impact)


def stockout_risk(
    config: Config,
    key: tuple[str, str],
    series: Series,
    stock: Optional[int],
    yesterday: date,
) -> Optional[Finding]:
    """The stock covers fewer days of sales than the minimum."""
    window = days(yesterday - timedelta(STOCK_DAYS - 1), yesterday)
    units = sum(float(series[day]["units"]) for day in window if day in series)
    if stock is None or units <= 0:
        return None
    per_day = units / len(window)
    cover = round(stock / per_day)
    if cover >= config.min_cover_days:
        return None
    margin_per_day = sum(
        float(series[day]["margin"]) for day in window if day in series
    ) / len(window)
    message = f"Остатка хватит на {cover} дн. при норме {config.min_cover_days} дн."
    impact = (config.min_cover_days - cover) * margin_per_day
    return Finding(STOCKOUT, key, (window[0], yesterday), message, impact)


def sales_drop(
    config: Config, key: tuple[str, str], series: Series, yesterday: date
) -> Optional[Finding]:
    """Revenue of the last 7 days fell against the 7 days before."""
    week = config.baseline_days
    last = days(yesterday - timedelta(week - 1), yesterday)
    previous = days(last[0] - timedelta(week), last[0] - timedelta(1))
    now = sum(float(series[day]["revenue"]) for day in last if day in series)
    before = sum(float(series[day]["revenue"]) for day in previous if day in series)
    if before <= 0:
        return None
    change = round(100 * (now - before) / before, 1)
    if -change <= config.sales_drop_pct:
        return None
    margin_before = sum(
        float(series[day]["margin"]) for day in previous if day in series
    )
    days_word = plural(week, "день", "дня", "дней")
    message = f"Выручка за {week} {days_word} {signed_pct(change)} к прошлой неделе"
    impact = (before - now) * margin_before / before
    return Finding(SALES_DROP, key, (last[0], yesterday), message, impact)


def advertising_above_limit(
    config: Config, key: tuple[str, str], series: Series, yesterday: date
) -> Optional[Finding]:
    """The advertising share of revenue is above the limit."""
    window = days(yesterday - timedelta(config.margin_days - 1), yesterday)
    totals = _totals(series, window)
    if totals is None:
        return None
    share = round(100 * totals["advertising"] / totals["revenue"], 1)
    limit = config.ad_share_limit_pct
    if share <= limit:
        return None
    message = f"Реклама {pct(share)} выручки при лимите {pct(limit)}"
    impact = (share - limit) / 100 * totals["revenue"]
    return Finding(ADVERTISING, key, (window[0], yesterday), message, impact)


def _active(conn: Connection) -> set[tuple[str, str, str]]:
    rows = conn.execute(
        select(deviation.c.rule, deviation.c.channel, deviation.c.sku).where(
            deviation.c.status.in_(ACTIVE)
        )
    )
    return {(str(rule), str(channel), str(sku)) for rule, channel, sku in rows}


def run_rules(pilot: Pilot) -> list[int]:
    """Run every rule and store new deviations; return their IDs."""
    config = pilot.config
    today = pilot.today()
    yesterday = today - timedelta(1)
    first = yesterday - timedelta(max(STOCK_DAYS, 2 * config.baseline_days) - 1)
    created: list[int] = []
    with pilot.engine.begin() as conn:
        series: dict[tuple[str, str], Series] = defaultdict(dict)
        for row in queries.run(
            conn, "all_days", date_from=first, date_to=yesterday
        ).rows:
            series[row["channel"], row["sku"]][as_date(row["day"])] = row
        stocks = {
            (row["channel"], row["sku"]): int(row["stock"])
            for row in queries.run(conn, "latest_stock", on_day=yesterday).rows
        }
        active = _active(conn)
        for key in sorted(series):
            found = [
                margin_below_plan(config, key, series[key], yesterday),
                stockout_risk(config, key, series[key], stocks.get(key), yesterday),
                sales_drop(config, key, series[key], yesterday),
            ]
            if (MARGIN, *key) not in active and found[0] is None:
                found.append(
                    advertising_above_limit(config, key, series[key], yesterday)
                )
            for finding in found:
                if (
                    finding is None
                    or (finding.rule, finding.channel, finding.sku) in active
                ):
                    continue
                created.append(_store(conn, finding, today))
                active.add((finding.rule, finding.channel, finding.sku))
    return created


def _store(conn: Connection, finding: Finding, today: date) -> int:
    result = conn.execute(
        insert(deviation).values(
            rule=finding.rule,
            sku=finding.sku,
            channel=finding.channel,
            window_start=finding.window_start,
            window_end=finding.window_end,
            message=finding.message,
            impact=finding.impact,
            status="open",
            note="",
            detected_on=today,
        )
    )
    deviation_id = new_id(result)
    evidence = queries.run(
        conn,
        "sku_days",
        channel=finding.channel,
        sku=finding.sku,
        date_from=finding.window_start,
        date_to=finding.window_end,
    )
    queries.save(conn, evidence, deviation_id)
    return deviation_id


def restock_units(config: Config, units_per_day: float, stock: int) -> int:
    """Units to order so the stock covers the minimum number of days."""
    return max(0, math.ceil(config.min_cover_days * units_per_day - stock))
