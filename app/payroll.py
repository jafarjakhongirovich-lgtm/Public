"""Oylik hisob-kitobi.

HISOB MODELI (va nega shunday)
------------------------------
O'zbekiston Mehnat kodeksi bo'yicha ish haqidan to'g'ridan-to'g'ri "jarima"
ushlash cheklangan. Shuning uchun tizim ikki xil summani **alohida** hisoblaydi:

1. `unpaid_time_deduction` — **ishlanmagan vaqt**. Bu ushlanma emas, shunchaki
   ishlanmagan daqiqalar uchun haq hisoblanmaydi. Qonuniy asosi mustahkam.
2. `bonus_reduction` — **intizom uchun ustama/mukofot kamayishi**. Bu ixtiyoriy
   rag'batlantirish qismidan ayiriladi va `max_deduction_percent` bilan
   cheklangan (ish haqidan cheksiz ushlab qolishning oldini oladi).

Yakuniy summa:

    hisoblangan (accrued) = oylik x (to'lanadigan daqiqa / jadvaldagi daqiqa)
    to'lanadigan (net)    = hisoblangan - ustama kamayishi

TO'LANMAYDIGAN DAQIQALAR
------------------------
* kechikish (grace ayirilgan)
* erta ketish (grace ayirilgan)
* tushlikdan oshib qolgan vaqt (grace ayirilgan)
* sababsiz kelmagan kun — to'liq kunlik norma
* to'lovsiz ruxsat kuni — to'liq kunlik norma

Bayram va dam olish kunlari `scheduled_days` ga umuman kirmaydi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import attendance as att_mod
from app.models import (
    Attendance,
    DayStatus,
    Employee,
    PayrollItem,
    Schedule,
)
from app.timeutil import iter_days, month_bounds, now_local

CENT = Decimal("0.01")


def _money(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class DeductionPolicy:
    """Intizom uchun ustama kamayishi qoidalari.

    Standart holatda hammasi nolga teng — ya'ni faqat ishlanmagan vaqt
    hisoblanadi. Summalarni admin panelda yoki bu yerda sozlash mumkin.
    """

    # Oyda shu martagacha kechikish "kechiriladi" (ustama kamaymaydi)
    free_late_count: int = 0
    # Undan keyingi har bir kechikish uchun summa (so'm)
    per_extra_late: Decimal = Decimal("0")
    # Shu daqiqadan ko'p kechikish "og'ir" hisoblanadi
    heavy_late_threshold_minutes: int = 30
    # Har bir "og'ir" kechikish uchun qo'shimcha summa (so'm)
    per_heavy_late: Decimal = Decimal("0")
    # Sababsiz kelmagan har bir kun uchun qo'shimcha summa (so'm)
    per_absent_day: Decimal = Decimal("0")
    # Xavfsizlik chegarasi: ustama kamayishi hisoblangan summaning shu %idan
    # oshmaydi. Mehnat kodeksidagi ushlanma cheklovini hurmat qilish uchun.
    max_deduction_percent: Decimal = Decimal("20")


DEFAULT_POLICY = DeductionPolicy()


@dataclass
class DayBreakdown:
    """Bir kunning hisobga qanday tushgani — hisobot va nizolar uchun."""

    day: date
    status: DayStatus
    late_minutes: int = 0
    billable_late_minutes: int = 0
    early_leave_minutes: int = 0
    lunch_overrun_minutes: int = 0
    unpaid_minutes: int = 0
    note: str = ""


@dataclass
class PayrollResult:
    employee_id: int
    employee_name: str
    period: str
    monthly_salary: Decimal

    scheduled_days: int = 0
    worked_days: int = 0
    absent_days: int = 0
    leave_days: int = 0
    late_count: int = 0
    heavy_late_count: int = 0

    total_late_minutes: int = 0
    total_early_leave_minutes: int = 0
    total_lunch_overrun_minutes: int = 0
    scheduled_minutes: int = 0
    unpaid_minutes: int = 0

    accrued: Decimal = Decimal("0")
    unpaid_time_deduction: Decimal = Decimal("0")
    bonus_reduction: Decimal = Decimal("0")
    net_payable: Decimal = Decimal("0")

    days: list[DayBreakdown] = field(default_factory=list)

    @property
    def paid_minutes(self) -> int:
        return max(0, self.scheduled_minutes - self.unpaid_minutes)


def billable_minutes(record: Attendance, schedule: Schedule) -> int:
    """Bir kun uchun to'lanmaydigan daqiqalar (grace har toifaga alohida)."""
    late = max(0, record.late_minutes - schedule.grace_minutes)
    early = max(0, record.early_leave_minutes - schedule.grace_minutes)
    lunch = max(0, record.lunch_overrun_minutes - schedule.grace_minutes)
    return late + early + lunch


