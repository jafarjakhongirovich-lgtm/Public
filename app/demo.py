"""Demo ma'lumot: tizimni bot va serversiz "jonli" ko'rish uchun.

Nima uchun kerak: Telegram bot tokeni va ofis ekrani bo'lmasa ham, admin
panelni, oylik hisobini va Excel eksportini to'liq ko'rib chiqish mumkin
bo'lsin. Bu O'QITUVCHI ma'lumot, real xodimlar emas.

MUHIM: yozuvlar `attendance.record_event()` orqali qo'shiladi, ya'ni kechikish,
tushlik oshig'i, holat va oylik — hammasi **haqiqiy kod** bilan hisoblanadi,
qo'lda "chizilmaydi". Shuning uchun demo ko'rsatgan raqamlar real ishlashiga
to'liq mos keladi.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import attendance as att_mod
from app.models import (
    Employee,
    EventSource,
    EventType,
    Holiday,
    Kiosk,
    Leave,
    LeaveKind,
    Location,
    Schedule,
)
from app.security import new_api_key
from app.timeutil import iter_days, month_bounds


@dataclass(frozen=True)
class Profile:
    """Xodimning "xarakteri" — demo ma'lumot ishonchli ko'rinishi uchun."""

    name: str
    position: str
    salary: int
    # Kelish vaqti tarqalishi: (eng erta, eng kech) daqiqa, jadvaldan
    arrival_spread: tuple[int, int]
    # Ketish vaqti tarqalishi (manfiy = erta ketish)
    departure_spread: tuple[int, int]
    # Tushlik davomiyligi (daqiqa)
    lunch_spread: tuple[int, int]
    # Ishga kelmaslik ehtimoli
    absence_chance: float = 0.0
    # Ketishini qayd etmay ketish ehtimoli
    forgets_checkout_chance: float = 0.0


PROFILES: list[Profile] = [
    Profile(
        "Aliyev Aziz Akmalovich",
        "Sotuv bo'limi boshlig'i",
        12_000_000,
        arrival_spread=(-15, 3),
        departure_spread=(0, 45),
        lunch_spread=(45, 60),
    ),
    Profile(
        "Karimova Nilufar Bahodirovna",
        "Bosh buxgalter",
        10_500_000,
        arrival_spread=(-10, 4),
        departure_spread=(-5, 20),
        lunch_spread=(55, 65),
    ),
    Profile(
        "Rasulov Jasur Farhodovich",
        "Sotuv menejeri",
        7_500_000,
        # Muntazam kechikadi — 10-40 daqiqa
        arrival_spread=(10, 40),
        departure_spread=(-10, 15),
        lunch_spread=(60, 85),
        forgets_checkout_chance=0.10,
    ),
    Profile(
        "Yusupova Zulfiya Rustamovna",
        "HR menejeri",
        8_000_000,
        arrival_spread=(-5, 12),
        # Erta ketishga moyil
        departure_spread=(-40, 5),
        lunch_spread=(60, 70),
    ),
    Profile(
        "To'xtayev Bekzod Shavkatovich",
        "Dasturchi",
        15_000_000,
        arrival_spread=(-5, 25),
        departure_spread=(30, 120),
        # Tushlikda uzoq yuradi
        lunch_spread=(70, 100),
        forgets_checkout_chance=0.15,
    ),
    Profile(
        "Sobirov Doniyor Ilhomovich",
        "Omborchi",
        6_000_000,
        arrival_spread=(-8, 6),
        departure_spread=(-5, 10),
        lunch_spread=(55, 65),
        # Ba'zan sababsiz kelmaydi
        absence_chance=0.08,
    ),
]


class DemoDataExists(Exception):
    """Bazada allaqachon xodim bor — demo ma'lumot ustiga yozilmaydi."""


