"""Baza modellari.

VAQT BO'YICHA KELISHUV
----------------------
Bazadagi barcha `DateTime` maydonlar **mahalliy vaqtda** (settings.timezone,
odatda Asia/Tashkent) va **naive** (tz belgisi yo'q) saqlanadi. Sabab: butun
tizim bitta vaqt zonasida ishlaydi va oylik hisobi mahalliy kalendar kunига
bog'langan. Har doim `app.timeutil.now_local()` dan foydalaning, `datetime.now()`
yoki `utcnow()` dan emas.

Yagona istisno — QR token ichidagi `issued_at`, u UTC epoch (butun son).
"""

from __future__ import annotations

import enum
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class EventType(str, enum.Enum):
    """Xodim qayd etadigan harakat turlari."""

    IN = "IN"  # ishga keldi
    LUNCH_OUT = "LUNCH_OUT"  # tushlikka chiqdi
    LUNCH_IN = "LUNCH_IN"  # tushlikdan qaytdi
    OUT = "OUT"  # ishdan ketdi


class EventSource(str, enum.Enum):
    """Qayd qaysi kanal orqali tushdi."""

    QR = "QR"  # ofisdagi ekrandagi QR skanerlandi
    MANUAL = "MANUAL"  # admin qo'lda kiritdi
    FACE_ID = "FACE_ID"  # kelajakda: kamera + yuz tanish


class DayStatus(str, enum.Enum):
    PRESENT = "PRESENT"  # vaqtida keldi
    LATE = "LATE"  # kechikdi
    ABSENT = "ABSENT"  # sababsiz kelmadi
    LEAVE = "LEAVE"  # ta'til / kasallik / ruxsat
    HOLIDAY = "HOLIDAY"  # bayram yoki dam olish kuni
    INCOMPLETE = "INCOMPLETE"  # keldi, lekin ketishini qayd etmadi


class LeaveKind(str, enum.Enum):
    VACATION = "VACATION"  # mehnat ta'tili
    SICK = "SICK"  # kasallik varaqasi
    UNPAID = "UNPAID"  # to'lovsiz ruxsat
    BUSINESS = "BUSINESS"  # xizmat safari


# --------------------------------------------------------------------------- #
# Tashkiliy tuzilma
# --------------------------------------------------------------------------- #


class Location(Base):
    """Ofis / filial. Har bir QR ekrani bitta lokatsiyaga tegishli."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Ixtiyoriy: ofis internetining tashqi IP'lari (vergul bilan, CIDR ham bo'ladi).
    # To'ldirilsa, QR faqat shu IP'lardan skanerlanishi mumkin.
    ip_allowlist: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    kiosks: Mapped[list[Kiosk]] = relationship(back_populates="location")


class Kiosk(Base):
    """QR ko'rsatib turuvchi ekran (TV, monitor, planshet).

    `api_key` — kiosk sahifasining maxfiy manzili. Faqat shu kalitni bilgan
    brauzer QR olishi mumkin, aks holda tokenlarni masofadan yasab olish
    mumkin bo'lib qolardi.
    """

    __tablename__ = "kiosks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    api_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    location: Mapped[Location] = relationship(back_populates="kiosks")


class Schedule(Base):
    """Ish jadvali. Bir nechta xodim bitta jadvalga ulanishi mumkin."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    lunch_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    lunch_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    # Tushlikka ajratilgan daqiqa. Bundan oshib ketgani ishlanmagan vaqt hisoblanadi.
    lunch_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    # Ish kunlari: ISO hafta kunlari, vergul bilan. Du=1 ... Ya=7
    work_days: Mapped[str] = mapped_column(String(20), default="1,2,3,4,5", nullable=False)
    # Jarima hisoblanmaydigan muhlat (daqiqa)
    grace_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    def work_weekdays(self) -> set[int]:
        return {int(x) for x in self.work_days.split(",") if x.strip()}

    def is_work_day(self, day: date) -> bool:
        return day.isoweekday() in self.work_weekdays()

    def scheduled_minutes(self) -> int:
        """Kunlik sof ish vaqti (tushlik chiqarilgan holda), daqiqada."""
        total = (self.end_time.hour * 60 + self.end_time.minute) - (
            self.start_time.hour * 60 + self.start_time.minute
        )
        return max(0, total - self.lunch_minutes)


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    # Telegram user_id — QR skanerlaganda xodimni shu bo'yicha tanib olamiz.
    telegram_user_id: Mapped[int | None] = mapped_column(
        Integer, unique=True, nullable=True, index=True
    )
    telegram_username: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    monthly_salary: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id"), nullable=False)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    hired_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    schedule: Mapped[Schedule] = relationship()
    location: Mapped[Location | None] = relationship()


