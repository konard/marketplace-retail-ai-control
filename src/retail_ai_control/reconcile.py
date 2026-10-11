"""Reconcile the data mart with the marketplace financial reports.

For every report in the range, the payout computed from the data mart
(revenue - commission - logistics) is compared with the payout in the
report. A channel is trusted only when its latest check is ``ok``.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Any, Optional

import httpx
from sqlalchemy import func, insert, select
from sqlalchemy.engine import Connection

from retail_ai_control import queries
from retail_ai_control.mart import reconciliation

if TYPE_CHECKING:
    from retail_ai_control.pilot import Pilot

logger = logging.getLogger(__name__)
OK = "ok"
MISMATCH = "mismatch"
MISSING = "missing report"


def difference_pct(computed: float, reported: float) -> float:
    """Return the relative difference in percent of the reported payout."""
    if not reported:
        return 0.0 if not computed else 100.0
    return round(abs(computed - reported) / abs(reported) * 100, 2)


def reconcile(pilot: Pilot, first: date, last: date) -> list[dict[str, Any]]:
    """Check every channel for the range and store the results."""
    results: list[dict[str, Any]] = []
    tolerance = pilot.config.reconciliation_tolerance_pct
    for channel, client in (("wb", pilot.wb), ("ozon", pilot.ozon)):
        if client is None:
            continue
        try:
            reports = [
                report
                for report in client.payout_reports(first, last)
                if first <= report[0] and report[1] <= last
            ]
        except (httpx.HTTPError, ValueError, KeyError) as error:
            logger.warning("financial report of %s failed: %s", channel, error)
            reports = []
        with pilot.engine.begin() as conn:
            if not reports:
                computed = _payout(conn, channel, first, last)
                results.append(
                    _store(pilot, conn, channel, first, last, computed, None, None)
                )
                continue
            for date_from, date_to, reported in reports:
                computed = _payout(conn, channel, date_from, date_to)
                diff = difference_pct(computed, reported)
                status = OK if diff <= tolerance else MISMATCH
                results.append(
                    _store(
                        pilot,
                        conn,
                        channel,
                        date_from,
                        date_to,
                        computed,
                        reported,
                        diff,
                        status,
                    )
                )
    return results


def _payout(conn: Connection, channel: str, first: date, last: date) -> float:
    rows = queries.run(
        conn, "channel_payout", channel=channel, date_from=first, date_to=last
    ).rows
    return float(rows[0]["payout"] or 0)


def _store(
    pilot: Pilot,
    conn: Connection,
    channel: str,
    first: date,
    last: date,
    computed: float,
    reported: Optional[float],
    diff: Optional[float],
    status: str = MISSING,
) -> dict[str, Any]:
    row = {
        "channel": channel,
        "date_from": first,
        "date_to": last,
        "computed": computed,
        "reported": reported,
        "diff_pct": diff,
        "status": status,
        "checked_on": pilot.today(),
    }
    conn.execute(insert(reconciliation).values(**row))
    return row


def channel_status(conn: Connection, channel: str) -> Optional[str]:
    """Return the worst status of the latest check, or ``None`` if never checked."""
    latest = conn.execute(
        select(func.max(reconciliation.c.checked_on)).where(
            reconciliation.c.channel == channel
        )
    ).scalar()
    if latest is None:
        return None
    statuses: set[str] = set(
        conn.execute(
            select(reconciliation.c.status).where(
                reconciliation.c.channel == channel,
                reconciliation.c.checked_on == latest,
            )
        ).scalars()
    )
    for status in (MISMATCH, MISSING):
        if status in statuses:
            return status
    return OK
