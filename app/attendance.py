"""Davomat mantiqi: skanerlashni qabul qilish va kunlik xulosani hisoblash.

IKKI QATLAM
-----------
1. `attendance_events` — har bir skanerlashning xom yozuvi, hech qachon
   o'chirilmaydi (faqat `is_voided` bilan bekor qilinadi).
2. `attendance` — shu yozuvlardan **qayta hisoblanadigan** kunlik xulosa.

Shu sababli har qanday tuzatishdan keyin `recompute_day()` chaqirilsa yetarli —
xulosa har doim xom yozuvlarga mos bo'ladi.

GRACE (jarima hisoblanmaydigan muhlat)
--------------------------------------
`late_minutes`, `early_leave_minutes`, `lunch_overrun_minutes` — **xom** qiymatlar,
grace ayirilmagan holda saqlanadi (hisobotlarda haqiqiy holat ko'rinishi uchun).
Grace har bir toifaga alohida qo'llanadi va to'lov hisobida ayiriladi
(`payroll.billable_minutes()`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, security
from app.models import (
    Attendance,
    AttendanceEvent,
    DayStatus,
    Employee,
    EventSource,
    EventType,
    Holiday,
    Leave,
    Schedule,
    UsedToken,
)
from app.timeutil import combine, minutes_between, now_local

# Tushlikka chiqishni taxmin qilish oynasi (dispetcher izohiga qarang)
_LUNCH_WINDOW_BEFORE = timedelta(minutes=60)
_LUNCH_WINDOW_TAIL = timedelta(minutes=45)


class AttendanceError(Exception):
    """Foydalanuvchiga ko'rsatiladigan davomat xatosi."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class TokenAlreadyUsed(AttendanceError):
    def __init__(self) -> None:
        super().__init__("Bu QR allaqachon ishlatilgan. Ekranda yangilanganini skanerlang.")


class UnknownEmployee(AttendanceError):
    def __init__(self) -> None:
        super().__init__(
            "Siz tizimda ro'yxatdan o'tmagansiz. Administratorga murojaat qiling."
        )


class WrongLocation(AttendanceError):
    def __init__(self, location_name: str) -> None:
        super().__init__(f"Bu QR boshqa ofisga tegishli ({location_name}).")


@dataclass
class ScanResult:
    """Skanerlash natijasi — botga javob yasash uchun."""

    employee: Employee
    event: AttendanceEvent
    attendance: Attendance
    event_type: EventType
    late_minutes: int
    was_auto_detected: bool


# --------------------------------------------------------------------------- #
# Kalendar yordamchilari
# --------------------------------------------------------------------------- #


def is_holiday(db: Session, day: date) -> Holiday | None:
    return db.get(Holiday, day)


def leave_for(db: Session, employee_id: int, day: date) -> Leave | None:
    return db.scalars(
        select(Leave).where(
            Leave.employee_id == employee_id,
            Leave.start_date <= day,
            Leave.end_date >= day,
        )
    ).first()


def employee_by_telegram(db: Session, telegram_user_id: int) -> Employee | None:
    return db.scalars(
        select(Employee).where(
            Employee.telegram_user_id == telegram_user_id,
            Employee.is_active.is_(True),
        )
    ).first()


# --------------------------------------------------------------------------- #
# Harakat turini taxmin qilish
# --------------------------------------------------------------------------- #


def suggest_event_type(
    attendance: Attendance | None, schedule: Schedule, at: datetime
) -> EventType:
    """Xodim shu daqiqada nima qilayotganini kunlik holatdan taxmin qiladi.

    Mantiq:
      * hali kelishi qayd etilmagan          -> IN
      * tushlikka chiqqan, qaytishi yo'q     -> LUNCH_IN
      * tushlik hali bo'lmagan va vaqt mos   -> LUNCH_OUT
      * qolgan barcha holat                  -> OUT

    Bu faqat **taxmin**: bot javobida tuzatish tugmalari ham chiqadi, shuning
    uchun chalkashgan holatda xodim bir bosishda to'g'rilaydi.
    """
    if attendance is None or attendance.check_in_at is None:
        return EventType.IN

    if attendance.lunch_out_at is not None and attendance.lunch_in_at is None:
        return EventType.LUNCH_IN

    if (
        schedule.lunch_start is not None
        and schedule.lunch_end is not None
        and attendance.lunch_out_at is None
    ):
        day = at.date()
        window_start = combine(day, schedule.lunch_start) - _LUNCH_WINDOW_BEFORE
        window_end = combine(day, schedule.end_time) - _LUNCH_WINDOW_TAIL
        if window_start <= at <= window_end:
            return EventType.LUNCH_OUT

    return EventType.OUT


