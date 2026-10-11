"""Load the sources into the data mart.

Each source loads in its own transaction: a failing source is recorded in
the sync report and the other sources still load. Facts are replaced for
the whole date range, so a recalculated marketplace report never doubles
the figures.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional

import httpx
from sqlalchemy import and_, delete, insert, select
from sqlalchemy.engine import Connection

from retail_ai_control.config import CHANNELS
from retail_ai_control.connectors import analytics_csv, ozon, wildberries
from retail_ai_control.mart import (
    ad_spend_daily,
    product,
    put_cost,
    replace_channel_facts,
    sales_daily,
    stock_daily,
    sync_run,
    unmapped,
)

if TYPE_CHECKING:
    from retail_ai_control.pilot import Pilot

logger = logging.getLogger(__name__)
SOURCE_ERRORS = (httpx.HTTPError, ValueError, KeyError, TypeError, OSError)


def _ids(conn: Connection, column: str) -> dict[str, str]:
    """Map a marketplace ID column of the catalog to the SKU."""
    rows = conn.execute(select(product.c.sku, product.c[column]))
    return {str(external): str(sku) for sku, external in rows if external}


def _replace_unmapped(
    conn: Connection, channel: str, first: date, last: date, rows: list[dict[str, Any]]
) -> None:
    conn.execute(
        delete(unmapped).where(
            and_(unmapped.c.channel == channel, unmapped.c.day.between(first, last))
        )
    )
    if rows:
        conn.execute(insert(unmapped), [{**row, "channel": channel} for row in rows])


def _load_onec(pilot: Pilot, first: date, last: date) -> int:
    client = pilot.onec
    assert client is not None
    products = client.products()
    sku_by_ref = {item["ref"]: item["sku"] for item in products}
    costs = client.costs(sku_by_ref)
    with pilot.engine.begin() as conn:
        for item in products:
            conn.execute(delete(product).where(product.c.sku == item["sku"]))
            values = {key: value for key, value in item.items() if key != "ref"}
            conn.execute(insert(product).values(**values))
        for cost in costs:
            put_cost(conn, cost["sku"], cost["valid_from"], cost["unit_cost"])
    return len(products) + len(costs)


def _load_wb(pilot: Pilot, first: date, last: date) -> int:
    client = pilot.wb
    assert client is not None
    with pilot.engine.connect() as conn:
        sku_by_nm_id = _ids(conn, "wb_nm_id")
    facts, lost = wildberries.daily_facts(client.sales_rows(first, last), sku_by_nm_id)
    stocks = client.stocks(sorted(sku_by_nm_id))
    _store(pilot, "wb", first, last, facts, lost, stocks, sku_by_nm_id)
    return len(facts)


def _load_ozon(pilot: Pilot, first: date, last: date) -> int:
    client = pilot.ozon
    assert client is not None
    with pilot.engine.connect() as conn:
        sku_by_ozon_sku = _ids(conn, "ozon_sku")
    facts, lost = ozon.daily_facts(client.accruals(first, last), sku_by_ozon_sku)
    stocks = client.stocks()
    _store(pilot, "ozon", first, last, facts, lost, stocks, sku_by_ozon_sku)
    return len(facts)


def _store(
    pilot: Pilot,
    channel: str,
    first: date,
    last: date,
    facts: list[dict[str, Any]],
    lost: list[dict[str, Any]],
    stocks: dict[str, int],
    sku_by_id: dict[str, str],
) -> None:
    stock_rows = [
        {"sku": sku_by_id[external], "day": last, "stock": stock}
        for external, stock in stocks.items()
        if external in sku_by_id
    ]
    with pilot.engine.begin() as conn:
        replace_channel_facts(conn, sales_daily, channel, first, last, facts)
        _replace_unmapped(conn, channel, first, last, lost)
        replace_channel_facts(conn, stock_daily, channel, last, last, stock_rows)


def _load_analytics(pilot: Pilot, first: date, last: date) -> int:
    rows = analytics_csv.read_spend(pilot.http, pilot.config.analytics_csv, first, last)
    with pilot.engine.begin() as conn:
        for channel in CHANNELS:
            own = [
                {key: value for key, value in row.items() if key != "channel"}
                for row in rows
                if row["channel"] == channel
            ]
            replace_channel_facts(conn, ad_spend_daily, channel, first, last, own)
    return len(rows)


def sync(pilot: Pilot, first: date, last: date) -> list[dict[str, Any]]:
    """Load every configured source for the date range; return the sync report."""
    loaders: list[tuple[str, Optional[object], Callable[[Pilot, date, date], int]]] = [
        ("1c", pilot.onec, _load_onec),
        ("wb", pilot.wb, _load_wb),
        ("ozon", pilot.ozon, _load_ozon),
        ("analytics", pilot.config.analytics_csv or None, _load_analytics),
    ]
    report = []
    for source, configured, load in loaders:
        if configured is None:
            continue
        try:
            rows = load(pilot, first, last)
            entry = {"source": source, "status": "loaded", "message": "", "rows": rows}
        except SOURCE_ERRORS as error:
            logger.warning("sync of %s failed: %s", source, error)
            entry = {
                "source": source,
                "status": "failed",
                "message": str(error),
                "rows": 0,
            }
        report.append(entry)
        with pilot.engine.begin() as conn:
            conn.execute(insert(sync_run).values(run_at=datetime.now(), **entry))  # noqa: DTZ005
    return report
