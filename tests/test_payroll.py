"""Oylik hisob-kitobi testlari.

2026 yil iyul: 23 ta ish kuni (Du–Ju), bayramsiz.
Jadval: 09:00–18:00, tushlik 60 daq -> kunlik norma 480 daqiqa.
Oylik norma: 23 x 480 = 11 040 daqiqa. Oylik: 10 000 000 so'm.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from app import attendance as att_mod
from app import payroll as payroll_mod
from app.models import EventType, Holiday, Leave, LeaveKind
from app.timeutil import iter_days, month_bounds

PERIOD = "2026-07"
WORK_DAYS = 23
DAILY_MINUTES = 480
MONTH_MINUTES = WORK_DAYS * DAILY_MINUTES  # 11 040
SALARY = Decimal("10000000")


def work_days_of(schedule, period: str = PERIOD) -> list[date]:
    start, end = month_bounds(period)
    return [d for d in iter_days(start, end) if schedule.is_work_day(d)]


def full_day(db, employee, day: date, arrive: time = time(9, 0), leave: time = time(18, 0)) -> None:
    att_mod.record_event(db, employee, EventType.IN, datetime.combine(day, arrive))
    att_mod.record_event(db, employee, EventType.OUT, datetime.combine(day, leave))


def fill_month(db, employee, schedule, **kwargs) -> None:
    for day in work_days_of(schedule):
        full_day(db, employee, day, **kwargs)


# --------------------------------------------------------------------------- #
# Asosiy holatlar
# --------------------------------------------------------------------------- #


def test_month_has_expected_norm(db, employee, schedule):
    res = payroll_mod.compute_employee(db, employee, PERIOD)
    assert res.scheduled_days == WORK_DAYS
    assert res.scheduled_minutes == MONTH_MINUTES


def test_perfect_month_pays_full_salary(db, employee, schedule):
    fill_month(db, employee, schedule)
    res = payroll_mod.compute_employee(db, employee, PERIOD)

    assert res.worked_days == WORK_DAYS
    assert res.absent_days == 0
    assert res.late_count == 0
    assert res.unpaid_minutes == 0
    assert res.accrued == SALARY
    assert res.unpaid_time_deduction == Decimal("0.00")
    assert res.net_payable == SALARY


def test_no_attendance_at_all_pays_nothing(db, employee, schedule):
    res = payroll_mod.compute_employee(db, employee, PERIOD)
    assert res.absent_days == WORK_DAYS
    assert res.worked_days == 0
    assert res.unpaid_minutes == MONTH_MINUTES
    assert res.net_payable == Decimal("0.00")
    assert res.unpaid_time_deduction == SALARY


def test_one_absent_day_deducts_one_day(db, employee, schedule):
    days = work_days_of(schedule)
    for day in days[1:]:
        full_day(db, employee, day)

    res = payroll_mod.compute_employee(db, employee, PERIOD)
    assert res.absent_days == 1
    assert res.worked_days == WORK_DAYS - 1
    assert res.unpaid_minutes == DAILY_MINUTES

    expected = (SALARY * Decimal(MONTH_MINUTES - DAILY_MINUTES) / Decimal(MONTH_MINUTES)).quantize(
        Decimal("0.01")
    )
    assert res.accrued == expected
    assert res.net_payable == expected


# --------------------------------------------------------------------------- #
# Kechikish
# --------------------------------------------------------------------------- #


def test_late_within_grace_costs_nothing(db, employee, schedule):
    """9:04 da kelish — 5 daqiqalik muhlat ichida, oylik to'liq."""
    days = work_days_of(schedule)
    full_day(db, employee, days[0], arrive=time(9, 4))
    for day in days[1:]:
        full_day(db, employee, day)

    res = payroll_mod.compute_employee(db, employee, PERIOD)
    assert res.total_late_minutes == 4
    assert res.late_count == 0
    assert res.unpaid_minutes == 0
    assert res.net_payable == SALARY


def test_half_hour_late_deducts_25_minutes(db, employee, schedule):
    """Foydalanuvchi so'ragan asosiy holat: yarim soat kechikish.

    30 daqiqa kechikdi, 5 daqiqa muhlat -> 25 daqiqa to'lanmaydi.
    """
    days = work_days_of(schedule)
    full_day(db, employee, days[0], arrive=time(9, 30))
    for day in days[1:]:
        full_day(db, employee, day)

    res = payroll_mod.compute_employee(db, employee, PERIOD)
    assert res.late_count == 1
    assert res.total_late_minutes == 30
    assert res.unpaid_minutes == 25

    expected = (SALARY * Decimal(MONTH_MINUTES - 25) / Decimal(MONTH_MINUTES)).quantize(
        Decimal("0.01")
    )
    assert res.accrued == expected
    # 25 daqiqa ~ 22 645 so'm (daqiqasi ~906 so'm)
    assert Decimal("22000") < res.unpaid_time_deduction < Decimal("23000")


