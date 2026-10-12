"""Explain a deviation with SQL evidence and propose actions.

The rule-based analyst below always runs: it decomposes the margin by cost
item, compares the price with the other channel and proposes actions within
the limits. The AI agent (:mod:`retail_ai_control.agent`) may then replace
the explanation and the actions if its answer passes the guards. No
proposal is made while the data of the channel is not trusted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import select, update
from sqlalchemy.engine import Connection

from retail_ai_control import queries, rules
from retail_ai_control.config import CHANNEL_NAMES, Config
from retail_ai_control.decisions import create_decision
from retail_ai_control.fmt import number, pct
from retail_ai_control.mart import deviation, evidence
from retail_ai_control.reconcile import OK, channel_status

if TYPE_CHECKING:
    from retail_ai_control.pilot import Pilot

RULES_LABEL = "Расчёт по правилам"
AI_LABEL = "Сгенерировано AI"
DATA_CHECK = "data check required"
RECONCILIATION_PERIOD = "reconciliation period"
SHARE_COLUMNS = {
    "commission": "commission_pct",
    "logistics": "logistics_pct",
    "advertising": "advertising_pct",
    "cost of goods": "cogs_pct",
}
GENITIVE = {
    "commission": "комиссии",
    "logistics": "логистики",
    "advertising": "рекламы",
    "cost of goods": "себестоимости",
}


@dataclass
class Analysis:
    """The result of an analysis: evidence, figures, cause and proposal."""

    deviation: dict[str, Any]
    now_from: date
    now_to: date
    target_pct: float
    guardrail_pct: float
    evidence: dict[str, queries.Evidence] = field(default_factory=dict)
    figures: dict[str, dict[str, Any]] = field(default_factory=dict)
    shares: dict[str, tuple[Optional[float], Optional[float]]] = field(
        default_factory=dict
    )
    cause: Optional[str] = None
    price_gap_pct: Optional[float] = None
    other_channel: Optional[str] = None
    actions: list[dict[str, Any]] = field(default_factory=list)
    explanation: str = ""
    label: str = RULES_LABEL
    log: list[str] = field(default_factory=list)
    decision_id: Optional[int] = None

    def figure(self, name: str, value: Optional[float], source: str) -> None:
        """Keep a figure with the name of the query it comes from."""
        if value is not None:
            self.figures[name] = {"value": value, "evidence": source}

    def numbers(self) -> set[float]:
        """Every number the explanation may cite."""
        found = {round(abs(float(item["value"])), 1) for item in self.figures.values()}
        for item in self.evidence.values():
            found |= item.numbers()
        return found


def _price_gap(analysis: Analysis, rows: list[dict[str, Any]]) -> None:
    channel = analysis.deviation["channel"]
    prices = {row["channel"]: row["unit_price"] for row in rows if row["unit_price"]}
    for row_channel, price in prices.items():
        analysis.figure(f"price:{row_channel}", price, "price_by_channel")
    others = [other for other in prices if other != channel]
    if channel in prices and others:
        other = others[0]
        analysis.other_channel = other
        gap = round(100 * (prices[other] - prices[channel]) / prices[other], 1)
        analysis.price_gap_pct = gap
        analysis.figure("price gap", gap, "price_by_channel")


def _margin_actions(config: Config, analysis: Analysis) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if analysis.cause == "advertising":
        before = analysis.shares["advertising"][0]
        limit = config.ad_share_limit_pct
        share = before if before is not None and before <= limit else limit
        actions.append({"type": "set_ad_share", "value": share})
    gap = analysis.price_gap_pct
    if gap is not None and gap > 0:
        actions.append(
            {"type": "change_price", "value": round(min(gap, config.price_step_pct), 1)}
        )
    return actions


def _explain_margin(analysis: Analysis) -> str:
    before = analysis.figures.get("margin before", {}).get("value")
    now = analysis.figures.get("margin now", {}).get("value")
    if now is None:
        return f"{analysis.deviation['message']}."
    if before is None:
        text = f"Маржа за период — {pct(now)}"
    else:
        verb = "упала" if now < before else "изменилась"
        text = f"Маржа {verb} с {pct(before)} до {pct(now)}"
    if analysis.cause and before is not None:
        old, new = analysis.shares[analysis.cause]
        text += f": доля {GENITIVE[analysis.cause]} выросла с {pct(old or 0)} до {pct(new or 0)} выручки"
    text += "."
    gap, other = analysis.price_gap_pct, analysis.other_channel
    if gap and other:
        name, other_name = (
            CHANNEL_NAMES[analysis.deviation["channel"]],
            CHANNEL_NAMES[other],
        )
        side = "ниже" if gap > 0 else "выше"
        text += f" Цена на {name} на {pct(abs(gap))} {side}, чем на {other_name}."
    return text


def _decompose(conn: Connection, analysis: Analysis, before_from: date) -> None:
    dev = analysis.deviation
    breakdown = queries.run(
        conn,
        "margin_breakdown",
        channel=dev["channel"],
        sku=dev["sku"],
        before_from=before_from,
        now_from=analysis.now_from,
        now_to=analysis.now_to,
    )
    analysis.evidence["margin_breakdown"] = breakdown
    periods = {row["period"]: row for row in breakdown.rows}
    before, now = periods.get("before"), periods.get("now")
    analysis.figure(
        "margin before", before["margin_pct"] if before else None, "margin_breakdown"
    )
    analysis.figure(
        "margin now", now["margin_pct"] if now else None, "margin_breakdown"
    )
    best = 0.0
    for item, column in SHARE_COLUMNS.items():
        old = before[column] if before else None
        new = now[column] if now else None
        analysis.shares[item] = (old, new)
        analysis.figure(f"{item} before", old, "margin_breakdown")
        analysis.figure(f"{item} now", new, "margin_breakdown")
        if old is not None and new is not None and new - old > best:
            best, analysis.cause = new - old, item
    prices = queries.run(
        conn,
        "price_by_channel",
        sku=dev["sku"],
        date_from=analysis.now_from,
        date_to=analysis.now_to,
    )
    analysis.evidence["price_by_channel"] = prices
    _price_gap(analysis, prices.rows)


def _stockout(conn: Connection, config: Config, analysis: Analysis) -> None:
    dev = analysis.deviation
    sales = queries.run(
        conn,
        "sku_days",
        channel=dev["channel"],
        sku=dev["sku"],
        date_from=dev["window_start"],
        date_to=dev["window_end"],
    )
    stock = queries.run(conn, "latest_stock", on_day=dev["window_end"])
    analysis.evidence.update({"sku_days": sales, "latest_stock": stock})
    window = (dev["window_end"] - dev["window_start"]).days + 1
    per_day = round(sum(row["units"] for row in sales.rows) / window, 1)
    left = next(
        (
            row["stock"]
            for row in stock.rows
            if (row["channel"], row["sku"]) == (dev["channel"], dev["sku"])
        ),
        0,
    )
    units = rules.restock_units(config, per_day, left)
    analysis.figure("units per day", per_day, "sku_days")
    analysis.figure("stock", left, "latest_stock")
    analysis.actions = [{"type": "restock", "value": units}]
    analysis.explanation = (
        f"Продажи {number(per_day)} шт. в день, остаток {left} шт.: "
        f"чтобы хватило на {config.min_cover_days} дн., нужно {units} шт."
    )


def rule_analysis(
    conn: Connection,
    config: Config,
    dev: dict[str, Any],
    window: Optional[tuple[date, date]] = None,
) -> Analysis:
    """Analyse a deviation with SQL only; ``window`` overrides the period."""
    now_from, now_to = window or (dev["window_start"], dev["window_end"])
    before_from = dev["window_start"] - timedelta(config.baseline_days)
    plan = config.margin_plan(dev["sku"], dev["channel"])
    analysis = Analysis(dev, now_from, now_to, 0.0, config.guardrail_drop_pct)
    analysis.figure("impact", dev["impact"], "sku_days")
    if dev["rule"] == rules.STOCKOUT:
        _stockout(conn, config, analysis)
    else:
        _decompose(conn, analysis, before_from)
        if dev["rule"] in (rules.MARGIN, rules.ADVERTISING):
            analysis.actions = _margin_actions(config, analysis)
            analysis.explanation = _explain_margin(analysis)
        else:
            gap = analysis.price_gap_pct
            if gap is not None and gap < 0:
                change = round(max(gap, -config.price_step_pct), 1)
                analysis.actions = [{"type": "change_price", "value": change}]
            analysis.explanation = _explain_margin(analysis)
    if not analysis.actions:
        analysis.actions = [{"type": "review", "value": None}]
    baseline = analysis.figures.get(
        "margin before", analysis.figures.get("margin now", {})
    )
    if plan is not None and dev["rule"] == rules.MARGIN:
        analysis.target_pct = round(plan - config.target_gap_pp, 1)
    else:
        analysis.target_pct = float(baseline.get("value", 0.0))
    if "sku_days" not in analysis.evidence:
        stored = (
            conn.execute(
                select(evidence).where(
                    evidence.c.deviation_id == dev["id"], evidence.c.name == "sku_days"
                )
            )
            .mappings()
            .first()
        )
        if stored:
            analysis.evidence["sku_days"] = queries.Evidence(
                stored["name"],
                stored["sql"],
                stored["params"],
                stored["rows"],
                stored["id"],
            )
    return analysis


def _withhold(conn: Connection, pilot: Pilot, dev: dict[str, Any]) -> Optional[str]:
    status = channel_status(conn, dev["channel"])
    if status is not None and status != OK:
        return DATA_CHECK
    start = pilot.config.recommendations_from
    if start is not None and pilot.today() < start:
        return RECONCILIATION_PERIOD
    return None


def analyse(
    pilot: Pilot,
    deviation_id: int,
    window: Optional[tuple[date, date]] = None,
    parent_id: Optional[int] = None,
    target_pct: Optional[float] = None,
) -> Analysis:
    """Analyse a deviation and store the proposal, unless the data is not trusted."""
    with pilot.engine.begin() as conn:
        dev = dict(
            conn.execute(select(deviation).where(deviation.c.id == deviation_id))
            .mappings()
            .one()
        )
        reason = _withhold(conn, pilot, dev)
        if reason:
            conn.execute(
                update(deviation)
                .where(deviation.c.id == deviation_id)
                .values(note=reason)
            )
            analysis = Analysis(dev, dev["window_start"], dev["window_end"], 0.0, 0.0)
            analysis.log.append(f"no proposal: {reason}")
            return analysis
        analysis = rule_analysis(conn, pilot.config, dev, window)
    if target_pct is not None:
        analysis.target_pct = target_pct
    if pilot.agent is not None:
        pilot.agent.explain(analysis)
    with pilot.engine.begin() as conn:
        for item in analysis.evidence.values():
            if item.id is None:
                queries.save(conn, item, deviation_id)
        for figure in analysis.figures.values():
            source = analysis.evidence.get(figure["evidence"])
            figure["evidence_id"] = source.id if source else None
        analysis.decision_id = create_decision(conn, analysis, pilot.today(), parent_id)
        conn.execute(
            update(deviation).where(deviation.c.id == deviation_id).values(note="")
        )
    return analysis
