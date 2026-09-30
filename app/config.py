import os
from datetime import time
from zoneinfo import ZoneInfo


def _time(v: str) -> time:
    h, m = v.split(":")
    return time(int(h), int(m))


def _ints(v: str) -> set[int]:
    return {int(x) for x in v.replace(" ", "").split(",") if x}


BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MASTER_IDS = _ints(os.environ.get("MASTER_IDS", ""))
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() in ("1", "true", "yes")
TZ = ZoneInfo(os.environ.get("TZ", "Europe/Moscow"))
SALON_NAME = os.environ.get("SALON_NAME", "Салон красоты")
SALON_ADDRESS = os.environ.get("SALON_ADDRESS", "")
WORK_START = _time(os.environ.get("WORK_START", "10:00"))
WORK_END = _time(os.environ.get("WORK_END", "20:00"))
SLOT_STEP_MIN = int(os.environ.get("SLOT_STEP_MIN", "30"))
DAYS_AHEAD = int(os.environ.get("DAYS_AHEAD", "14"))
DAYS_OFF = _ints(os.environ.get("DAYS_OFF", "6"))
DB_PATH = os.environ.get("DB_PATH", "data/salon.db")

# Напоминание уходит, когда до записи осталось не более стольких часов
REMIND_BEFORE_H = 24
# Нельзя записаться на время ближе, чем через столько минут
MIN_LEAD_MIN = 60

DEFAULT_SERVICES = [
    ("Маникюр классический", 60, 1500),
    ("Маникюр + гель-лак", 120, 2500),
    ("Педикюр", 90, 2500),
    ("Снятие покрытия", 30, 500),
    ("Наращивание ногтей", 150, 3500),
]
