import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from . import config, handlers_client, handlers_master
from .db import DB
from .reminders import reminder_loop


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан (см. .env.example)")
    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
    db = await DB.open(config.DB_PATH, config.DEFAULT_SERVICES, config.MASTER_IDS)

    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp["db"] = db
    dp.include_router(handlers_master.router)
    dp.include_router(handlers_client.router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="book", description="Записаться"),
        BotCommand(command="my", description="Мои записи"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="today", description="Расписание на сегодня (мастер)"),
        BotCommand(command="tomorrow", description="Расписание на завтра (мастер)"),
        BotCommand(command="schedule", description="Расписание на дату (мастер)"),
        BotCommand(command="cancel", description="Отменить запись по номеру (мастер)"),
    ])
    task = asyncio.create_task(reminder_loop(bot, db))
    try:
        await dp.start_polling(bot)
    finally:
        task.cancel()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
