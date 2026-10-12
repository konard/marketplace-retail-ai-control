"""Named SQL queries. Every number people see comes from one of them.

A query result is kept as :class:`Evidence`: the SQL text, its parameters
and the result rows. The decision card links each figure to its evidence,
and the AI agent may only cite numbers that appear in evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Engine, insert
from sqlalchemy.engine import Connection

from retail_ai_control.mart import evidence, new_id, sql_text

QUERIES: dict[str, str] = {
    "sku_days": """
SELECT day, units, revenue, commission, logistics, advertising, cogs, margin,
       ROUND(100.0 * margin / NULLIF(revenue, 0), 1) AS margin_pct,
       ROUND(100.0 * advertising / NULLIF(revenue, 0), 1) AS advertising_pct
FROM unit_economics
WHERE channel = :channel AND sku = :sku AND day BETWEEN :date_from AND :date_to
ORDER BY day""",
    "all_days": """
SELECT channel, sku, day, units, revenue, advertising, margin
FROM unit_economics
WHERE day BETWEEN :date_from AND :date_to
ORDER BY channel, sku, day""",
    "latest_stock": """
SELECT s.channel, s.sku, s.day, s.stock
FROM stock_daily s
WHERE s.day = (SELECT MAX(t.day) FROM stock_daily t
               WHERE t.channel = s.channel AND t.sku = s.sku AND t.day <= :on_day)
ORDER BY s.channel, s.sku""",
    "margin_breakdown": """
SELECT CASE WHEN day < :now_from THEN 'before' ELSE 'now' END AS period,
       ROUND(SUM(revenue), 2) AS revenue,
       ROUND(SUM(margin), 2) AS margin,
       ROUND(100.0 * SUM(commission) / NULLIF(SUM(revenue), 0), 1) AS commission_pct,
       ROUND(100.0 * SUM(logistics) / NULLIF(SUM(revenue), 0), 1) AS logistics_pct,
       ROUND(100.0 * SUM(advertising) / NULLIF(SUM(revenue), 0), 1) AS advertising_pct,
       ROUND(100.0 * SUM(cogs) / NULLIF(SUM(revenue), 0), 1) AS cogs_pct,
       ROUND(100.0 * SUM(margin) / NULLIF(SUM(revenue), 0), 1) AS margin_pct
FROM unit_economics
WHERE channel = :channel AND sku = :sku AND day BETWEEN :before_from AND :now_to
GROUP BY 1
ORDER BY 1""",
    "price_by_channel": """
SELECT channel, SUM(units) AS units, ROUND(SUM(revenue), 2) AS revenue,
       ROUND(SUM(revenue) / NULLIF(SUM(units), 0), 2) AS unit_price
FROM sales_daily
WHERE sku = :sku AND day BETWEEN :date_from AND :date_to
GROUP BY channel
ORDER BY channel""",
    "margin_by_channel": """
SELECT channel, CASE WHEN day < :now_from THEN 'before' ELSE 'now' END AS period,
       ROUND(SUM(revenue), 2) AS revenue,
       ROUND(SUM(margin), 2) AS margin,
       ROUND(100.0 * SUM(margin) / NULLIF(SUM(revenue), 0), 1) AS margin_pct,
       ROUND(100.0 * SUM(advertising) / NULLIF(SUM(revenue), 0), 1) AS advertising_pct
FROM unit_economics
WHERE day BETWEEN :before_from AND :now_to
GROUP BY 1, 2
ORDER BY 1, 2""",
    "window_totals": """
SELECT COUNT(DISTINCT day) AS days, COALESCE(SUM(units), 0) AS units,
       ROUND(COALESCE(SUM(revenue), 0), 2) AS revenue,
       ROUND(COALESCE(SUM(margin), 0), 2) AS margin,
       ROUND(100.0 * SUM(margin) / NULLIF(SUM(revenue), 0), 1) AS margin_pct
FROM unit_economics
WHERE channel = :channel AND sku IN :skus AND day BETWEEN :date_from AND :date_to""",
    "channel_payout": """
SELECT ROUND(COALESCE(SUM(revenue - commission - logistics), 0), 2) AS payout
FROM sales_daily
WHERE channel = :channel AND day BETWEEN :date_from AND :date_to""",
}


@dataclass
class Evidence:
    """The SQL text, its parameters and the result rows."""

    name: str
    sql: str
    params: dict[str, Any]
    rows: list[dict[str, Any]] = field(default_factory=list)
    id: Optional[int] = None

    def numbers(self) -> set[float]:
        """Return every number in the rows, rounded to one decimal."""
        found: set[float] = set()
        for row in self.rows:
            for value in row.values():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    found.add(round(abs(float(value)), 1))
        return found


class QueryRefusedError(ValueError):
    """The SQL is not a single read-only query."""


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def run(conn: Connection, name: str, **params: Any) -> Evidence:
    """Run a named query and keep the result as evidence."""
    sql = QUERIES[name].strip()
    result = conn.execute(sql_text(sql, params)).mappings()
    rows = [{key: _plain(value) for key, value in row.items()} for row in result]
    plain = {key: _plain(value) for key, value in params.items()}
    return Evidence(name, sql, plain, rows)


def save(conn: Connection, item: Evidence, deviation_id: Optional[int]) -> Evidence:
    """Store evidence so a page can show it later."""
    result = conn.execute(
        insert(evidence).values(
            deviation_id=deviation_id,
            name=item.name,
            sql=item.sql,
            params=item.params,
            rows=item.rows,
        )
    )
    item.id = new_id(result)
    return item


_WRITE_FREE_START = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


def run_readonly_sql(engine: Engine, sql: str, max_rows: int = 200) -> Evidence:
    """Run SQL written by the AI agent; refuse anything but one SELECT.

    Two guards: the text must be one SELECT/WITH statement, and the database
    session is read-only, so a write hidden in a CTE fails as well.
    """
    statement = sql.strip().rstrip(";").strip()
    if ";" in statement or not _WRITE_FREE_START.match(statement):
        msg = "only one SELECT statement is allowed"
        raise QueryRefusedError(msg)
    sqlite = engine.dialect.name == "sqlite"
    with engine.connect() as conn:
        if sqlite:
            conn.exec_driver_sql("PRAGMA query_only = ON")
        else:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        try:
            result = conn.exec_driver_sql(statement).mappings()
            rows = [
                {key: _plain(value) for key, value in row.items()}
                for row in result.fetchmany(max_rows)
            ]
        except Exception as error:
            raise QueryRefusedError(str(error)) from error
        finally:
            conn.rollback()
            if sqlite:
                conn.exec_driver_sql("PRAGMA query_only = OFF")
    return Evidence("run_sql", statement, {}, rows)