def compute_employee(
    db: Session,
    employee: Employee,
    period: str,
    policy: DeductionPolicy = DEFAULT_POLICY,
) -> PayrollResult:
    """Bir xodimning bir oylik hisobini chiqaradi (bazaga yozmaydi)."""
    start, end = month_bounds(period)
    # Ishga kirgan sanadan oldingi kunlar hisobga olinmaydi
    if employee.hired_at is not None and employee.hired_at > start:
        start = employee.hired_at

    schedule = employee.schedule
    daily_minutes = schedule.scheduled_minutes()
    result = PayrollResult(
        employee_id=employee.id,
        employee_name=employee.full_name,
        period=period,
        monthly_salary=_money(employee.monthly_salary),
    )

    records = {
        row.work_date: row
        for row in db.scalars(
            select(Attendance).where(
                Attendance.employee_id == employee.id,
                Attendance.work_date >= start,
                Attendance.work_date <= end,
            )
        ).all()
    }

    for day in iter_days(start, end):
        if not schedule.is_work_day(day) or att_mod.is_holiday(db, day) is not None:
            continue

        result.scheduled_days += 1
        result.scheduled_minutes += daily_minutes

        leave = att_mod.leave_for(db, employee.id, day)
        if leave is not None:
            result.leave_days += 1
            if leave.is_paid:
                result.days.append(
                    DayBreakdown(day, DayStatus.LEAVE, note=f"{leave.kind.value} (to'lanadi)")
                )
            else:
                result.unpaid_minutes += daily_minutes
                result.days.append(
                    DayBreakdown(
                        day,
                        DayStatus.LEAVE,
                        unpaid_minutes=daily_minutes,
                        note=f"{leave.kind.value} (to'lanmaydi)",
                    )
                )
            continue

        record = records.get(day)
        if record is None or record.check_in_at is None:
            result.absent_days += 1
            result.unpaid_minutes += daily_minutes
            result.days.append(
                DayBreakdown(
                    day, DayStatus.ABSENT, unpaid_minutes=daily_minutes, note="kelmadi"
                )
            )
            continue

        result.worked_days += 1
        day_unpaid = billable_minutes(record, schedule)
        result.unpaid_minutes += day_unpaid
        result.total_late_minutes += record.late_minutes
        result.total_early_leave_minutes += record.early_leave_minutes
        result.total_lunch_overrun_minutes += record.lunch_overrun_minutes

        if record.billable_late_minutes > 0:
            result.late_count += 1
            if record.late_minutes > policy.heavy_late_threshold_minutes:
                result.heavy_late_count += 1

        note = ""
        if record.check_out_at is None:
            note = "ketishi qayd etilmagan"
        result.days.append(
            DayBreakdown(
                day=day,
                status=record.status,
                late_minutes=record.late_minutes,
                billable_late_minutes=record.billable_late_minutes,
                early_leave_minutes=record.early_leave_minutes,
                lunch_overrun_minutes=record.lunch_overrun_minutes,
                unpaid_minutes=day_unpaid,
                note=note,
            )
        )

    _apply_money(result, policy)
    return result


def _apply_money(result: PayrollResult, policy: DeductionPolicy) -> None:
    """Daqiqalarni pulga aylantiradi va ustama kamayishini qo'llaydi."""
    salary = result.monthly_salary

    if result.scheduled_minutes <= 0 or salary <= 0:
        # Oyda ish kuni yo'q yoki oylik belgilanmagan.
        result.accrued = _money(0)
        result.unpaid_time_deduction = _money(0)
        result.bonus_reduction = _money(0)
        result.net_payable = _money(0)
        return

    ratio = Decimal(result.paid_minutes) / Decimal(result.scheduled_minutes)
    result.accrued = _money(salary * ratio)
    result.unpaid_time_deduction = _money(salary - result.accrued)

    extra_late = max(0, result.late_count - policy.free_late_count)
    raw_bonus_cut = (
        Decimal(extra_late) * Decimal(policy.per_extra_late)
        + Decimal(result.heavy_late_count) * Decimal(policy.per_heavy_late)
        + Decimal(result.absent_days) * Decimal(policy.per_absent_day)
    )
    cap = result.accrued * Decimal(policy.max_deduction_percent) / Decimal("100")
    result.bonus_reduction = _money(min(raw_bonus_cut, cap))
    result.net_payable = _money(result.accrued - result.bonus_reduction)


def compute_period(
    db: Session,
    period: str,
    policy: DeductionPolicy = DEFAULT_POLICY,
    *,
    only_active: bool = True,
) -> list[PayrollResult]:
    """Barcha xodimlar uchun oylik hisobi."""
    query = select(Employee).order_by(Employee.full_name)
    if only_active:
        query = query.where(Employee.is_active.is_(True))
    return [compute_employee(db, emp, period, policy) for emp in db.scalars(query).all()]


def save_results(db: Session, results: list[PayrollResult]) -> list[PayrollItem]:
    """Hisob natijalarini `payroll_items` ga yozadi (mavjud bo'lsa yangilaydi)."""
    saved: list[PayrollItem] = []
    for res in results:
        item = db.scalars(
            select(PayrollItem).where(
                PayrollItem.employee_id == res.employee_id,
                PayrollItem.period == res.period,
            )
        ).first()
        if item is None:
            item = PayrollItem(employee_id=res.employee_id, period=res.period)
            db.add(item)

        item.monthly_salary = res.monthly_salary
        item.scheduled_days = res.scheduled_days
        item.worked_days = res.worked_days
        item.absent_days = res.absent_days
        item.leave_days = res.leave_days
        item.late_count = res.late_count
        item.total_late_minutes = res.total_late_minutes
        item.total_early_leave_minutes = res.total_early_leave_minutes
        item.total_lunch_overrun_minutes = res.total_lunch_overrun_minutes
        item.unpaid_minutes = res.unpaid_minutes
        item.unpaid_time_deduction = res.unpaid_time_deduction
        item.bonus_reduction = res.bonus_reduction
        item.net_payable = res.net_payable
        item.computed_at = now_local()
        saved.append(item)
    db.flush()
    return saved
