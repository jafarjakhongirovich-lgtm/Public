"""Vaqt bilan ishlash yordamchilari.

Bazada hamma narsa mahalliy vaqtda va naive saqlanadi (models.py izohiga qarang),
shuning uchun bu yerdagi funksiyalar ham naive qaytaradi.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.config import settings

UZ_WEEKDAYS = {
    1: "Dushanba",
    2: "Seshanba",
    3: "Chorshanba",
    4: "Payshanba",
    5: "Juma",
    6: "Shanba",
    7: "Yakshanba",
}


def now_local() -> datetime:
    """Hozirgi mahalliy vaqt, naive (tz belgisi olib tashlangan)."""
    return datetime.now(settings.tz).replace(tzinfo=None)


def today_local() -> date:
    return now_local().date()


def combine(day: date, t: time) -> datetime:
    return datetime.combine(day, t)


def minutes_between(earlier: datetime, later: datetime) -> int:
    """`later - earlier` ni to'liq daqiqada qaytaradi (manfiy ham bo'lishi mumkin)."""
    return int((later - earlier).total_seconds() // 60)


def fmt_time(value: datetime | time | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%H:%M")


def fmt_minutes(total: int) -> str:
    """95 -> "1 s 35 daq" ko'rinishida."""
    if total <= 0:
        return "—"
    hours, minutes = divmod(total, 60)
    if hours and minutes:
        return f"{hours} s {minutes} daq"
    if hours:
        return f"{hours} s"
    return f"{minutes} daq"


def month_bounds(period: str) -> tuple[date, date]:
    """"2026-07" -> (2026-07-01, 2026-07-31)."""
    year_str, month_str = period.split("-")
    year, month = int(year_str), int(month_str)
    first = date(year, month, 1)
    next_first = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return first, next_first - timedelta(days=1)


def iter_days(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def current_period() -> str:
    return now_local().strftime("%Y-%m")
