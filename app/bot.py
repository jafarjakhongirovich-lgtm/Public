"""Telegram bot: QR skanerlashni qabul qiladi va xodimga javob qaytaradi.

XODIM UCHUN JARAYON
-------------------
1. Ofisdagi ekrandagi QR ni telefon kamerasi bilan skanerlaydi.
2. Telefon `https://t.me/<bot>?start=<token>` havolasini ochadi — Telegram
   o'zi ochiladi va `/start <token>` yuboriladi. Hech narsa yozish shart emas.
3. Bot tokenni tekshiradi (imzo + muddat + takror ishlatilmagani), xodimni
   `telegram_user_id` bo'yicha taniydi va vaqtni yozadi.
4. Bot qanday harakat deb tushunganini yozadi va **tuzatish tugmalarini** beradi.

Baza sinxron SQLAlchemy bilan ishlaydi, shuning uchun har bir DB ishi
`asyncio.to_thread()` ichida bajariladi — bot tsikli bloklanmaydi.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select

from app import attendance as att_mod
from app import payroll as payroll_mod
from app import security
from app.config import settings
from app.db import session_scope
from app.models import DayStatus, Employee, EventType
from app.timeutil import current_period, fmt_minutes, fmt_time, now_local, today_local

log = logging.getLogger(__name__)

EVENT_LABELS = {
    EventType.IN: "Ishga keldi",
    EventType.LUNCH_OUT: "Tushlikka chiqdi",
    EventType.LUNCH_IN: "Tushlikdan qaytdi",
    EventType.OUT: "Ishdan ketdi",
}

_BUTTON_LABELS = {
    EventType.IN: "Keldim",
    EventType.LUNCH_OUT: "Tushlikka",
    EventType.LUNCH_IN: "Tushlikdan qaytdim",
    EventType.OUT: "Ketdim",
}

STATUS_LABELS = {
    DayStatus.PRESENT: "vaqtida",
    DayStatus.LATE: "kechikdi",
    DayStatus.ABSENT: "kelmadi",
    DayStatus.LEAVE: "ta'til/ruxsat",
    DayStatus.HOLIDAY: "dam olish kuni",
    DayStatus.INCOMPLETE: "ketishi qayd etilmagan",
}

dp = Dispatcher()


# --------------------------------------------------------------------------- #
# Sinxron DB ishlari (to_thread ichida chaqiriladi)
# --------------------------------------------------------------------------- #


def _do_scan(telegram_user_id: int, token: str) -> dict:
    with session_scope() as db:
        result = att_mod.scan(db, telegram_user_id, token)
        return {
            "event_id": result.event.id,
            "name": result.employee.full_name,
            "event_type": result.event_type,
            "at": result.event.happened_at,
            "late_minutes": result.attendance.late_minutes,
            "billable_late": result.attendance.billable_late_minutes,
            "grace": result.employee.schedule.grace_minutes,
            "scheduled_start": result.employee.schedule.start_time,
            "scheduled_end": result.employee.schedule.end_time,
            "worked_minutes": result.attendance.worked_minutes,
            "early_leave": result.attendance.early_leave_minutes,
        }


def _do_correct(event_id: int, new_type: EventType, telegram_user_id: int) -> dict:
    with session_scope() as db:
        result = att_mod.correct_event(
            db,
            event_id,
            new_type,
            f"tg:{telegram_user_id}",
            by_telegram_user_id=telegram_user_id,
        )
        return {
            "event_id": result.event.id,
            "name": result.employee.full_name,
            "event_type": result.event_type,
            "at": result.event.happened_at,
            "late_minutes": result.attendance.late_minutes,
            "billable_late": result.attendance.billable_late_minutes,
            "grace": result.employee.schedule.grace_minutes,
            "scheduled_start": result.employee.schedule.start_time,
            "scheduled_end": result.employee.schedule.end_time,
            "worked_minutes": result.attendance.worked_minutes,
            "early_leave": result.attendance.early_leave_minutes,
        }


def _link_or_describe(telegram_user_id: int, username: str, full_name: str) -> dict:
    """Xodimni Telegram akkaunti bilan bog'laydi (username bo'yicha) yoki holat qaytaradi."""
    with session_scope() as db:
        employee = att_mod.employee_by_telegram(db, telegram_user_id)
        if employee is not None:
            return {"linked": True, "name": employee.full_name}

        if username:
            candidate = db.scalars(
                select(Employee).where(
                    Employee.telegram_username == username.lstrip("@"),
                    Employee.telegram_user_id.is_(None),
                    Employee.is_active.is_(True),
                )
            ).first()
            if candidate is not None:
                candidate.telegram_user_id = telegram_user_id
                att_mod.log_audit(
                    db,
                    f"tg:{telegram_user_id}",
                    "link_telegram",
                    "employee",
                    candidate.id,
                    f"@{username}",
                )
                return {"linked": True, "name": candidate.full_name, "just_linked": True}

        return {"linked": False, "user_id": telegram_user_id, "tg_name": full_name}


def _my_today(telegram_user_id: int) -> dict | None:
    with session_scope() as db:
        employee = att_mod.employee_by_telegram(db, telegram_user_id)
        if employee is None:
            return None
        record = att_mod.get_attendance(db, employee.id, today_local())
        if record is None:
            return {"name": employee.full_name, "empty": True}
        return {
            "name": employee.full_name,
            "empty": False,
            "check_in": record.check_in_at,
            "lunch_out": record.lunch_out_at,
            "lunch_in": record.lunch_in_at,
            "check_out": record.check_out_at,
            "late": record.late_minutes,
            "worked": record.worked_minutes,
            "status": record.status,
        }


def _my_payroll(telegram_user_id: int) -> dict | None:
    with session_scope() as db:
        employee = att_mod.employee_by_telegram(db, telegram_user_id)
        if employee is None:
            return None
        res = payroll_mod.compute_employee(db, employee, current_period())
        return {
            "name": res.employee_name,
            "period": res.period,
            "salary": res.monthly_salary,
            "scheduled_days": res.scheduled_days,
            "worked_days": res.worked_days,
            "absent_days": res.absent_days,
            "late_count": res.late_count,
            "late_minutes": res.total_late_minutes,
            "unpaid_minutes": res.unpaid_minutes,
            "unpaid_deduction": res.unpaid_time_deduction,
            "bonus_reduction": res.bonus_reduction,
            "net": res.net_payable,
        }


# --------------------------------------------------------------------------- #
# Javob yasash
# --------------------------------------------------------------------------- #


def _correction_keyboard(event_id: int, current: EventType) -> InlineKeyboardMarkup:
    """Boshqa harakat turlariga o'tkazish tugmalari."""
    buttons = [
        InlineKeyboardButton(
            text=_BUTTON_LABELS[kind], callback_data=f"fix:{event_id}:{kind.value}"
        )
        for kind in EventType
        if kind != current
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _scan_reply(data: dict) -> str:
    kind: EventType = data["event_type"]
    lines = [f"<b>{EVENT_LABELS[kind]}</b> — {fmt_time(data['at'])}", f"{data['name']}"]

    if kind == EventType.IN:
        if data["late_minutes"] <= 0:
            lines.append(f"Vaqtida keldingiz (jadval {fmt_time(data['scheduled_start'])}).")
        elif data["billable_late"] <= 0:
            lines.append(
                f"{data['late_minutes']} daqiqa kechikdingiz — "
                f"{data['grace']} daqiqalik muhlat ichida, ushlanma yo'q."
            )
        else:
            lines.append(
                f"⚠️ {data['late_minutes']} daqiqa kechikdingiz. "
                f"Hisobga olinadi: {fmt_minutes(data['billable_late'])}."
            )
    elif kind == EventType.OUT:
        lines.append(f"Bugun ishlangan vaqt: {fmt_minutes(data['worked_minutes'])}.")
        if data["early_leave"] > 0:
            lines.append(
                f"⚠️ Jadvaldan {fmt_minutes(data['early_leave'])} erta ketdingiz "
                f"(jadval {fmt_time(data['scheduled_end'])})."
            )
    elif kind == EventType.LUNCH_OUT:
        lines.append("Qaytganingizda yana QR ni skanerlang.")
    else:
        lines.append("Qaytganingiz qayd etildi.")

    lines.append("")
    lines.append("<i>Noto'g'ri tushunilgan bo'lsa, pastdagi tugmani bosing.</i>")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Handlerlar
# --------------------------------------------------------------------------- #


@dp.message(CommandStart(deep_link=True))
async def handle_qr(message: Message, command: CommandObject) -> None:
    token = (command.args or "").strip()
    user = message.from_user
    if user is None:
        return

    try:
        data = await asyncio.to_thread(_do_scan, user.id, token)
    except security.TokenError as exc:
        log.info("token rad etildi (user=%s): %s", user.id, exc)
        await message.answer(f"❌ {exc.user_message}")
        return
    except att_mod.AttendanceError as exc:
        log.info("davomat rad etildi (user=%s): %s", user.id, exc)
        await message.answer(f"❌ {exc.user_message}")
        return
    except Exception:  # noqa: BLE001
        log.exception("skanerlashda kutilmagan xato (user=%s)", user.id)
        await message.answer("❌ Texnik xatolik. Administratorga xabar bering.")
        return

    await message.answer(
        _scan_reply(data),
        reply_markup=_correction_keyboard(data["event_id"], data["event_type"]),
    )


@dp.message(CommandStart())
async def handle_start(message: Message) -> None:
    user = message.from_user
    if user is None:
        return
    info = await asyncio.to_thread(
        _link_or_describe, user.id, user.username or "", user.full_name
    )

    if info["linked"]:
        prefix = "✅ Akkaunt bog'landi.\n\n" if info.get("just_linked") else ""
        await message.answer(
            f"{prefix}Salom, <b>{info['name']}</b>!\n\n"
            "Ishga kelganda va ketganda ofisdagi ekrandagi QR ni telefon kamerasi "
            "bilan skanerlang — qolganini bot o'zi qiladi.\n\n"
            "/holat — bugungi davomatim\n"
            "/oylik — shu oydagi hisob"
        )
        return

    await message.answer(
        "Siz hali tizimga ulanmagansiz.\n\n"
        f"Administratorga shu raqamni yuboring:\n<code>{info['user_id']}</code>\n\n"
        "Administrator sizni ro'yxatga qo'shgandan keyin QR ishlay boshlaydi."
    )


@dp.callback_query(F.data.startswith("fix:"))
async def handle_correction(callback: CallbackQuery) -> None:
    if callback.data is None or callback.from_user is None:
        return
    try:
        _, event_id_raw, type_raw = callback.data.split(":", 2)
        event_id = int(event_id_raw)
        new_type = EventType(type_raw)
    except (ValueError, KeyError):
        await callback.answer("Tugma yaroqsiz.", show_alert=True)
        return

    try:
        data = await asyncio.to_thread(_do_correct, event_id, new_type, callback.from_user.id)
    except att_mod.AttendanceError as exc:
        await callback.answer(exc.user_message, show_alert=True)
        return
    except Exception:  # noqa: BLE001
        log.exception("tuzatishda xato (event=%s)", event_id)
        await callback.answer("Texnik xatolik.", show_alert=True)
        return

    if callback.message is not None:
        await callback.message.edit_text(
            _scan_reply(data),
            reply_markup=_correction_keyboard(data["event_id"], data["event_type"]),
        )
    await callback.answer("Tuzatildi.")


@dp.message(Command("holat"))
async def handle_status(message: Message) -> None:
    user = message.from_user
    if user is None:
        return
    info = await asyncio.to_thread(_my_today, user.id)
    if info is None:
        await message.answer("Siz tizimga ulanmagansiz. /start bosing.")
        return
    if info["empty"]:
        await message.answer(f"{info['name']} — bugun hali qayd yo'q.")
        return

    lines = [
        f"<b>{info['name']}</b> — bugun ({STATUS_LABELS.get(info['status'], '')})",
        f"Keldi: {fmt_time(info['check_in'])}",
    ]
    if info["lunch_out"] or info["lunch_in"]:
        lines.append(f"Tushlik: {fmt_time(info['lunch_out'])} – {fmt_time(info['lunch_in'])}")
    lines.append(f"Ketdi: {fmt_time(info['check_out'])}")
    if info["late"] > 0:
        lines.append(f"Kechikish: {fmt_minutes(info['late'])}")
    if info["worked"] > 0:
        lines.append(f"Ishlangan: {fmt_minutes(info['worked'])}")
    await message.answer("\n".join(lines))


@dp.message(Command("oylik"))
async def handle_payroll(message: Message) -> None:
    user = message.from_user
    if user is None:
        return
    info = await asyncio.to_thread(_my_payroll, user.id)
    if info is None:
        await message.answer("Siz tizimga ulanmagansiz. /start bosing.")
        return

    await message.answer(
        f"<b>{info['name']}</b> — {info['period']} (hozirgi holat)\n\n"
        f"Ish kuni normasi: {info['scheduled_days']}\n"
        f"Ishlagan kun: {info['worked_days']}\n"
        f"Kelmagan kun: {info['absent_days']}\n"
        f"Kechikish: {info['late_count']} marta, jami {fmt_minutes(info['late_minutes'])}\n"
        f"To'lanmaydigan vaqt: {fmt_minutes(info['unpaid_minutes'])}\n\n"
        f"Oylik: {info['salary']:,.0f} so'm\n"
        f"Ishlanmagan vaqt: −{info['unpaid_deduction']:,.0f} so'm\n"
        f"Ustama kamayishi: −{info['bonus_reduction']:,.0f} so'm\n"
        f"<b>Hozircha to'lanadi: {info['net']:,.0f} so'm</b>\n\n"
        "<i>Oy tugagach yakuniy hisob buxgalteriya tomonidan tasdiqlanadi.</i>"
    )


# --------------------------------------------------------------------------- #
# Ishga tushirish
# --------------------------------------------------------------------------- #


def build_bot() -> Bot:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN sozlanmagan (.env faylini tekshiring)")
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def run_polling() -> None:
    """Long polling — domen ham, HTTPS sertifikat ham kerak emas."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    bot = build_bot()

    me = await bot.get_me()
    if not settings.bot_username and me.username:
        # QR havolasi bot username'iga bog'liq — .env bo'sh bo'lsa o'zi to'ldiradi.
        settings.bot_username = me.username
    log.info("bot ishga tushdi: @%s (%s)", me.username, now_local().strftime("%Y-%m-%d %H:%M"))

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


def main() -> None:
    from app.db import init_db

    init_db()
    asyncio.run(run_polling())


if __name__ == "__main__":
    main()