# --------------------------------------------------------------------------- #
# Token qabul qilish
# --------------------------------------------------------------------------- #


def consume_token(
    db: Session,
    payload: security.TokenPayload,
    employee_id: int | None,
    at: datetime | None = None,
) -> None:
    """Tokenni "ishlatilgan" deb belgilaydi. Takror ishlatilsa xato beradi.

    Poyga holatida (bir vaqtda ikki so'rov) baza `nonce` ustunidagi PRIMARY KEY
    cheklovi ikkinchisini rad etadi — shuning uchun bu tekshiruv atomik.
    """
    key = payload.replay_key
    if db.get(UsedToken, key) is not None:
        raise TokenAlreadyUsed
    db.add(
        UsedToken(
            nonce=key,
            location_id=payload.location_id,
            issued_at_epoch=payload.issued_at_epoch,
            used_at=at or now_local(),
            employee_id=employee_id,
        )
    )
    db.flush()


def purge_old_tokens(db: Session, older_than_hours: int = 48) -> int:
    """Eski `used_tokens` yozuvlarini tozalaydi (ular endi replay uchun kerak emas)."""
    cutoff = now_local() - timedelta(hours=older_than_hours)
    rows = db.scalars(select(UsedToken).where(UsedToken.used_at < cutoff)).all()
    for row in rows:
        db.delete(row)
    return len(rows)


# --------------------------------------------------------------------------- #
# Yozuv qo'shish
# --------------------------------------------------------------------------- #


def record_event(
    db: Session,
    employee: Employee,
    event_type: EventType,
    at: datetime,
    *,
    source: EventSource = EventSource.QR,
    location_id: int | None = None,
    kiosk_id: int | None = None,
    token_nonce: str = "",
    note: str = "",
) -> AttendanceEvent:
    """Xom yozuv qo'shadi va kunlik xulosani qayta hisoblaydi."""
    event = AttendanceEvent(
        employee_id=employee.id,
        work_date=at.date(),
        event_type=event_type,
        happened_at=at,
        source=source,
        location_id=location_id,
        kiosk_id=kiosk_id,
        token_nonce=token_nonce,
        note=note,
    )
    db.add(event)
    db.flush()
    recompute_day(db, employee, at.date())
    return event


def void_event(db: Session, event_id: int, actor: str, reason: str = "") -> AttendanceEvent:
    """Yozuvni bekor qiladi (o'chirmaydi) va kunni qayta hisoblaydi."""
    event = db.get(AttendanceEvent, event_id)
    if event is None:
        raise AttendanceError("Bunday yozuv topilmadi.")
    event.is_voided = True
    event.note = (event.note + f" | bekor qilindi: {reason}").strip(" |")
    db.flush()
    employee = db.get(Employee, event.employee_id)
    if employee is not None:
        recompute_day(db, employee, event.work_date)
    log_audit(db, actor, "void_event", "attendance_event", event.id, reason)
    return event


