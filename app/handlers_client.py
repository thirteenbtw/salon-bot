from datetime import date, datetime, timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, Message, ReplyKeyboardMarkup)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import config, slots
from .db import DB
from .texts import card, contact_line, day_long, day_short, dt_long, h, parse

router = Router()

BTN_BOOK = "💅 Записаться"
BTN_MY = "📋 Мои записи"
BTN_INFO = "ℹ️ О салоне"
BTN_TODAY = "📅 Сегодня"
BTN_TOMORROW = "📅 Завтра"
BTN_OTHER = "🗓 Другая дата"
BTN_SKIP = "Пропустить"


def now() -> datetime:
    return datetime.now(config.TZ)


def menu_kb(is_master: bool) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=BTN_BOOK)], [KeyboardButton(text=BTN_MY), KeyboardButton(text=BTN_INFO)]]
    if is_master:
        rows.append([KeyboardButton(text=BTN_TODAY), KeyboardButton(text=BTN_TOMORROW),
                     KeyboardButton(text=BTN_OTHER)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, input_field_placeholder="Выберите действие")


def btn(text, data):
    return InlineKeyboardButton(text=text, callback_data=data)


async def show(cb: CallbackQuery, text: str, kb: InlineKeyboardMarkup | None = None):
    """Редактируем текущее сообщение — чат не засоряется."""
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass
    await cb.answer()


# ---------- старт и меню ----------

@router.message(CommandStart())
async def start(m: Message, db: DB):
    master = await db.is_master(m.from_user.id)
    await m.answer(
        f"Здравствуйте, {h(m.from_user.first_name)}! 🌸\n"
        f"Это бот записи в <b>{h(config.SALON_NAME)}</b>.\n\n"
        "Выберите услугу, удобные день и время — и запись готова. "
        "За день до визита я пришлю напоминание.\n\n"
        "Нажмите «💅 Записаться» 👇",
        reply_markup=menu_kb(master))


@router.message(Command("help"))
async def help_(m: Message, db: DB):
    text = ("<b>Что я умею</b>\n"
            "💅 Записаться — выбрать услугу, дату и время\n"
            "📋 Мои записи — посмотреть или отменить запись\n"
            "ℹ️ О салоне — адрес и часы работы\n")
    if await db.is_master(m.from_user.id):
        text += ("\n<b>Команды мастера</b>\n"
                 "/today — расписание на сегодня\n"
                 "/tomorrow — на завтра\n"
                 "/schedule — расписание на выбранную дату (или /schedule 05.10)\n"
                 "/cancel &lt;номер&gt; — отменить запись по номеру\n"
                 "Под каждой записью в расписании есть кнопка «Отменить».\n"
                 "/client — выйти из режима мастера (демо)")
    elif config.DEMO_MODE:
        text += "\n🧪 Демо: команда /master включает режим мастера."
    await m.answer(text)


@router.message(Command("id"))
async def my_id(m: Message):
    await m.answer(f"Ваш Telegram ID: <code>{m.from_user.id}</code>")


@router.message(F.text == BTN_INFO)
async def info(m: Message):
    off = ", ".join(("пн", "вт", "ср", "чт", "пт", "сб", "вс")[d] for d in sorted(config.DAYS_OFF)) or "нет"
    await m.answer(
        f"🌸 <b>{h(config.SALON_NAME)}</b>\n"
        f"📍 {h(config.SALON_ADDRESS)}\n"
        f"🕐 Ежедневно {config.WORK_START:%H:%M}–{config.WORK_END:%H:%M}\n"
        f"Выходной: {off}")


@router.callback_query(F.data == "home")
async def home(cb: CallbackQuery):
    await show(cb, "Главное меню — нажмите «💅 Записаться» внизу 👇")


# ---------- запись: услуга → дата → время → подтверждение ----------

@router.message(F.text == BTN_BOOK)
@router.message(Command("book"))
async def book(m: Message, db: DB):
    text, kb = await services_view(db)
    await m.answer(text, reply_markup=kb)


async def services_view(db: DB):
    kb = InlineKeyboardBuilder()
    for s in await db.services():
        kb.row(btn(f"{s['name']} · {s['price']} ₽ · {s['duration_min']} мин", f"s:{s['id']}"))
    return "<b>Шаг 1 из 3.</b> Выберите услугу:", kb.as_markup()


@router.callback_query(F.data == "book")
async def book_cb(cb: CallbackQuery, db: DB):
    await show(cb, *await services_view(db))


@router.callback_query(F.data.startswith("s:"))
async def pick_service(cb: CallbackQuery, db: DB):
    sid = int(cb.data.split(":")[1])
    svc = await db.service(sid)
    kb = InlineKeyboardBuilder()
    days = []
    for d in slots.bookable_days(now().date()):
        # показываем только дни, где есть хотя бы одно свободное окно
        if slots.free_slots(d, svc["duration_min"], await db.busy(d.isoformat()), now()):
            days.append(d)
    for d in days:
        kb.button(text=day_short(d), callback_data=f"d:{sid}:{d:%Y%m%d}")
    kb.adjust(3)
    kb.row(btn("‹ Назад к услугам", "book"))
    if not days:
        await show(cb, "😔 Свободных дат для этой услуги пока нет. Попробуйте позже.", kb.as_markup())
        return
    await show(cb, f"<b>Шаг 2 из 3.</b> {h(svc['name'])}\nВыберите дату:", kb.as_markup())


def parse_day(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()


@router.callback_query(F.data.startswith("d:"))
async def pick_day(cb: CallbackQuery, db: DB):
    _, sid, ds = cb.data.split(":")
    sid, day = int(sid), parse_day(ds)
    svc = await db.service(sid)
    free = slots.free_slots(day, svc["duration_min"], await db.busy(day.isoformat()), now())
    kb = InlineKeyboardBuilder()
    for t in free:
        kb.button(text=f"{t:%H:%M}", callback_data=f"t:{sid}:{ds}:{t:%H%M}")
    kb.adjust(4)
    kb.row(btn("‹ Другая дата", f"s:{sid}"))
    if not free:
        await show(cb, "😔 На этот день свободного времени не осталось. Выберите другую дату.", kb.as_markup())
        return
    await show(cb, f"<b>Шаг 3 из 3.</b> {day_long(day)}\nВыберите время:", kb.as_markup())


@router.callback_query(F.data.startswith("t:"))
async def confirm(cb: CallbackQuery, db: DB):
    _, sid, ds, hm = cb.data.split(":")
    svc = await db.service(int(sid))
    start = datetime.strptime(ds + hm, "%Y%m%d%H%M")
    kb = InlineKeyboardBuilder()
    kb.row(btn("✅ Подтвердить", f"ok:{sid}:{ds}:{hm}"))
    kb.row(btn("‹ Другое время", f"d:{sid}:{ds}"), btn("✖ Отмена", "home"))
    await show(cb,
               "Проверьте запись:\n\n"
               f"💅 <b>{h(svc['name'])}</b>\n🗓 {dt_long(start)}\n"
               f"⏱ {svc['duration_min']} мин\n💰 {svc['price']} ₽\n"
               f"📍 {h(config.SALON_ADDRESS)}",
               kb.as_markup())


PENDING: dict[int, tuple[str, str, str]] = {}  # user_id -> (sid, ds, hm): запись ждёт номер телефона
SKIPPED: set[int] = set()  # кто отказался делиться номером — больше не спрашиваем


@router.callback_query(F.data.startswith("ok:"))
async def create(cb: CallbackQuery, db: DB):
    _, sid, ds, hm = cb.data.split(":")
    uid = cb.from_user.id
    phone = await db.client_phone(uid)
    if phone is None and uid not in SKIPPED:
        PENDING[uid] = (sid, ds, hm)
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)],
                      [KeyboardButton(text=BTN_SKIP)]],
            resize_keyboard=True, one_time_keyboard=True)
        await cb.message.answer("Оставьте номер телефона — мастер сможет связаться с вами, "
                                "если что-то изменится 📞", reply_markup=kb)
        await cb.answer()
        return
    await finish_booking(cb.bot, db, cb.from_user, sid, ds, hm, phone,
                         lambda text, kb=None: show(cb, text, kb))


