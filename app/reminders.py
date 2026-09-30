import asyncio
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import config
from .db import DB
from .handlers_client import btn
from .texts import card

log = logging.getLogger(__name__)


async def send_due(bot: Bot, db: DB, now: datetime) -> int:
    """Шлёт напоминания о записях, до которых осталось <= REMIND_BEFORE_H часов."""
    sent = 0
    for a in await db.due_reminders(now, config.REMIND_BEFORE_H):
        kb = InlineKeyboardBuilder()
        kb.row(btn("❌ Отменить запись", f"c:{a['id']}"))
        try:
            await bot.send_message(
                a["user_id"],
                "🔔 <b>Напоминание о записи</b>\nЖдём вас завтра!\n\n"
                f"{card(a)}\n📍 {config.SALON_ADDRESS}\n\n"
                "Если планы изменились — отмените запись кнопкой ниже.",
                reply_markup=kb.as_markup())
            sent += 1
        except Exception as e:  # клиент мог заблокировать бота
            log.warning("reminder %s failed: %s", a["id"], e)
        await db.mark_reminded(a["id"])
    return sent


async def reminder_loop(bot: Bot, db: DB):
    while True:
        try:
            await send_due(bot, db, datetime.now(config.TZ).replace(tzinfo=None))
        except Exception:
            log.exception("reminder loop error")
        await asyncio.sleep(60)
