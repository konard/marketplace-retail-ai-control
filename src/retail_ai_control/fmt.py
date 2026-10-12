"""Russian number formats for texts that people read."""

from __future__ import annotations

from datetime import date

MINUS = "−"


def pct(value: float) -> str:
    """Format a rate: ``4.0`` -> ``4,0%``."""
    return f"{value:.1f}%".replace(".", ",").replace("-", MINUS)


def number(value: float) -> str:
    """Format a count without trailing zeros: ``35.7`` -> ``35,7``, ``8.0`` -> ``8``."""
    return f"{value:g}".replace(".", ",").replace("-", MINUS)


def signed_pct(value: float) -> str:
    """Format a change: ``-6.0`` -> ``−6,0%``, ``5.0`` -> ``+5,0%``."""
    text = pct(abs(value))
    if round(value, 1) < 0:
        return MINUS + text
    return "+" + text


def money(value: float) -> str:
    """Format rubles without kopecks: ``14520`` -> ``14 520 ₽``."""
    text = f"{round(value):,}".replace(",", " ").replace("-", MINUS)
    return f"{text} ₽"


def day(value: date) -> str:
    """Format a date: ``2026-10-09`` -> ``09.10.2026``."""
    return value.strftime("%d.%m.%Y")


def plural(count: int, one: str, few: str, many: str) -> str:
    """Choose the Russian plural form for a count."""
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many
