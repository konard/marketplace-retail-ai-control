"""1C: the product catalog and cost prices through the standard OData interface.

Reference: https://its.1c.ru/db/v8323doc#bookmark:dev:TI000001358 (the
standard OData interface publishes catalogs and registers as
``{base}/{Entity}?$format=json``). Entity and field names come from
:class:`~retail_ai_control.config.OneCSettings`.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from retail_ai_control.config import OneCSettings


class OneCClient:
    """Reads the catalog and the cost register of 1C."""

    def __init__(self, http: httpx.Client, settings: OneCSettings) -> None:
        self.http = http
        self.settings = settings

    def _entity(self, name: str) -> list[dict[str, Any]]:
        response = self.http.get(
            f"{self.settings.url.rstrip('/')}/{name}",
            params={"$format": "json"},
            auth=(self.settings.user, self.settings.password),
        )
        response.raise_for_status()
        rows: list[dict[str, Any]] = response.json().get("value", [])
        return rows

    def products(self) -> list[dict[str, Any]]:
        """Return the catalog: SKU, name and marketplace IDs, keyed by ``Ref_Key``."""
        s = self.settings
        return [
            {
                "ref": row.get("Ref_Key", ""),
                "sku": str(row[s.sku_field]),
                "name": str(row.get(s.name_field) or ""),
                "wb_nm_id": str(row.get(s.wb_field) or "") or None,
                "ozon_sku": str(row.get(s.ozon_field) or "") or None,
            }
            for row in self._entity(s.products_entity)
            if row.get(s.sku_field)
        ]

    def costs(self, sku_by_ref: dict[str, str]) -> list[dict[str, Any]]:
        """Return the cost prices with the date they are valid from."""
        s = self.settings
        found = []
        for row in self._entity(s.costs_entity):
            sku = sku_by_ref.get(str(row.get(s.cost_product_field)))
            if sku:
                found.append(
                    {
                        "sku": sku,
                        "valid_from": date.fromisoformat(
                            str(row[s.cost_period_field])[:10]
                        ),
                        "unit_cost": float(row[s.cost_value_field]),
                    }
                )
        return found