def test_early_leave_and_lunch_overrun_add_up(db, employee, schedule):
    """Kechikish + erta ketish + tushlik oshig'i — har biriga grace alohida."""
    days = work_days_of(schedule)
    day = days[0]
    att_mod.record_event(db, employee, EventType.IN, datetime.combine(day, time(9, 20)))
    att_mod.record_event(db, employee, EventType.LUNCH_OUT, datetime.combine(day, time(13, 0)))
    att_mod.record_event(db, employee, EventType.LUNCH_IN, datetime.combine(day, time(14, 30)))
    att_mod.record_event(db, employee, EventType.OUT, datetime.combine(day, time(17, 30)))
    for other in days[1:]:
        full_day(db, employee, other)

    res = payroll_mod.compute_employee(db, employee, PERIOD)
    # kechikish 20-5=15, erta ketish 30-5=25, tushlik oshig'i 30-5=25
    assert res.total_late_minutes == 20
    assert res.total_early_leave_minutes == 30
    assert res.total_lunch_overrun_minutes == 30
    assert res.unpaid_minutes == 15 + 25 + 25


def test_missing_checkout_costs_nothing_extra_but_is_flagged(db, employee, schedule):
    """Ketishini qayd etmagan kun — kunlik tafsilotda izoh bilan belgilanadi."""
    days = work_days_of(schedule)
    att_mod.record_event(db, employee, EventType.IN, datetime.combine(days[0], time(9, 0)))
    for day in days[1:]:
        full_day(db, employee, day)

    res = payroll_mod.compute_employee(db, employee, PERIOD)
    assert res.worked_days == WORK_DAYS
    flagged = [d for d in res.days if d.note == "ketishi qayd etilmagan"]
    assert len(flagged) == 1
    assert flagged[0].day == days[0]


# --------------------------------------------------------------------------- #
# Bayram, ta'til
# --------------------------------------------------------------------------- #


def test_holiday_reduces_the_norm(db, employee, schedule):
    days = work_days_of(schedule)
    db.add(Holiday(day=days[0], name="Sinov bayrami"))
    db.flush()

    res = payroll_mod.compute_employee(db, employee, PERIOD)
    assert res.scheduled_days == WORK_DAYS - 1
    assert res.scheduled_minutes == (WORK_DAYS - 1) * DAILY_MINUTES
    # O'sha kunda kelmagani jarima emas
    assert days[0] not in [d.day for d in res.days]


def test_holiday_absence_is_not_penalised(db, employee, schedule):
    days = work_days_of(schedule)
    db.add(Holiday(day=days[0], name="Sinov bayrami"))
    db.flush()
    for day in days[1:]:
        full_day(db, employee, day)

    res = payroll_mod.compute_employee(db, employee, PERIOD)
    assert res.absent_days == 0
    assert res.net_payable == SALARY


def test_paid_leave_keeps_full_salary(db, employee, schedule):
    start, end = month_bounds(PERIOD)
    db.add(
        Leave(
            employee_id=employee.id,
            start_date=start,
            end_date=end,
            kind=LeaveKind.VACATION,
            is_paid=True,
        )
    )
    db.flush()

    res = payroll_mod.compute_employee(db, employee, PERIOD)
    assert res.leave_days == WORK_DAYS
    assert res.absent_days == 0
    assert res.unpaid_minutes == 0
    assert res.net_payable == SALARY


def test_unpaid_leave_is_not_paid(db, employee, schedule):
    start, end = month_bounds(PERIOD)
    db.add(
        Leave(
            employee_id=employee.id,
            start_date=start,
            end_date=end,
            kind=LeaveKind.UNPAID,
            is_paid=False,
        )
    )
    db.flush()

    res = payroll_mod.compute_employee(db, employee, PERIOD)
    assert res.leave_days == WORK_DAYS
    assert res.absent_days == 0
    assert res.unpaid_minutes == MONTH_MINUTES
    assert res.net_payable == Decimal("0.00")


