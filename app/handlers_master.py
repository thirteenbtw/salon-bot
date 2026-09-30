from datetime import date, datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import config
from .db import DB
from .handlers_client import BTN_OTHER, BTN_TODAY, BTN_TOMORROW, btn, menu_kb, now, show
from .texts import WD_FULL, contact_line, day_long, day_short, dt_long, h, parse

router = Router()


async def deny(target):
    text = "Эта функция только для мастера."
    if isinstance(target, CallbackQuery):
        await target.answer(text, show_alert=True)
    else:
        await target.answer(text)


@router.message(Command("master"))
async def become_master(m: Message, db: DB):
    if await db.is_master(m.from_user.id):
        await m.answer("Вы уже мастер ✅", reply_markup=menu_kb(True))
    elif config.DEMO_MODE:
        await db.add_master(m.from_user.id)
        await m.answer("🧪 Демо-режим: вы теперь мастер.\n"
                       "Внизу появились кнопки расписания, команды — в /help.\n"
                       "Уведомления о новых записях будут приходить вам.",
                       reply_markup=menu_kb(True))
    else:
        await deny(m)


@router.message(Command("client"))
async def leave_master(m: Message, db: DB):
    if not await db.is_master(m.from_user.id):
        await m.answer("Вы и так в режиме клиента.")
    elif config.DEMO_MODE:
        await db.remove_master(m.from_user.id)
        await m.answer("Вы вышли из режима мастера. Вернуться можно командой /master.",
                       reply_markup=menu_kb(False))
    else:
        await m.answer("Роль мастера задана в настройках (MASTER_IDS), выйти из неё командой нельзя.")


async def schedule_view(db: DB, day: date):
    items = await db.day(day.isoformat())
    kb = InlineKeyboardBuilder()
    head = f"📅 <b>{day_long(day)}</b>\n"
    if not items:
        return head + "\nЗаписей нет — день свободен 🌿", kb.as_markup()
    lines = []
    for a in items:
        lines.append(f"<b>{parse(a['start']):%H:%M}–{parse(a['end']):%H:%M}</b>  №{a['id']}\n"
                     f"  {contact_line(a)}\n  💅 {h(a['service'])}")
        kb.row(btn(f"❌ Отменить №{a['id']} ({parse(a['start']):%H:%M} {a['user_name'][:15]})",
                   f"mc:{a['id']}:{day:%Y%m%d}"))
    return head + f"Записей: {len(items)}\n\n" + "\n".join(lines), kb.as_markup()


async def send_day(m: Message, db: DB, day: date):
    if not await db.is_master(m.from_user.id):
        return await deny(m)
    text, kb = await schedule_view(db, day)
    await m.answer(text, reply_markup=kb)


@router.message(Command("today"))
@router.message(F.text == BTN_TODAY)
async def today(m: Message, db: DB):
    await send_day(m, db, now().date())


@router.message(Command("tomorrow"))
@router.message(F.text == BTN_TOMORROW)
async def tomorrow(m: Message, db: DB):
    await send_day(m, db, now().date() + timedelta(days=1))


def picker():
    kb = InlineKeyboardBuilder()
    for i in range(config.DAYS_AHEAD + 1):
        d = now().date() + timedelta(days=i)
        kb.button(text=day_short(d), callback_data=f"ms:{d:%Y%m%d}")
    kb.adjust(4)
    return kb.as_markup()


@router.message(Command("schedule"))
@router.message(F.text == BTN_OTHER)
async def schedule(m: Message, db: DB, command: CommandObject | None = None):
    if not await db.is_master(m.from_user.id):
        return await deny(m)
    arg = (command.args or "").strip() if command else ""
    if arg:
        for fmt in ("%d.%m.%Y", "%d.%m", "%Y-%m-%d"):
            try:
                d = datetime.strptime(arg, fmt).date()
                if fmt == "%d.%m":
                    d = d.replace(year=now().year)
                return await send_day(m, db, d)
            except ValueError:
                continue
        return await m.answer("Не поняла дату 🤔 Пример: /schedule 05.10")
    await m.answer("Выберите дату:", reply_markup=picker())


@router.callback_query(F.data.startswith("ms:"))
async def schedule_cb(cb: CallbackQuery, db: DB):
    if not await db.is_master(cb.from_user.id):
        return await deny(cb)
    day = datetime.strptime(cb.data.split(":")[1], "%Y%m%d").date()
    await show(cb, *await schedule_view(db, day))


async def do_cancel(bot, db: DB, aid: int) -> str:
    """Отмена мастером + уведомление клиента. Возвращает текст-результат."""
    a = await db.appointment(aid)
    if not a or not await db.cancel(aid):
        return f"Запись №{aid} не найдена или уже отменена."
    try:
        await bot.send_message(
            a["user_id"],
            "😔 К сожалению, мастер отменил вашу запись:\n\n"
            f"💅 {h(a['service'])}\n🗓 {dt_long(parse(a['start']))}\n\n"
            "Пожалуйста, выберите другое время — нажмите «💅 Записаться».")
    except Exception:
        pass
    return f"✅ Запись №{aid} отменена, клиент {h(a['user_name'])} уведомлён."


@router.callback_query(F.data.startswith("mc:"))
async def cancel_cb(cb: CallbackQuery, db: DB):
    if not await db.is_master(cb.from_user.id):
        return await deny(cb)
    _, aid, ds = cb.data.split(":")
    result = await do_cancel(cb.bot, db, int(aid))
    day = datetime.strptime(ds, "%Y%m%d").date()
    text, kb = await schedule_view(db, day)
    await show(cb, f"{result}\n\n{text}", kb)


@router.message(Command("cancel"))
async def cancel_cmd(m: Message, db: DB, command: CommandObject):
    if not await db.is_master(m.from_user.id):
        return await deny(m)
    arg = (command.args or "").strip().lstrip("№#")
    if not arg.isdigit():
        return await m.answer("Укажите номер записи: /cancel 12\nНомера видны в расписании (/today).")
    await m.answer(await do_cancel(m.bot, db, int(arg)))
