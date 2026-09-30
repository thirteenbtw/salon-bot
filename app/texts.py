from datetime import date, datetime
from html import escape

from .db import FMT

WD = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
WD_FULL = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]


def parse(s: str) -> datetime:
    return datetime.strptime(s, FMT)


def day_long(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]}, {WD_FULL[d.weekday()]}"


def dt_long(dt: datetime) -> str:
    return f"{day_long(dt.date())} в {dt:%H:%M}"


def day_short(d: date) -> str:
    return f"{WD[d.weekday()]} {d:%d.%m}"


def card(a) -> str:
    """Описание записи для клиента."""
    return (f"💅 <b>{escape(a['service'])}</b>\n"
            f"🗓 {dt_long(parse(a['start']))}\n"
            f"💰 {a['price']} ₽")


def contact_line(a) -> str:
    """Имя клиента ссылкой на профиль в Telegram + телефон (для мастера)."""
    link = f"https://t.me/{a['username']}" if a["username"] else f"tg://user?id={a['user_id']}"
    line = f'<a href="{link}">{escape(a["user_name"])}</a>'
    if a["username"]:
        line += f" (@{escape(a['username'])})"
    if a["phone"]:
        line += f" · 📞 {escape(a['phone'])}"
    return line


def h(text: str) -> str:
    return escape(text or "")
