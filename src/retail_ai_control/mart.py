"""The data mart: one schema for facts, deviations and decisions.

Facts are stored per channel x SKU x day. The ``unit_economics`` view joins
sales, advertising and the cost price valid on the day, so every later step
reads the same margin. SQLite is enough for the pilot; the same schema runs
on PostgreSQL by changing ``database_url``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Engine,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    and_,
    bindparam,
    create_engine,
    delete,
    insert,
    select,
    text,
)
from sqlalchemy.engine import Connection, CursorResult
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.elements import BindParameter, TextClause

metadata = MetaData()


def _money(name: str, *, nullable: bool = False) -> Column[Any]:
    return Column(name, Numeric(14, 2, asdecimal=False), nullable=nullable)


product = Table(
    "product",
    metadata,
    Column("sku", String(64), primary_key=True),
    Column("name", String(255), nullable=False, default=""),
    Column("wb_nm_id", String(32)),
    Column("ozon_sku", String(32)),
)
cost_price = Table(
    "cost_price",
    metadata,
    Column("sku", String(64), primary_key=True),
    Column("valid_from", Date, primary_key=True),
    _money("unit_cost"),
)
sales_daily = Table(
    "sales_daily",
    metadata,
    Column("channel", String(16), primary_key=True),
    Column("sku", String(64), primary_key=True),
    Column("day", Date, primary_key=True),
    Column("units", Integer, nullable=False),
    _money("revenue"),
    _money("commission"),
    _money("logistics"),
)
ad_spend_daily = Table(
    "ad_spend_daily",
    metadata,
    Column("channel", String(16), primary_key=True),
    Column("sku", String(64), primary_key=True),
    Column("day", Date, primary_key=True),
    _money("spend"),
)
stock_daily = Table(
    "stock_daily",
    metadata,
    Column("channel", String(16), primary_key=True),
    Column("sku", String(64), primary_key=True),
    Column("day", Date, primary_key=True),
    Column("stock", Integer, nullable=False),
)
unmapped = Table(
    "unmapped",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("channel", String(16), nullable=False),
    Column("external_id", String(64), nullable=False),
    Column("day", Date, nullable=False),
    _money("revenue"),
)
reconciliation = Table(
    "reconciliation",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("channel", String(16), nullable=False),
    Column("date_from", Date, nullable=False),
    Column("date_to", Date, nullable=False),
    _money("computed"),
    _money("reported", nullable=True),
    Column("diff_pct", Numeric(8, 2, asdecimal=False)),
    Column("status", String(32), nullable=False),
    Column("checked_on", Date, nullable=False),
)
sync_run = Table(
    "sync_run",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_at", DateTime, nullable=False),
    Column("source", String(32), nullable=False),
    Column("status", String(16), nullable=False),
    Column("message", Text, nullable=False, default=""),
    Column("rows", Integer, nullable=False, default=0),
)
deviation = Table(
    "deviation",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("rule", String(64), nullable=False),
    Column("sku", String(64), nullable=False),
    Column("channel", String(16), nullable=False),
    Column("window_start", Date, nullable=False),
    Column("window_end", Date, nullable=False),
    Column("message", Text, nullable=False),
    _money("impact"),
    Column("status", String(32), nullable=False, default="open"),
    Column("note", String(64), nullable=False, default=""),
    Column("detected_on", Date, nullable=False),
)
evidence = Table(
    "evidence",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("deviation_id", Integer),
    Column("name", String(64), nullable=False),
    Column("sql", Text, nullable=False),
    Column("params", JSON, nullable=False),
    Column("rows", JSON, nullable=False),
)
decision = Table(
    "decision",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("deviation_id", Integer, nullable=False),
    Column("parent_id", Integer),
    Column("status", String(32), nullable=False),
    Column("proposed_actions", JSON, nullable=False),
    Column("actions", JSON, nullable=False),
    Column("explanation", Text, nullable=False, default=""),
    Column("label", String(64), nullable=False, default=""),
    Column("cause", String(32)),
    Column("figures", JSON, nullable=False),
    Column("target_pct", Numeric(8, 2, asdecimal=False), nullable=False),
    Column("guardrail_pct", Numeric(8, 2, asdecimal=False), nullable=False),
    Column("significant_edit", Boolean),
    Column("approved_by", Integer),
    Column("decided_on", Date),
    Column("reject_reason", Text),
    Column("task_id", String(32)),
    Column("task_title", Text),
    Column("responsible_id", Integer),
    Column("responsible_name", String(255)),
    Column("deadline", Date),
    Column("completed_on", Date),
    Column("followup_due", Date),
    Column("outcome", String(32)),
    Column("result_text", Text),
    _money("incremental_margin", nullable=True),
    Column("evaluated_on", Date),
    Column("created_on", Date, nullable=False),
)
decision_event = Table(
    "decision_event",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("decision_id", Integer, nullable=False),
    Column("stage", String(32), nullable=False),
    Column("user_id", Integer),
    Column("note", Text, nullable=False, default=""),
    Column("on_day", Date, nullable=False),
)

_COST_ON_DAY = (
    "COALESCE((SELECT c.unit_cost FROM cost_price c WHERE c.sku = g.sku"
    " AND c.valid_from <= g.day ORDER BY c.valid_from DESC LIMIT 1), 0)"
)
UNIT_ECONOMICS_VIEW = f"""
SELECT e.*, e.revenue - e.commission - e.logistics - e.advertising - e.cogs AS margin
FROM (
  SELECT g.*, g.units * {_COST_ON_DAY} AS cogs
  FROM (
    SELECT f.channel, f.sku, f.day,
           SUM(f.units) AS units, SUM(f.revenue) AS revenue,
           SUM(f.commission) AS commission, SUM(f.logistics) AS logistics,
           SUM(f.advertising) AS advertising
    FROM (
      SELECT channel, sku, day, units, revenue, commission, logistics,
             0 AS advertising
      FROM sales_daily
      UNION ALL
      SELECT channel, sku, day, 0, 0, 0, 0, spend FROM ad_spend_daily
    ) f
    GROUP BY f.channel, f.sku, f.day
  ) g
) e
"""


def sql_text(query: str, params: dict[str, Any]) -> TextClause:
    """Build a text query with typed parameters (dates, lists for ``IN``)."""
    binds: list[BindParameter[Any]] = []
    for name, value in params.items():
        if isinstance(value, (list, tuple)):
            binds.append(bindparam(name, list(value), expanding=True))
        elif isinstance(value, date):
            binds.append(bindparam(name, value, type_=Date))
        else:
            binds.append(bindparam(name, value))
    return text(query).bindparams(*binds)


def new_id(result: CursorResult[Any]) -> int:
    """The primary key of the row an ``INSERT`` created."""
    key = result.inserted_primary_key
    if not key:
        msg = "the insert returned no primary key"
        raise RuntimeError(msg)
    return int(key[0])


def as_date(value: Any) -> date:
    """Read a date column of a text query (SQLite returns strings)."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def make_engine(url: str) -> Engine:
    """Create the engine; an in-memory SQLite database is shared by threads."""
    if url in {"sqlite://", "sqlite:///:memory:"}:
        return create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(url)


