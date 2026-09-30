from datetime import date, datetime, timedelta

from . import config
from .db import FMT


def bookable_days(today: date) -> list[date]:
    """Даты, доступные для записи (без выходных)."""
    days = [today + timedelta(days=i) for i in range(config.DAYS_AHEAD + 1)]
    return [d for d in days if d.weekday() not in config.DAYS_OFF]


def free_slots(day: date, duration_min: int, busy: list[tuple[str, str]], now: datetime) -> list[datetime]:
    """Свободные времена начала для услуги заданной длительности."""
    if day.weekday() in config.DAYS_OFF:
        return []
    open_dt = datetime.combine(day, config.WORK_START)
    close_dt = datetime.combine(day, config.WORK_END)
    earliest = now.replace(tzinfo=None) + timedelta(minutes=config.MIN_LEAD_MIN)
    step, dur = timedelta(minutes=config.SLOT_STEP_MIN), timedelta(minutes=duration_min)
    out, t = [], open_dt
    while t + dur <= close_dt:
        s, e = t.strftime(FMT), (t + dur).strftime(FMT)
        if t >= earliest and not any(bs < e and be > s for bs, be in busy):
            out.append(t)
        t += step
    return out
