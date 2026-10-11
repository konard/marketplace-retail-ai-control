"""Unit economics of a SKU on a channel for a day.

Margin = revenue - commission - logistics - advertising - units x unit cost,
where the unit cost is the 1C cost price valid on the sale date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy.engine import Connection

from retail_ai_control.mart import day_facts

COST_ITEMS = {
    "commission": "commission",
    "logistics": "logistics",
    "advertising": "advertising",
    "cost of goods": "cogs",
    "margin": "margin",
}


@dataclass
class UnitEconomics:
    """The figures of one SKU-day from the ``unit_economics`` view."""

    units: int
    revenue: float
    commission: float
    logistics: float
    advertising: float
    cogs: float
    margin: float

    @property
    def margin_pct(self) -> Optional[float]:
        """The margin as a share of revenue; undefined without revenue."""
        if not self.revenue:
            return None
        return round(100 * self.margin / self.revenue, 1)

    def shares(self) -> dict[str, Optional[float]]:
        """Each cost item and the margin as a percentage of revenue."""
        return {
            item: round(100 * getattr(self, column) / self.revenue, 1)
            if self.revenue
            else None
            for item, column in COST_ITEMS.items()
        }


def compute(conn: Connection, channel: str, sku: str, on_day: date) -> UnitEconomics:
    """Read the unit economics of one SKU-day; zeros when nothing was sold."""
    row = day_facts(conn, channel, sku, on_day) or {}
    return UnitEconomics(
        units=int(row.get("units") or 0),
        revenue=float(row.get("revenue") or 0),
        commission=float(row.get("commission") or 0),
        logistics=float(row.get("logistics") or 0),
        advertising=float(row.get("advertising") or 0),
        cogs=float(row.get("cogs") or 0),
        margin=float(row.get("margin") or 0),
    )
