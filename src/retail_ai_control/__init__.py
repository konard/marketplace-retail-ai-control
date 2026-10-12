"""AI management loop for a Wildberries and Ozon retailer.

The package implements the pilot from ``docs/concept/README.md``: data from
1C, the marketplaces and an analytics service go into one data mart; rules
find deviations; an analyst (an AI agent with a rule-based fallback) explains
them with SQL evidence and proposes actions; a person approves; the decision
becomes a Bitrix24 task; the effect is measured after seven days.

The executable specification is in ``features/``.
"""

from __future__ import annotations

from retail_ai_control.config import Config
from retail_ai_control.pilot import Pilot

__all__ = ["Config", "Pilot"]