# --------------------------------------------------------------------------- #
# Davomat
# --------------------------------------------------------------------------- #


class AttendanceEvent(Base):
    """Har bir skanerlashning xom yozuvi. O'chirilmaydi — bu audit izi.

    `Attendance` esa shu yozuvlardan hisoblab chiqarilgan kunlik xulosa.
    """

    __tablename__ = "attendance_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False)
    happened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source: Mapped[EventSource] = mapped_column(
        Enum(EventSource), default=EventSource.QR, nullable=False
    )
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    kiosk_id: Mapped[int | None] = mapped_column(ForeignKey("kiosks.id"), nullable=True)
    # QR token nonce'si — qaysi token bilan kirganini kuzatish uchun
    token_nonce: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Bekor qilingan yozuv (xodim "xato" tugmasini bosdi yoki admin bekor qildi)
    is_voided: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    employee: Mapped[Employee] = relationship()


class Attendance(Base):
    """Bir xodimning bir kunlik yakuniy davomat xulosasi."""

    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("employee_id", "work_date", name="uq_attendance_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    check_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lunch_out_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lunch_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Xom kechikish (grace hisobga olinmagan) — hisobot uchun
    late_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Grace ayirilgandan keyin qolgani — ushlanma shundan hisoblanadi
    billable_late_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    early_leave_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lunch_overrun_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    worked_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[DayStatus] = mapped_column(
        Enum(DayStatus), default=DayStatus.ABSENT, nullable=False
    )
    source: Mapped[EventSource] = mapped_column(
        Enum(EventSource), default=EventSource.QR, nullable=False
    )
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    employee: Mapped[Employee] = relationship()


class UsedToken(Base):
    """Ishlatilgan QR tokenlar. Bitta token ikkinchi marta ishlamaydi (replay himoyasi)."""

    __tablename__ = "used_tokens"

    nonce: Mapped[str] = mapped_column(String(32), primary_key=True)
    location_id: Mapped[int] = mapped_column(Integer, nullable=False)
    issued_at_epoch: Mapped[int] = mapped_column(Integer, nullable=False)
    used_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    employee_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


# --------------------------------------------------------------------------- #
# Kalendar
# --------------------------------------------------------------------------- #


class Holiday(Base):
    __tablename__ = "holidays"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class Leave(Base):
    """Ta'til / kasallik / ruxsat. Bu kunlarga jarima qo'llanmaydi."""

    __tablename__ = "leaves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[LeaveKind] = mapped_column(Enum(LeaveKind), nullable=False)
    # To'lanadigan ta'tilmi? (mehnat ta'tili — ha, to'lovsiz ruxsat — yo'q)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    employee: Mapped[Employee] = relationship()


# --------------------------------------------------------------------------- #
# Oylik
# --------------------------------------------------------------------------- #


class PayrollItem(Base):
    """Bir xodimning bir oylik hisob-kitobi."""

    __tablename__ = "payroll_items"
    __table_args__ = (UniqueConstraint("employee_id", "period", name="uq_payroll_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    # "2026-07" ko'rinishida
    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)

    monthly_salary: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    scheduled_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    worked_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    absent_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leave_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    late_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    total_late_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_early_leave_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_lunch_overrun_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unpaid_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Ishlanmagan vaqt uchun ushlanma (Mehnat kodeksi bo'yicha qonuniy asos)
    unpaid_time_deduction: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    # Intizom uchun ustama/mukofot kamayishi (jarima emas)
    bonus_reduction: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    net_payable: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    computed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    employee: Mapped[Employee] = relationship()


class AuditLog(Base):
    """Qo'lda qilingan har bir o'zgarish izi. Tizimga ishonch shundan boshlanadi."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    entity_id: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    details: Mapped[str] = mapped_column(Text, default="", nullable=False)
