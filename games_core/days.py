"""Календарь бота — московское время: «сегодня» у друзей, уведомлений и напоминаний."""
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=3))   # Москва, без перехода на летнее время


def local(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, TZ)


def day_key(ts: float) -> str:
    """'2026-10-21' — какой это день по Москве."""
    return local(ts).strftime("%Y-%m-%d")


def day_start(ts: float) -> float:
    """Начало московских суток, в которые попадает ts."""
    d = local(ts)
    return d.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def hour(ts: float) -> int:
    return local(ts).hour


def next_time(ts: float, hh: int, mm: int) -> float:
    """Ближайшее после ts время hh:mm по Москве (если уже прошло — завтра)."""
    d = local(ts)
    at = d.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if at.timestamp() <= ts:
        at += timedelta(days=1)
    return at.timestamp()