async def _resume(m: Message, db: DB, phone: str | None):
    pending = PENDING.pop(m.from_user.id, None)
    await m.answer("Спасибо! 👍" if phone else "Хорошо, без номера 👌",
                   reply_markup=menu_kb(await db.is_master(m.from_user.id)))
    if pending:
        await finish_booking(m.bot, db, m.from_user, *pending, phone,
                             lambda text, kb=None: m.answer(text, reply_markup=kb))


@router.message(F.contact)
async def got_contact(m: Message, db: DB):
    if m.contact.user_id != m.from_user.id:
        return await m.answer("Пожалуйста, отправьте свой номер кнопкой «📱 Поделиться номером».")
    phone = m.contact.phone_number
    phone = phone if phone.startswith("+") else "+" + phone
    await db.set_client_phone(m.from_user.id, phone)
    await _resume(m, db, phone)


@router.message(F.text == BTN_SKIP)
async def skip_contact(m: Message, db: DB):
    SKIPPED.add(m.from_user.id)
    await _resume(m, db, None)


async def finish_booking(bot, db: DB, user, sid, ds, hm, phone, reply):
    svc = await db.service(int(sid))
    start = datetime.strptime(ds + hm, "%Y%m%d%H%M")
    end = start + timedelta(minutes=svc["duration_min"])
    n = now().replace(tzinfo=None)
    # перепроверяем: слот мог занять кто-то другой, пока клиент думал
    if start not in slots.free_slots(start.date(), svc["duration_min"], await db.busy(start.date().isoformat()), now()):
        kb = InlineKeyboardBuilder()
        kb.row(btn("Выбрать другое время", f"d:{sid}:{ds}"))
        await reply("😔 Это время только что заняли или оно уже недоступно.", kb.as_markup())
        return
    # если до визита меньше суток — напоминание не нужно
    too_close = start - n <= timedelta(hours=config.REMIND_BEFORE_H)
    aid = await db.create(user.id, user.full_name, svc["id"], start, end, reminded=too_close,
                          username=user.username, phone=phone)
    if aid is None:
        kb = InlineKeyboardBuilder()
        kb.row(btn("Выбрать другое время", f"d:{sid}:{ds}"))
        await reply("😔 Это время только что заняли. Выберите другое.", kb.as_markup())
        return
    kb = InlineKeyboardBuilder()
    kb.row(btn("📋 Мои записи", "my"))
    remind = "" if too_close else "\n\n🔔 За день до визита я напомню."
    await reply(f"🎉 <b>Вы записаны!</b> (№{aid})\n\n"
                f"💅 {h(svc['name'])}\n🗓 {dt_long(start)}\n💰 {svc['price']} ₽\n"
                f"📍 {h(config.SALON_ADDRESS)}{remind}",
                kb.as_markup())
    # уведомляем мастеров
    who = contact_line({"user_id": user.id, "user_name": user.full_name,
                        "username": user.username, "phone": phone})
    for mid in await db.master_ids():
        try:
            await bot.send_message(
                mid, f"🆕 Новая запись №{aid}\n{who}\n"
                     f"💅 {h(svc['name'])}\n🗓 {dt_long(start)}")
        except Exception:
            pass