def create_schema(engine: Engine) -> None:
    """Create the tables and the ``unit_economics`` view if they are missing."""
    metadata.create_all(engine)
    create = (
        "CREATE VIEW IF NOT EXISTS"
        if engine.dialect.name == "sqlite"
        else "CREATE OR REPLACE VIEW"
    )
    with engine.begin() as conn:
        conn.execute(text(f"{create} unit_economics AS {UNIT_ECONOMICS_VIEW}"))


def days(first: date, last: date) -> list[date]:
    """Return every day from ``first`` to ``last`` inclusive."""
    return [first + timedelta(n) for n in range((last - first).days + 1)]


def replace_channel_facts(
    conn: Connection,
    table: Table,
    channel: str,
    first: date,
    last: date,
    rows: list[dict[str, Any]],
) -> None:
    """Replace the facts of one channel in a date range (safe to reload)."""
    conn.execute(
        delete(table).where(
            and_(table.c.channel == channel, table.c.day.between(first, last))
        )
    )
    if rows:
        conn.execute(insert(table), [{**row, "channel": channel} for row in rows])


def put_cost(conn: Connection, sku: str, valid_from: date, unit_cost: float) -> None:
    """Insert or replace a cost price."""
    conn.execute(
        delete(cost_price).where(
            and_(cost_price.c.sku == sku, cost_price.c.valid_from == valid_from)
        )
    )
    conn.execute(
        insert(cost_price).values(sku=sku, valid_from=valid_from, unit_cost=unit_cost)
    )


def day_facts(
    conn: Connection, channel: str, sku: str, on_day: date
) -> Optional[dict[str, Any]]:
    """Return the unit economics of one SKU-day, or ``None``."""
    row = (
        conn.execute(
            sql_text(
                "SELECT units, revenue, commission, logistics, advertising, cogs,"
                " margin FROM unit_economics"
                " WHERE channel = :channel AND sku = :sku AND day = :day",
                {"channel": channel, "sku": sku, "day": on_day},
            ),
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def log_event(
    conn: Connection,
    decision_id: int,
    stage: str,
    on_day: date,
    user_id: Optional[int] = None,
    note: str = "",
) -> None:
    """Append a stage to the decision journal."""
    conn.execute(
        insert(decision_event).values(
            decision_id=decision_id,
            stage=stage,
            user_id=user_id,
            note=note,
            on_day=on_day,
        )
    )


def journal(conn: Connection, decision_id: int) -> list[dict[str, Any]]:
    """Return the journal of a decision in order."""
    rows = conn.execute(
        select(decision_event)
        .where(decision_event.c.decision_id == decision_id)
        .order_by(decision_event.c.id)
    ).mappings()
    return [dict(row) for row in rows]
