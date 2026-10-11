"""The example from the concept as demo data.

SKU-1001 sells on Ozon and Wildberries. For the last 3 days the advertising
share on Ozon rose from 9% to 21% of revenue, so the margin fell from 16% to
4% at a plan of 15%; the Wildberries stock lasts 8 days at a norm of 14.
``retail-ai-control demo`` loads it into an empty data mart.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import insert

from retail_ai_control.mart import (
    ad_spend_daily,
    days,
    product,
    put_cost,
    replace_channel_facts,
    sales_daily,
    stock_daily,
)

if TYPE_CHECKING:
    from retail_ai_control.pilot import Pilot

SKU = "SKU-1001"
BASELINE = (7, 3960.00)
RECENT = (3, 9240.00)
STOCK_WINDOW = 14


def load_demo(pilot: Pilot) -> list[int]:
    """Load the example up to yesterday, run the rules and analyse them."""
    today = pilot.today()
    last = today - timedelta(1)
    recent_from = last - timedelta(RECENT[0] - 1)
    first = recent_from - timedelta(BASELINE[0])
    stock_from = last - timedelta(STOCK_WINDOW - 1)
    ozon = [
        {
            "sku": SKU,
            "day": d,
            "units": 50,
            "revenue": 44000.0,
            "commission": 6600.0,
            "logistics": 4400.0,
        }
        for d in days(first, last)
    ]
    wb = [
        {
            "sku": SKU,
            "day": d,
            "units": 50,
            "revenue": 50000.0,
            "commission": 7500.0,
            "logistics": 5000.0,
        }
        for d in days(stock_from, last)
    ]
    spend = [
        {"sku": SKU, "day": d, "spend": RECENT[1] if d >= recent_from else BASELINE[1]}
        for d in days(first, last)
    ]
    with pilot.engine.begin() as conn:
        conn.execute(
            insert(product).values(
                sku=SKU, name="Кофемолка ручная", wb_nm_id="1001", ozon_sku="9001"
            )
        )
        put_cost(conn, SKU, stock_from.replace(day=1), 440.0)
        replace_channel_facts(conn, sales_daily, "ozon", first, last, ozon)
        replace_channel_facts(conn, sales_daily, "wb", stock_from, last, wb)
        replace_channel_facts(conn, ad_spend_daily, "ozon", first, last, spend)
        replace_channel_facts(
            conn,
            stock_daily,
            "wb",
            last,
            last,
            [{"sku": SKU, "day": last, "stock": 400}],
        )
    found = pilot.run_rules()
    pilot.analyse_open()
    return found