# ---------- мои записи ----------

async def my_view(db: DB, uid: int):
    items = await db.user_upcoming(uid, now().replace(tzinfo=None))
    kb = InlineKeyboardBuilder()
    if not items:
        kb.row(btn("💅 Записаться", "book"))
        return "У вас пока нет предстоящих записей.", kb.as_markup()
    text = "<b>Ваши записи</b>\n\n" + "\n\n".join(card(a) for a in items)
    for a in items:
        kb.row(btn(f"❌ Отменить: {parse(a['start']):%d.%m %H:%M}", f"c:{a['id']}"))
    return text, kb.as_markup()


@router.message(F.text == BTN_MY)
@router.message(Command("my"))
async def my(m: Message, db: DB):
    text, kb = await my_view(db, m.from_user.id)
    await m.answer(text, reply_markup=kb)


@router.callback_query(F.data == "my")
async def my_cb(cb: CallbackQuery, db: DB):
    await show(cb, *await my_view(db, cb.from_user.id))


@router.callback_query(F.data.startswith("c:"))
async def cancel_ask(cb: CallbackQuery, db: DB):
    a = await db.appointment(int(cb.data.split(":")[1]))
    if not a or a["user_id"] != cb.from_user.id or a["status"] != "active":
        await show(cb, "Эта запись уже неактивна.")
        return
    kb = InlineKeyboardBuilder()
    kb.row(btn("Да, отменить", f"cy:{a['id']}"), btn("Нет, оставить", "my"))
    await show(cb, f"Отменить запись?\n\n{card(a)}", kb.as_markup())


@router.callback_query(F.data.startswith("cy:"))
async def cancel_do(cb: CallbackQuery, db: DB):
    a = await db.appointment(int(cb.data.split(":")[1]))
    if not a or a["user_id"] != cb.from_user.id or not await db.cancel(a["id"]):
        await show(cb, "Эта запись уже неактивна.")
        return
    kb = InlineKeyboardBuilder()
    kb.row(btn("💅 Записаться снова", "book"))
    await show(cb, "Запись отменена. Ждём вас в другой раз 🌸", kb.as_markup())
    for mid in await db.master_ids():
        try:
            await cb.bot.send_message(
                mid, f"❌ Клиент отменил запись №{a['id']}\n{contact_line(a)}\n"
                     f"💅 {h(a['service'])}\n🗓 {dt_long(parse(a['start']))}")
        except Exception:
            pass