def scan(
    db: Session,
    telegram_user_id: int,
    token: str,
    *,
    at: datetime | None = None,
    forced_type: EventType | None = None,
) -> ScanResult:
    """QR skanerlashning to'liq yo'li: token -> xodim -> yozuv.

    `forced_type` bot tugmasi orqali tuzatish uchun (o'sha tokenni qayta
    ishlatmaydi — tuzatish `correct_event()` orqali ketadi).
    """
    payload = security.verify_token(token)  # muddat/imzo — xato bo'lsa TokenError

    employee = employee_by_telegram(db, telegram_user_id)
    if employee is None:
        raise UnknownEmployee

    if (
        employee.location_id is not None
        and employee.location_id != payload.location_id
    ):
        location = db.get(models.Location, payload.location_id)
        raise WrongLocation(location.name if location else f"#{payload.location_id}")

    consume_token(db, payload, employee.id, at)

    moment = at or now_local()
    attendance = get_attendance(db, employee.id, moment.date())
    event_type = forced_type or suggest_event_type(attendance, employee.schedule, moment)

    event = record_event(
        db,
        employee,
        event_type,
        moment,
        source=EventSource.QR,
        location_id=payload.location_id,
        token_nonce=payload.replay_key,
    )
    attendance = get_attendance(db, employee.id, moment.date())
    assert attendance is not None  # record_event() uni yaratadi

    return ScanResult(
        employee=employee,
        event=event,
        attendance=attendance,
        event_type=event_type,
        late_minutes=attendance.late_minutes,
        was_auto_detected=forced_type is None,
    )


def correct_event(
    db: Session,
    event_id: int,
    new_type: EventType,
    actor: str,
    *,
    by_telegram_user_id: int | None = None,
) -> ScanResult:
    """Yozuvning turini o'zgartiradi (xodim "aslida ketyapman" desa).

    `by_telegram_user_id` berilsa — chaqiruv xodimning o'zidan kelgan, shuning
    uchun ikki cheklov qo'llanadi:

    * yozuv **o'ziga** tegishli bo'lishi kerak. Bu majburiy: bot tugmasining
      `callback_data` sida `event_id` bor va uni qo'lda o'zgartirib yuborish
      mumkin, ya'ni tekshirmasak boshqa xodimning davomatini tuzatib qo'ysa
      bo'lardi;
    * yozuv **bugungi** bo'lishi kerak — o'tgan kunlarni faqat admin tuzatadi.

    Adminning tuzatishlarida (`by_telegram_user_id=None`) cheklov yo'q.
    """
    event = db.get(AttendanceEvent, event_id)
    if event is None:
        raise AttendanceError("Tuzatish uchun yozuv topilmadi.")

    if by_telegram_user_id is not None:
        owner = db.get(Employee, event.employee_id)
        if owner is None or owner.telegram_user_id != by_telegram_user_id:
            # Ataylab noaniq xabar: boshqa xodimning yozuvi borligini oshkor qilmaymiz.
            raise AttendanceError("Tuzatish uchun yozuv topilmadi.")
        if event.work_date != now_local().date():
            raise AttendanceError(
                "O'tgan kunlarni faqat administrator tuzatadi. Unga murojaat qiling."
            )

    old_type = event.event_type
    if old_type == new_type:
        employee = db.get(Employee, event.employee_id)
        attendance = get_attendance(db, event.employee_id, event.work_date)
        assert employee is not None and attendance is not None
        return ScanResult(employee, event, attendance, new_type, attendance.late_minutes, False)

    event.event_type = new_type
    db.flush()
    employee = db.get(Employee, event.employee_id)
    assert employee is not None
    recompute_day(db, employee, event.work_date)
    log_audit(
        db,
        actor,
        "correct_event",
        "attendance_event",
        event.id,
        f"{old_type.value} -> {new_type.value}",
    )
    attendance = get_attendance(db, employee.id, event.work_date)
    assert attendance is not None
    return ScanResult(employee, event, attendance, new_type, attendance.late_minutes, False)


# --------------------------------------------------------------------------- #
# Kunlik xulosani hisoblash
# --------------------------------------------------------------------------- #


def get_attendance(db: Session, employee_id: int, day: date) -> Attendance | None:
    return db.scalars(
        select(Attendance).where(
            Attendance.employee_id == employee_id, Attendance.work_date == day
        )
    ).first()


