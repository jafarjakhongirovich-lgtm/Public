#!/usr/bin/env python3
"""Boshqaruv buyruqlari.

    python manage.py init          — bazani yaratadi va boshlang'ich ma'lumot qo'yadi
    python manage.py demo          — namoyish uchun xodimlar va bir oylik davomat
    python manage.py holidays      — O'zbekiston bayramlarini qo'shadi
    python manage.py kiosks        — kiosk havolalarini ko'rsatadi
    python manage.py add-employee  — xodim qo'shadi
    python manage.py recompute     — oraliqdagi davomatni qayta hisoblaydi
    python manage.py payroll       — oylik hisobini terminalga chiqaradi
    python manage.py purge-tokens  — eski QR tokenlarini tozalaydi
    python manage.py secret        — yangi SECRET_KEY yasaydi
"""

from __future__ import annotations

import argparse
import secrets
import socket
import sys
from datetime import date, time

from sqlalchemy import select

from app import attendance as att_mod
from app import demo as demo_mod
from app import holidays_uz, security
from app import payroll as payroll_mod
from app.config import settings
from app.db import init_db, session_scope
from app.models import Employee, Holiday, Kiosk, Location, Schedule
from app.timeutil import UZ_WEEKDAYS, current_period, fmt_minutes, month_bounds


def cmd_init(args: argparse.Namespace) -> None:
    init_db()
    with session_scope() as db:
        schedule = db.scalars(select(Schedule)).first()
        if schedule is None:
            schedule = Schedule(
                name="Asosiy (09:00–18:00)",
                start_time=time(9, 0),
                end_time=time(18, 0),
                lunch_start=time(13, 0),
                lunch_end=time(14, 0),
                lunch_minutes=60,
                work_days="1,2,3,4,5",
                grace_minutes=5,
            )
            db.add(schedule)
            print("+ ish jadvali yaratildi: Asosiy (09:00–18:00, tushlik 13:00–14:00, grace 5 daq)")

        location = db.scalars(select(Location)).first()
        if location is None:
            location = Location(name="Bosh ofis")
            db.add(location)
            db.flush()
            print(f"+ ofis yaratildi: Bosh ofis (id={location.id})")

        kiosk = db.scalars(select(Kiosk)).first()
        if kiosk is None:
            kiosk = Kiosk(
                name="Kirish eshigi ekrani",
                location_id=location.id,
                api_key=security.new_api_key(),
            )
            db.add(kiosk)
            db.flush()
            print("+ kiosk yaratildi: Kirish eshigi ekrani")

    print("\nBaza tayyor.")
    cmd_kiosks(args)

    if settings.secret_key == "dev-insecure-secret-key":
        print("\n⚠️  SECRET_KEY standart qiymatda! .env ga yangi kalit yozing:")
        print(f"   SECRET_KEY={secrets.token_urlsafe(32)}")
    if not settings.bot_username:
        print("⚠️  BOT_USERNAME bo'sh — QR ichidagi havola ishlamaydi.")


