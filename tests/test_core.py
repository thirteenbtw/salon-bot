from datetime import datetime, timedelta

import pytest

from app import config, slots
from app.db import DB
from app.reminders import send_due

MON = datetime(2026, 10, 5, 9, 0)  # понедельник


@pytest.fixture
async def db(tmp_path):
    d = await DB.open(str(tmp_path / "t.db"), config.DEFAULT_SERVICES)
    yield d
    await d.close()


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, uid, text, **kw):
        self.sent.append((uid, text))


def test_slots_respect_busy_and_hours():
    busy = [("2026-10-06 12:00", "2026-10-06 13:00")]
    s = slots.free_slots(MON.date() + timedelta(days=1), 60, busy, MON)
    times = [t.strftime("%H:%M") for t in s]
    assert times[0] == "10:00" and times[-1] == "19:00"
    assert "11:30" not in times and "12:00" not in times and "12:30" not in times
    assert "11:00" in times and "13:00" in times


def test_sunday_and_lead_time():
    assert slots.free_slots(datetime(2026, 10, 4).date(), 60, [], MON) == []
    today = slots.free_slots(MON.date(), 60, [], MON)
    assert today[0].strftime("%H:%M") == "10:00"
    assert slots.free_slots(MON.date(), 60, [], MON.replace(hour=15))[0].strftime("%H:%M") == "16:00"


async def test_no_double_booking(db):
    s = datetime(2026, 10, 6, 12, 0)
    a = await db.create(1, "A", 1, s, s + timedelta(hours=1), False)
    b = await db.create(2, "B", 1, s + timedelta(minutes=30), s + timedelta(minutes=90), False)
    c = await db.create(2, "B", 1, s + timedelta(hours=1), s + timedelta(hours=2), False)
    assert a and b is None and c
    assert await db.cancel(a) and not await db.cancel(a)
    assert await db.create(3, "C", 1, s, s + timedelta(hours=1), False)


async def test_reminders_once(db):
    s = datetime(2026, 10, 6, 12, 0)
    await db.create(1, "A", 1, s, s + timedelta(hours=1), False)
    far = datetime(2026, 10, 8, 12, 0)
    await db.create(2, "B", 1, far, far + timedelta(hours=1), False)
    bot = FakeBot()
    assert await send_due(bot, db, datetime(2026, 10, 5, 11, 0)) == 0
    assert await send_due(bot, db, datetime(2026, 10, 5, 12, 1)) == 1
    assert await send_due(bot, db, datetime(2026, 10, 5, 12, 2)) == 0
    assert bot.sent[0][0] == 1 and "Напоминание" in bot.sent[0][1]