def recompute_day(db: Session, employee: Employee, day: date) -> Attendance:
    """Kunning xom yozuvlaridan `attendance` qatorini qaytadan yasaydi."""
    events = db.scalars(
        select(AttendanceEvent)
        .where(
            AttendanceEvent.employee_id == employee.id,
            AttendanceEvent.work_date == day,
            AttendanceEvent.is_voided.is_(False),
        )
        .order_by(AttendanceEvent.happened_at)
    ).all()

    attendance = get_attendance(db, employee.id, day)
    if attendance is None:
        attendance = Attendance(employee_id=employee.id, work_date=day)
        db.add(attendance)

    def first_of(kind: EventType) -> datetime | None:
        return next((e.happened_at for e in events if e.event_type == kind), None)

    def last_of(kind: EventType) -> datetime | None:
        return next((e.happened_at for e in reversed(events) if e.event_type == kind), None)

    # Kelish — kunning eng birinchi IN'i; ketish — eng oxirgi OUT.
    attendance.check_in_at = first_of(EventType.IN)
    attendance.lunch_out_at = first_of(EventType.LUNCH_OUT)
    attendance.lunch_in_at = last_of(EventType.LUNCH_IN)
    attendance.check_out_at = last_of(EventType.OUT)
    if events:
        attendance.source = events[0].source

    schedule = employee.schedule
    _apply_metrics(attendance, schedule, day)
    attendance.status = _resolve_status(db, attendance, employee, schedule, day)
    db.flush()
    return attendance


def _apply_metrics(attendance: Attendance, schedule: Schedule, day: date) -> None:
    """Kechikish / erta ketish / tushlik oshig'i / ishlangan vaqtni hisoblaydi."""
    scheduled_start = combine(day, schedule.start_time)
    scheduled_end = combine(day, schedule.end_time)

    if attendance.check_in_at is not None:
        attendance.late_minutes = max(0, minutes_between(scheduled_start, attendance.check_in_at))
    else:
        attendance.late_minutes = 0
    attendance.billable_late_minutes = max(0, attendance.late_minutes - schedule.grace_minutes)

    if attendance.check_out_at is not None:
        attendance.early_leave_minutes = max(
            0, minutes_between(attendance.check_out_at, scheduled_end)
        )
    else:
        attendance.early_leave_minutes = 0

    # Tushlik: ikkalasi qayd etilgan bo'lsa haqiqiy vaqt, aks holda jadvaldagi
    # me'yor ayiriladi. Aks holda tushlikni qayd etmaslik foydali bo'lib qolardi.
    lunch_taken = schedule.lunch_minutes
    if attendance.lunch_out_at is not None and attendance.lunch_in_at is not None:
        lunch_taken = max(0, minutes_between(attendance.lunch_out_at, attendance.lunch_in_at))
    attendance.lunch_overrun_minutes = max(0, lunch_taken - schedule.lunch_minutes)

    if attendance.check_in_at is not None and attendance.check_out_at is not None:
        gross = max(0, minutes_between(attendance.check_in_at, attendance.check_out_at))
        attendance.worked_minutes = max(0, gross - lunch_taken)
    else:
        attendance.worked_minutes = 0


def _resolve_status(
    db: Session, attendance: Attendance, employee: Employee, schedule: Schedule, day: date
) -> DayStatus:
    if is_holiday(db, day) is not None or not schedule.is_work_day(day):
        # Bayram/dam olish kunida ishlagan bo'lsa ham status HOLIDAY qoladi —
        # ishlangan vaqt `worked_minutes` da ko'rinadi (qo'shimcha ish haqi uchun).
        return DayStatus.HOLIDAY
    if leave_for(db, employee.id, day) is not None:
        return DayStatus.LEAVE
    if attendance.check_in_at is None:
        return DayStatus.ABSENT
    if attendance.check_out_at is None:
        return DayStatus.INCOMPLETE
    if attendance.billable_late_minutes > 0:
        return DayStatus.LATE
    return DayStatus.PRESENT


def recompute_range(db: Session, employee: Employee, start: date, end: date) -> None:
    """Oraliqdagi har bir kunni qayta hisoblaydi (jadval/bayram o'zgarganda kerak)."""
    from app.timeutil import iter_days

    for day in iter_days(start, end):
        recompute_day(db, employee, day)


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #


def log_audit(
    db: Session,
    actor: str,
    action: str,
    entity: str = "",
    entity_id: int | str = "",
    details: str = "",
) -> None:
    db.add(
        models.AuditLog(
            at=now_local(),
            actor=actor,
            action=action,
            entity=entity,
            entity_id=str(entity_id),
            details=details,
        )
    )