def test_hire_date_mid_month_shrinks_the_norm(db, employee, schedule):
    """Oy o'rtasida ishga kirgan xodimga oldingi kunlar hisoblanmaydi."""
    employee.hired_at = date(2026, 7, 16)
    db.flush()
    res = payroll_mod.compute_employee(db, employee, PERIOD)
    assert res.scheduled_days < WORK_DAYS
    assert all(d.day >= date(2026, 7, 16) for d in res.days)


# --------------------------------------------------------------------------- #
# Ustama kamayishi (intizom) va cheklov
# --------------------------------------------------------------------------- #


def test_bonus_reduction_applies_after_free_late_count(db, employee, schedule):
    days = work_days_of(schedule)
    for day in days[:4]:
        full_day(db, employee, day, arrive=time(9, 20))
    for day in days[4:]:
        full_day(db, employee, day)

    policy = payroll_mod.DeductionPolicy(
        free_late_count=2, per_extra_late=Decimal("50000")
    )
    res = payroll_mod.compute_employee(db, employee, PERIOD, policy)
    assert res.late_count == 4
    # 4 kechikish - 2 bepul = 2 x 50 000
    assert res.bonus_reduction == Decimal("100000.00")
    assert res.net_payable == res.accrued - Decimal("100000")


def test_heavy_late_adds_extra(db, employee, schedule):
    days = work_days_of(schedule)
    full_day(db, employee, days[0], arrive=time(10, 0))  # 60 daq — "og'ir"
    full_day(db, employee, days[1], arrive=time(9, 15))  # 15 daq — oddiy
    for day in days[2:]:
        full_day(db, employee, day)

    policy = payroll_mod.DeductionPolicy(
        free_late_count=0,
        per_extra_late=Decimal("30000"),
        heavy_late_threshold_minutes=30,
        per_heavy_late=Decimal("70000"),
    )
    res = payroll_mod.compute_employee(db, employee, PERIOD, policy)
    assert res.late_count == 2
    assert res.heavy_late_count == 1
    assert res.bonus_reduction == Decimal("130000.00")  # 2x30 000 + 1x70 000


def test_deduction_is_capped_at_20_percent(db, employee, schedule):
    """Qonuniy xavfsizlik chegarasi: ustama kamayishi hisoblangan summaning
    20%idan oshmaydi, jarima summalari qanchalik katta bo'lsa ham."""
    fill_month(db, employee, schedule, arrive=time(9, 30))

    policy = payroll_mod.DeductionPolicy(
        free_late_count=0,
        per_extra_late=Decimal("5000000"),  # ataylab bema'ni katta
        max_deduction_percent=Decimal("20"),
    )
    res = payroll_mod.compute_employee(db, employee, PERIOD, policy)
    cap = (res.accrued * Decimal("20") / Decimal("100")).quantize(Decimal("0.01"))
    assert res.bonus_reduction == cap
    assert res.net_payable == res.accrued - cap
    assert res.net_payable > 0


def test_default_policy_has_no_bonus_reduction(db, employee, schedule):
    """Standart holatda faqat ishlanmagan vaqt hisoblanadi."""
    fill_month(db, employee, schedule, arrive=time(9, 45))
    res = payroll_mod.compute_employee(db, employee, PERIOD)
    assert res.bonus_reduction == Decimal("0.00")
    assert res.net_payable == res.accrued


def test_zero_salary_is_safe(db, employee, schedule):
    employee.monthly_salary = 0
    db.flush()
    res = payroll_mod.compute_employee(db, employee, PERIOD)
    assert res.net_payable == Decimal("0.00")


# --------------------------------------------------------------------------- #
# Saqlash va eksport
# --------------------------------------------------------------------------- #


def test_save_results_is_idempotent(db, employee, schedule):
    fill_month(db, employee, schedule)
    results = payroll_mod.compute_period(db, PERIOD)

    first = payroll_mod.save_results(db, results)
    second = payroll_mod.save_results(db, results)
    assert len(first) == len(second) == 1
    assert first[0].id == second[0].id  # yangi qator yasamaydi
    assert second[0].net_payable == SALARY


def test_excel_export_produces_a_workbook(db, employee, schedule):
    from app import excel as excel_mod

    fill_month(db, employee, schedule, arrive=time(9, 30))
    results = payroll_mod.compute_period(db, PERIOD)

    payroll_bytes = excel_mod.payroll_workbook(results, PERIOD)
    assert payroll_bytes[:2] == b"PK"  # xlsx = zip
    assert len(payroll_bytes) > 5000

    tabel_bytes = excel_mod.attendance_workbook(db, PERIOD)
    assert tabel_bytes[:2] == b"PK"
