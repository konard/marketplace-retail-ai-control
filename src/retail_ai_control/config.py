"""Pilot settings: thresholds, people, integrations.

Rates are in percent and their names end with ``_pct``. Every threshold of
the concept is a setting, so the owner can tune the loop without code.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, fields
from datetime import date
from pathlib import Path
from typing import Any, Optional

if sys.version_info >= (3, 11):  # pragma: no cover - depends on the interpreter
    import tomllib
else:  # pragma: no cover - depends on the interpreter
    import tomli as tomllib

CHANNELS = ("wb", "ozon")
CHANNEL_NAMES = {"wb": "WB", "ozon": "Ozon"}


@dataclass
class Person:
    """A Bitrix24 user."""

    user_id: int
    name: str = ""


@dataclass
class OneCSettings:
    """Standard OData interface of 1C and the field mapping of the catalog.

    The entity and field names depend on the 1C configuration and are fixed
    during requirements refinement; the defaults follow 1C:Trade Management.
    """

    url: str = ""
    user: str = ""
    password: str = ""
    products_entity: str = "Catalog_Номенклатура"
    sku_field: str = "Артикул"
    name_field: str = "Description"
    wb_field: str = "АртикулWB"
    ozon_field: str = "SKUOzon"
    costs_entity: str = "InformationRegister_СебестоимостьНоменклатуры"
    cost_product_field: str = "Номенклатура_Key"
    cost_period_field: str = "Period"
    cost_value_field: str = "Себестоимость"


@dataclass
class LLMSettings:
    """Any OpenAI-compatible chat completions endpoint.

    Examples: YandexGPT ``https://ai.api.cloud.yandex.net/v1``, GigaChat
    through the gpt2giga proxy, vLLM or Ollama in the company network.
    """

    base_url: str = ""
    model: str = ""
    api_key: str = ""
    project: str = ""
    max_tool_calls: int = 5


@dataclass
class Config:
    """All settings of the pilot. Load them with :func:`load_config`."""

    # Deviation rules
    margin_plan_pct: dict[str, float] = field(default_factory=dict)
    margin_days: int = 3
    baseline_days: int = 7
    ad_share_limit_pct: float = 15.0
    sales_drop_pct: float = 20.0
    min_cover_days: int = 14
    # Proposals and their limits
    price_change_max_pct: float = 10.0
    price_step_pct: float = 5.0
    target_gap_pp: float = 3.0
    guardrail_drop_pct: float = 10.0
    followup_days: int = 7
    # Tasks
    task_business_days: int = 2
    task_hour: int = 19
    timezone: str = "Europe/Moscow"
    holidays: list[date] = field(default_factory=list)
    # Data quality and the pilot
    reconciliation_tolerance_pct: float = 2.0
    recommendations_from: Optional[date] = None
    pilot_cost: float = 0.0
    approval_share_target_pct: float = 60.0
    lead_time_target_days: int = 2
    sync_lookback_days: int = 35
    # People
    approvers: list[int] = field(default_factory=list)
    channel_managers: dict[str, Person] = field(default_factory=dict)
    # Bitrix24, web app, webhooks
    bitrix_webhook_url: str = ""
    bitrix_application_token: str = ""
    digest_dialog: str = ""
    digest_max_items: int = 5
    web_url: str = "http://localhost:8000"
    dashboard_url: str = ""
    metabase_secret: str = ""
    # Sources
    database_url: str = "sqlite:///retail_ai_control.db"
    wb_token: str = ""
    wb_page_pause_seconds: float = 61.0
    ozon_client_id: str = ""
    ozon_api_key: str = ""
    onec: OneCSettings = field(default_factory=OneCSettings)
    analytics_csv: str = ""
    llm: LLMSettings = field(default_factory=LLMSettings)

    def margin_plan(self, sku: str, channel: str) -> Optional[float]:
        """Return the planned margin rate of a SKU on a channel, if any."""
        for key in (f"{sku}:{channel}", sku, f"*:{channel}"):
            if key in self.margin_plan_pct:
                return self.margin_plan_pct[key]
        return None

    def manager(self, channel: str) -> Person:
        """Return the person responsible for a channel."""
        if channel in self.channel_managers:
            return self.channel_managers[channel]
        return Person(self.approvers[0] if self.approvers else 1)


def _build(cls: Any, data: dict[str, Any]) -> Any:
    known = {f.name for f in fields(cls)}
    unknown = set(data) - known
    if unknown:
        msg = f"unknown settings: {', '.join(sorted(unknown))}"
        raise ValueError(msg)
    return cls(**data)


def load_config(path: Path) -> Config:
    """Read the settings from a TOML file (see ``examples/pilot.toml``)."""
    with path.open("rb") as handle:
        data: dict[str, Any] = tomllib.load(handle)
    data["onec"] = _build(OneCSettings, data.get("onec", {}))
    data["llm"] = _build(LLMSettings, data.get("llm", {}))
    managers = data.get("channel_managers", {})
    data["channel_managers"] = {
        channel: Person(int(person["user_id"]), str(person.get("name", "")))
        for channel, person in managers.items()
    }
    config: Config = _build(Config, data)
    return config