def seed_demo(
    db: Session,
    period: str,
    *,
    seed: int = 20260730,
    force: bool = False,
) -> dict:
    """Demo xodimlar va bir oylik davomat yozuvlarini yaratadi.

    `seed` fiksirlangan — bir xil chaqiruv har doim bir xil natija beradi,
    shuning uchun testlar aniq raqamlarni tekshirishi mumkin.
    """
    existing = db.scalars(select(Employee)).first()
    if existing is not None and not force:
        raise DemoDataExists(
            f"Bazada allaqachon xodimlar bor (masalan: {existing.full_name}). "
            "Demo ma'lumot qo'shish uchun --force ishlating."
        )

    rng = random.Random(seed)
    schedule = _ensure_schedule(db)
    location = _ensure_location(db)
    _ensure_kiosk(db, location)

    start, end = month_bounds(period)
    employees = [_create_employee(db, profile, schedule, location) for profile in PROFILES]

    # Bitta bayram va bitta ta'til — statuslar qanday ko'rinishini ko'rsatish uchun
    holiday = _pick_workday(start, end, schedule, offset=9)
    if holiday is not None and db.get(Holiday, holiday) is None:
        db.add(Holiday(day=holiday, name="Demo bayram kuni"))

    vacation_start = _pick_workday(start, end, schedule, offset=15)
    vacation_days = 0
    if vacation_start is not None:
        vacation_end = min(vacation_start + timedelta(days=4), end)
        db.add(
            Leave(
                employee_id=employees[1].id,
                start_date=vacation_start,
                end_date=vacation_end,
                kind=LeaveKind.VACATION,
                is_paid=True,
                note="Demo: mehnat ta'tili",
            )
        )
        vacation_days = (vacation_end - vacation_start).days + 1
    db.flush()

    events = 0
    for profile, employee in zip(PROFILES, employees, strict=True):
        for day in iter_days(start, end):
            if not schedule.is_work_day(day):
                continue
            if att_mod.is_holiday(db, day) is not None:
                continue
            if att_mod.leave_for(db, employee.id, day) is not None:
                continue
            if rng.random() < profile.absence_chance:
                continue  # sababsiz kelmagan kun
            events += _seed_one_day(db, employee, schedule, profile, day, rng)

    return {
        "employees": len(employees),
        "events": events,
        "period": period,
        "holiday": holiday,
        "vacation_days": vacation_days,
        "kiosk_key": db.scalars(select(Kiosk)).first().api_key,
    }


def _seed_one_day(
    db: Session,
    employee: Employee,
    schedule: Schedule,
    profile: Profile,
    day: date,
    rng: random.Random,
) -> int:
    """Bir kunlik yozuvlarni qo'shadi, qo'shilgan yozuv sonini qaytaradi."""
    scheduled_start = datetime.combine(day, schedule.start_time)
    scheduled_end = datetime.combine(day, schedule.end_time)

    arrived = scheduled_start + timedelta(minutes=rng.randint(*profile.arrival_spread))
    att_mod.record_event(
        db, employee, EventType.IN, arrived, source=EventSource.QR, note="demo"
    )
    count = 1

    if schedule.lunch_start is not None:
        lunch_out = datetime.combine(day, schedule.lunch_start) + timedelta(
            minutes=rng.randint(-10, 20)
        )
        lunch_back = lunch_out + timedelta(minutes=rng.randint(*profile.lunch_spread))
        att_mod.record_event(
            db, employee, EventType.LUNCH_OUT, lunch_out, source=EventSource.QR, note="demo"
        )
        att_mod.record_event(
            db, employee, EventType.LUNCH_IN, lunch_back, source=EventSource.QR, note="demo"
        )
        count += 2

    if rng.random() >= profile.forgets_checkout_chance:
        left = scheduled_end + timedelta(minutes=rng.randint(*profile.departure_spread))
        att_mod.record_event(
            db, employee, EventType.OUT, left, source=EventSource.QR, note="demo"
        )
        count += 1

    return count


def _pick_workday(start: date, end: date, schedule: Schedule, offset: int) -> date | None:
    """Oraliqdagi `offset`-chi ish kunini qaytaradi (bayram/ta'til qo'yish uchun)."""
    workdays = [day for day in iter_days(start, end) if schedule.is_work_day(day)]
    if not workdays:
        return None
    return workdays[min(offset, len(workdays) - 1)]


def _ensure_schedule(db: Session) -> Schedule:
    schedule = db.scalars(select(Schedule)).first()
    if schedule is not None:
        return schedule
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
    db.flush()
    return schedule


def _ensure_location(db: Session) -> Location:
    location = db.scalars(select(Location)).first()
    if location is not None:
        return location
    location = Location(name="Bosh ofis")
    db.add(location)
    db.flush()
    return location


def _ensure_kiosk(db: Session, location: Location) -> Kiosk:
    kiosk = db.scalars(select(Kiosk)).first()
    if kiosk is not None:
        return kiosk
    kiosk = Kiosk(
        name="Kirish eshigi ekrani", location_id=location.id, api_key=new_api_key()
    )
    db.add(kiosk)
    db.flush()
    return kiosk


def _create_employee(
    db: Session, profile: Profile, schedule: Schedule, location: Location
) -> Employee:
    employee = Employee(
        full_name=profile.name,
        position=profile.position,
        # Demo xodimlarga Telegram bog'lanmaydi — bot bo'lmasa ham ishlaydi.
        telegram_user_id=None,
        monthly_salary=profile.salary,
        schedule_id=schedule.id,
        location_id=location.id,
        hired_at=date(2024, 1, 15),
    )
    db.add(employee)
    db.flush()
    return employee