def lan_ip() -> str | None:
    """Bu kompyuterning lokal tarmoqdagi manzili.

    UDP soketni tashqariga "ulaymiz" — hech qanday paket yuborilmaydi, lekin
    OS qaysi interfeys ishlatilishini aytadi. Bu bir nechta tarmoq kartasi
    bo'lganda `gethostbyname` dan ishonchliroq.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def cmd_kiosks(args: argparse.Namespace) -> None:
    port = args.port
    with session_scope() as db:
        kiosks = db.scalars(select(Kiosk).order_by(Kiosk.id)).all()
        if not kiosks:
            print("Kiosk yo'q. `python manage.py init` ni ishlating.")
            return

        address = lan_ip()
        print("\nOfis ekranida ochiladigan havolalar (maxfiy!):")
        for kiosk in kiosks:
            print(f"\n  {kiosk.name} [{kiosk.location.name}]")
            print(f"    Shu kompyuterda:      http://localhost:{port}/kiosk/{kiosk.api_key}")
            if address:
                print(f"    Lokal tarmoqdan:      http://{address}:{port}/kiosk/{kiosk.api_key}")

        print(
            "\nEkran shu kompyuterda bo'lsa — birinchi havola. Boshqa qurilmada"
            "\n(TV, planshet) bo'lsa — ikkinchisi, lekin server `--host 0.0.0.0`"
            "\nbilan ishga tushirilgan bo'lishi kerak."
        )
        if address is None:
            print("\n(Lokal IP aniqlanmadi — tarmoq ulanmagan bo'lishi mumkin.)")


def cmd_demo(args: argparse.Namespace) -> None:
    period = args.period or current_period()
    init_db()
    with session_scope() as db:
        try:
            result = demo_mod.seed_demo(db, period, force=args.force)
        except demo_mod.DemoDataExists as exc:
            sys.exit(f"\n{exc}")

    print(f"\nDemo ma'lumot yaratildi — {result['period']}")
    print(f"  xodimlar:        {result['employees']}")
    print(f"  davomat yozuvi:  {result['events']}")
    if result["holiday"]:
        print(f"  bayram kuni:     {result['holiday']}")
    if result["vacation_days"]:
        print(f"  ta'til:          {result['vacation_days']} kun (bitta xodimga)")

    address = lan_ip()
    host = f"http://{address}:{args.port}" if address else f"http://localhost:{args.port}"
    print("\nEndi web serverni ishga tushiring:")
    print(f"  uvicorn app.main:app --host 0.0.0.0 --port {args.port}")
    print("\nSo'ng ochib ko'ring:")
    print(f"  Kunlik jadval:  {host}/admin")
    print(f"  Oylik hisobi:   {host}/admin/payroll?period={result['period']}")
    print(f"  Ofis ekrani:    {host}/kiosk/{result['kiosk_key']}")
    print(f"\nAdmin logini: {settings.admin_username} / (.env dagi ADMIN_PASSWORD)")
    print(
        "\nDIQQAT: bu o'qitish uchun soxta ma'lumot. Haqiqiy ishga o'tishdan oldin"
        "\nbazani tozalab oling (SQLite bo'lsa — tabel.db faylini o'chirish yetarli)."
    )


def cmd_holidays(args: argparse.Namespace) -> None:
    year = args.year
    added, existed = 0, 0
    with session_scope() as db:
        for day, name in holidays_uz.fixed_for_year(year):
            if db.get(Holiday, day) is None:
                db.add(Holiday(day=day, name=name))
                added += 1
            else:
                existed += 1

    print(f"\n{year} yil uchun qat'iy bayramlar: {added} ta qo'shildi", end="")
    print(f", {existed} ta allaqachon bor edi." if existed else ".")

    hints = holidays_uz.lunar_hints_for_year(year)
    if hints:
        print(
            "\n⚠️  QO'LDA KIRITISH KERAK — oy taqvimiga bog'liq bayramlar."
            "\n   Aniq sanani O'zbekiston musulmonlari idorasi e'lon qiladi,"
            "\n   quyidagilar faqat taxminiy hisob:"
        )
        for day, name in hints:
            print(f"     ~{day.strftime('%d.%m.%Y')}  {name}")
    else:
        print(f"\n(⚠️  {year} yil uchun hayit sanalari bazada yo'q — qo'lda kiritasiz.)")

    collisions = holidays_uz.weekend_collisions(year)
    if collisions:
        print(
            "\n⚠️  DAM OLISH KUNIGA TUSHGAN BAYRAMLAR — dam olish kuni boshqa kunga"
            "\n   ko'chiriladi, ko'chirish sanasini hukumat qarori belgilaydi:"
        )
        for day, name in collisions:
            print(f"     {day.strftime('%d.%m.%Y')} ({UZ_WEEKDAYS[day.isoweekday()]})  {name}")

    print("\nQo'shish/tahrirlash: admin panel -> Sozlamalar -> Bayramlar")


def cmd_add_employee(args: argparse.Namespace) -> None:
    with session_scope() as db:
        schedule_id = args.schedule
        if schedule_id is None:
            schedule = db.scalars(select(Schedule).order_by(Schedule.id)).first()
            if schedule is None:
                sys.exit("Ish jadvali yo'q. Avval `python manage.py init`.")
            schedule_id = schedule.id

        employee = Employee(
            full_name=args.name,
            position=args.position or "",
            telegram_user_id=args.telegram_id,
            telegram_username=(args.username or "").lstrip("@"),
            monthly_salary=args.salary,
            schedule_id=schedule_id,
            hired_at=date.fromisoformat(args.hired) if args.hired else None,
        )
        db.add(employee)
        db.flush()
        print(f"+ xodim qo'shildi: {employee.full_name} (id={employee.id})")
        if employee.telegram_user_id is None:
            print("  Telegram user_id kiritilmadi — xodim botga /start yozganda ulanadi")
            print("  (username to'ldirilgan bo'lsa avtomatik, aks holda qo'lda kiritasiz).")


def cmd_recompute(args: argparse.Namespace) -> None:
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    with session_scope() as db:
        employees = db.scalars(select(Employee)).all()
        for employee in employees:
            att_mod.recompute_range(db, employee, start, end)
        print(f"{len(employees)} xodim uchun {start}..{end} qayta hisoblandi.")


def cmd_payroll(args: argparse.Namespace) -> None:
    period = args.period or current_period()
    start, end = month_bounds(period)
    # f-string ichida apostrof bo'lmasligi uchun alohida o'zgaruvchilar
    unpaid_label = "To'lanmaydi"
    net_label = "To'lanadi"
    with session_scope() as db:
        results = payroll_mod.compute_period(db, period)
        print(f"\nOylik hisobi — {period} ({start}..{end})\n")
        header = (
            f"{'F.I.Sh.':<24}{'Norma':>6}{'Ishlagan':>9}{'Kelmadi':>8}"
            f"{'Kechik.':>8}{unpaid_label:>13}{net_label:>14}"
        )
        print(header)
        print("-" * len(header))
        for res in results:
            print(
                f"{res.employee_name[:23]:<24}"
                f"{res.scheduled_days:>6}"
                f"{res.worked_days:>9}"
                f"{res.absent_days:>8}"
                f"{res.late_count:>8}"
                f"{fmt_minutes(res.unpaid_minutes):>13}"
                f"{res.net_payable:>14,.0f}"
            )
        if args.save:
            payroll_mod.save_results(db, results)
            print("\nNatijalar payroll_items jadvaliga yozildi.")


def cmd_purge_tokens(args: argparse.Namespace) -> None:
    with session_scope() as db:
        removed = att_mod.purge_old_tokens(db, args.hours)
        print(f"{removed} ta eski token o'chirildi.")


def cmd_secret(args: argparse.Namespace) -> None:
    print(secrets.token_urlsafe(32))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Davomat tizimi boshqaruvi")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="bazani yaratish va boshlang'ich ma'lumot")
    init.add_argument("--port", type=int, default=8000, help="web server porti (havola uchun)")
    init.set_defaults(func=cmd_init)

    kiosks = sub.add_parser("kiosks", help="kiosk havolalarini ko'rsatish")
    kiosks.add_argument("--port", type=int, default=8000, help="web server porti (havola uchun)")
    kiosks.set_defaults(func=cmd_kiosks)

    demo = sub.add_parser("demo", help="namoyish uchun soxta ma'lumot yaratish")
    demo.add_argument("--period", help="YYYY-MM (standart: shu oy)")
    demo.add_argument("--port", type=int, default=8000, help="web server porti (havola uchun)")
    demo.add_argument(
        "--force", action="store_true", help="bazada xodim bo'lsa ham qo'shish"
    )
    demo.set_defaults(func=cmd_demo)

    holidays = sub.add_parser("holidays", help="O'zbekiston bayramlarini qo'shish")
    holidays.add_argument("--year", type=int, default=date.today().year, help="yil, masalan 2026")
    holidays.set_defaults(func=cmd_holidays)
    sub.add_parser("secret", help="yangi SECRET_KEY yasash").set_defaults(func=cmd_secret)

    add = sub.add_parser("add-employee", help="xodim qo'shish")
    add.add_argument("--name", required=True)
    add.add_argument("--salary", type=float, default=0)
    add.add_argument("--position", default="")
    add.add_argument("--telegram-id", type=int, dest="telegram_id")
    add.add_argument("--username", default="")
    add.add_argument("--schedule", type=int)
    add.add_argument("--hired")
    add.set_defaults(func=cmd_add_employee)

    rec = sub.add_parser("recompute", help="davomatni qayta hisoblash")
    rec.add_argument("--start", required=True, help="YYYY-MM-DD")
    rec.add_argument("--end", required=True, help="YYYY-MM-DD")
    rec.set_defaults(func=cmd_recompute)

    pay = sub.add_parser("payroll", help="oylik hisobi")
    pay.add_argument("--period", help="YYYY-MM (standart: shu oy)")
    pay.add_argument("--save", action="store_true", help="natijani bazaga yozish")
    pay.set_defaults(func=cmd_payroll)

    purge = sub.add_parser("purge-tokens", help="eski QR tokenlarini tozalash")
    purge.add_argument("--hours", type=int, default=48)
    purge.set_defaults(func=cmd_purge_tokens)

    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
