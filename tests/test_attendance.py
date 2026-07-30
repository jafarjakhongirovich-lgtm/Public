"""Davomat mantiqi: harakat turini taxmin qilish, skanerlash, hisob-kitob."""

from __future__ import annotations

import time as _time
from datetime import date, datetime, time

import pytest

from app import attendance as att_mod
from app import security
from app.models import DayStatus, EventSource, EventType, Holiday, Leave, LeaveKind

# 2026-07-15 — chorshanba, ish kuni
DAY = date(2026, 7, 15)


def at(hour: int, minute: int = 0) -> datetime:
    return datetime.combine(DAY, time(hour, minute))


def fresh_token(location_id: int) -> str:
    return security.issue_token(location_id, issued_at_epoch=int(_time.time()))


# --------------------------------------------------------------------------- #
# Harakat turini taxmin qilish
# --------------------------------------------------------------------------- #


def test_first_scan_is_check_in(db, employee, schedule):
    assert att_mod.suggest_event_type(None, schedule, at(9, 0)) == EventType.IN


def test_scan_during_lunch_window_is_lunch_out(db, employee, schedule):
    att_mod.record_event(db, employee, EventType.IN, at(9, 0))
    record = att_mod.get_attendance(db, employee.id, DAY)
    assert att_mod.suggest_event_type(record, schedule, at(13, 5)) == EventType.LUNCH_OUT


def test_scan_after_lunch_out_is_lunch_in(db, employee, schedule):
    att_mod.record_event(db, employee, EventType.IN, at(9, 0))
    att_mod.record_event(db, employee, EventType.LUNCH_OUT, at(13, 0))
    record = att_mod.get_attendance(db, employee.id, DAY)
    assert att_mod.suggest_event_type(record, schedule, at(13, 50)) == EventType.LUNCH_IN


def test_evening_scan_is_check_out(db, employee, schedule):
    att_mod.record_event(db, employee, EventType.IN, at(9, 0))
    att_mod.record_event(db, employee, EventType.LUNCH_OUT, at(13, 0))
    att_mod.record_event(db, employee, EventType.LUNCH_IN, at(14, 0))
    record = att_mod.get_attendance(db, employee.id, DAY)
    assert att_mod.suggest_event_type(record, schedule, at(18, 5)) == EventType.OUT


def test_late_afternoon_scan_is_check_out_not_lunch(db, employee, schedule):
    """Tushlik qayd etilmagan bo'lsa ham, ish tugashiga yaqin skan = ketish."""
    att_mod.record_event(db, employee, EventType.IN, at(9, 0))
    record = att_mod.get_attendance(db, employee.id, DAY)
    assert att_mod.suggest_event_type(record, schedule, at(17, 40)) == EventType.OUT


# --------------------------------------------------------------------------- #
# Skanerlash yo'li
# --------------------------------------------------------------------------- #


def test_scan_records_check_in(db, employee, location):
    result = att_mod.scan(db, 555001, fresh_token(location.id), at=at(9, 0))
    assert result.event_type == EventType.IN
    assert result.attendance.check_in_at == at(9, 0)
    assert result.attendance.status == DayStatus.INCOMPLETE  # hali ketmagan


def test_same_token_cannot_be_reused(db, employee, location):
    """Bir QR ni ikki marta ishlatib bo'lmaydi — asosiy aldash yo'li shu."""
    token = fresh_token(location.id)
    att_mod.scan(db, 555001, token, at=at(9, 0))
    with pytest.raises(att_mod.TokenAlreadyUsed):
        att_mod.scan(db, 555001, token, at=at(9, 1))


def test_token_cannot_be_shared_with_colleague(db, employee, schedule, location):
    """Xodim QR rasmini hamkasbiga bersa ham, token allaqachon ishlatilgan."""
    from app.models import Employee

    other = Employee(
        full_name="Karimov Bek",
        telegram_user_id=555002,
        monthly_salary=5_000_000,
        schedule_id=schedule.id,
        location_id=location.id,
    )
    db.add(other)
    db.flush()

    token = fresh_token(location.id)
    att_mod.scan(db, 555001, token, at=at(9, 0))
    with pytest.raises(att_mod.TokenAlreadyUsed):
        att_mod.scan(db, 555002, token, at=at(9, 0))


def test_unknown_telegram_user_rejected(db, employee, location):
    with pytest.raises(att_mod.UnknownEmployee):
        att_mod.scan(db, 999999, fresh_token(location.id), at=at(9, 0))


def test_wrong_office_rejected(db, employee, location):
    """Xodim boshqa ofisga bog'langan bo'lsa, u ofisning QR'i ishlamaydi."""
    from app.models import Location

    other = Location(name="Filial")
    db.add(other)
    db.flush()
    with pytest.raises(att_mod.WrongLocation):
        att_mod.scan(db, 555001, fresh_token(other.id), at=at(9, 0))


def test_expired_token_rejected_in_scan(db, employee, location):
    stale = security.issue_token(location.id, issued_at_epoch=int(_time.time()) - 300)
    with pytest.raises(security.ExpiredToken):
        att_mod.scan(db, 555001, stale, at=at(9, 0))


def test_correction_changes_event_type_and_recomputes(db, employee, location):
    """Bot tugmasi bilan «aslida ketyapman» deb tuzatish."""
    result = att_mod.scan(db, 555001, fresh_token(location.id), at=at(9, 0))
    assert result.attendance.check_in_at == at(9, 0)

    att_mod.record_event(db, employee, EventType.IN, at(9, 5))  # ikkinchi IN — noto'g'ri
    second = db.scalars(
        __import__("sqlalchemy").select(att_mod.AttendanceEvent).order_by(
            att_mod.AttendanceEvent.id.desc()
        )
    ).first()
    fixed = att_mod.correct_event(db, second.id, EventType.OUT, "tg:555001")
    assert fixed.attendance.check_out_at == at(9, 5)
    assert fixed.attendance.check_in_at == at(9, 0)  # birinchi IN saqlanib qoldi


def test_employee_cannot_correct_someone_elses_event(db, employee, schedule, location):
    """Bot tugmasidagi `event_id` ni qo'lda o'zgartirib yuborish mumkin, shuning
    uchun tuzatishda yozuv egasi tekshirilishi shart."""
    from app.models import Employee

    victim = Employee(
        full_name="Karimov Bek",
        telegram_user_id=555002,
        monthly_salary=5_000_000,
        schedule_id=schedule.id,
        location_id=location.id,
    )
    db.add(victim)
    db.flush()

    victim_event = att_mod.record_event(db, victim, EventType.IN, at(9, 0))

    with pytest.raises(att_mod.AttendanceError):
        att_mod.correct_event(
            db, victim_event.id, EventType.OUT, "tg:555001", by_telegram_user_id=555001
        )

    # Jabrlanuvchining yozuvi o'zgarmagan
    record = att_mod.get_attendance(db, victim.id, DAY)
    assert record.check_in_at == at(9, 0)
    assert record.check_out_at is None


def test_employee_can_correct_own_event(db, employee, location):
    from app.timeutil import now_local

    today = now_local().date()
    event = att_mod.record_event(
        db, employee, EventType.IN, datetime.combine(today, time(9, 0))
    )
    result = att_mod.correct_event(
        db, event.id, EventType.OUT, "tg:555001", by_telegram_user_id=555001
    )
    assert result.event_type == EventType.OUT


def test_employee_cannot_correct_past_days(db, employee, location):
    """O'tgan kunni xodim o'zgartira olmaydi — faqat admin."""
    event = att_mod.record_event(db, employee, EventType.IN, at(9, 0))  # 2026-07-15
    with pytest.raises(att_mod.AttendanceError):
        att_mod.correct_event(
            db, event.id, EventType.OUT, "tg:555001", by_telegram_user_id=555001
        )
    # Admin esa o'zgartira oladi
    result = att_mod.correct_event(db, event.id, EventType.OUT, "admin")
    assert result.event_type == EventType.OUT


def test_correcting_missing_event_is_rejected(db, employee):
    with pytest.raises(att_mod.AttendanceError):
        att_mod.correct_event(db, 999999, EventType.OUT, "admin")


def test_voided_event_is_excluded(db, employee, location):
    result = att_mod.scan(db, 555001, fresh_token(location.id), at=at(9, 30))
    att_mod.void_event(db, result.event.id, "admin", "xato skan")
    record = att_mod.get_attendance(db, employee.id, DAY)
    assert record.check_in_at is None
    assert record.status == DayStatus.ABSENT
    # Xom yozuv o'chirilmagan — audit izi qoladi
    assert db.get(att_mod.AttendanceEvent, result.event.id).is_voided is True


# --------------------------------------------------------------------------- #
# Kunlik hisob-kitob
# --------------------------------------------------------------------------- #


def test_on_time_arrival_has_no_late_minutes(db, employee):
    att_mod.record_event(db, employee, EventType.IN, at(8, 55))
    record = att_mod.get_attendance(db, employee.id, DAY)
    assert record.late_minutes == 0
    assert record.billable_late_minutes == 0


def test_late_within_grace_is_not_billable(db, employee):
    """5 daqiqalik grace: 9:04 da kelish hisobga olinmaydi."""
    att_mod.record_event(db, employee, EventType.IN, at(9, 4))
    record = att_mod.get_attendance(db, employee.id, DAY)
    assert record.late_minutes == 4
    assert record.billable_late_minutes == 0


def test_late_beyond_grace_is_billable(db, employee):
    """9:30 da kelish = 30 daqiqa kechikish, 25 daqiqasi hisobga olinadi."""
    att_mod.record_event(db, employee, EventType.IN, at(9, 30))
    record = att_mod.get_attendance(db, employee.id, DAY)
    assert record.late_minutes == 30
    assert record.billable_late_minutes == 25


def test_full_day_metrics(db, employee):
    att_mod.record_event(db, employee, EventType.IN, at(9, 0))
    att_mod.record_event(db, employee, EventType.LUNCH_OUT, at(13, 0))
    att_mod.record_event(db, employee, EventType.LUNCH_IN, at(14, 0))
    att_mod.record_event(db, employee, EventType.OUT, at(18, 0))

    record = att_mod.get_attendance(db, employee.id, DAY)
    assert record.status == DayStatus.PRESENT
    assert record.late_minutes == 0
    assert record.early_leave_minutes == 0
    assert record.lunch_overrun_minutes == 0
    assert record.worked_minutes == 8 * 60  # 9 soat − 1 soat tushlik


def test_lunch_overrun_counted(db, employee):
    """Tushlik 60 daqiqa, xodim 95 daqiqa yurdi -> 35 daqiqa oshiq."""
    att_mod.record_event(db, employee, EventType.IN, at(9, 0))
    att_mod.record_event(db, employee, EventType.LUNCH_OUT, at(13, 0))
    att_mod.record_event(db, employee, EventType.LUNCH_IN, at(14, 35))
    att_mod.record_event(db, employee, EventType.OUT, at(18, 0))

    record = att_mod.get_attendance(db, employee.id, DAY)
    assert record.lunch_overrun_minutes == 35
    assert record.worked_minutes == 9 * 60 - 95


def test_unrecorded_lunch_still_deducted(db, employee):
    """Tushlikni qayd etmaslik foyda bermasligi kerak — norma ayiriladi."""
    att_mod.record_event(db, employee, EventType.IN, at(9, 0))
    att_mod.record_event(db, employee, EventType.OUT, at(18, 0))
    record = att_mod.get_attendance(db, employee.id, DAY)
    assert record.worked_minutes == 8 * 60
    assert record.lunch_overrun_minutes == 0


def test_early_leave_counted(db, employee):
    att_mod.record_event(db, employee, EventType.IN, at(9, 0))
    att_mod.record_event(db, employee, EventType.OUT, at(17, 0))
    record = att_mod.get_attendance(db, employee.id, DAY)
    assert record.early_leave_minutes == 60


def test_missing_checkout_is_incomplete(db, employee):
    att_mod.record_event(db, employee, EventType.IN, at(9, 0))
    record = att_mod.get_attendance(db, employee.id, DAY)
    assert record.status == DayStatus.INCOMPLETE
    assert record.worked_minutes == 0


def test_late_status_when_beyond_grace(db, employee):
    att_mod.record_event(db, employee, EventType.IN, at(9, 20))
    att_mod.record_event(db, employee, EventType.OUT, at(18, 0))
    record = att_mod.get_attendance(db, employee.id, DAY)
    assert record.status == DayStatus.LATE


def test_holiday_status(db, employee):
    db.add(Holiday(day=DAY, name="Sinov bayrami"))
    db.flush()
    att_mod.recompute_day(db, employee, DAY)
    record = att_mod.get_attendance(db, employee.id, DAY)
    assert record.status == DayStatus.HOLIDAY


def test_weekend_status(db, employee):
    saturday = date(2026, 7, 18)
    att_mod.recompute_day(db, employee, saturday)
    record = att_mod.get_attendance(db, employee.id, saturday)
    assert record.status == DayStatus.HOLIDAY


def test_leave_status(db, employee):
    db.add(
        Leave(
            employee_id=employee.id,
            start_date=DAY,
            end_date=DAY,
            kind=LeaveKind.VACATION,
            is_paid=True,
        )
    )
    db.flush()
    att_mod.recompute_day(db, employee, DAY)
    record = att_mod.get_attendance(db, employee.id, DAY)
    assert record.status == DayStatus.LEAVE


def test_earliest_in_and_latest_out_win(db, employee):
    """Bir necha skan bo'lsa: kelish — eng birinchisi, ketish — eng oxirgisi."""
    att_mod.record_event(db, employee, EventType.IN, at(9, 10))
    att_mod.record_event(db, employee, EventType.IN, at(9, 40))
    att_mod.record_event(db, employee, EventType.OUT, at(17, 0))
    att_mod.record_event(db, employee, EventType.OUT, at(18, 30))
    record = att_mod.get_attendance(db, employee.id, DAY)
    assert record.check_in_at == at(9, 10)
    assert record.check_out_at == at(18, 30)


def test_manual_event_marks_source(db, employee):
    att_mod.record_event(
        db, employee, EventType.IN, at(9, 0), source=EventSource.MANUAL, note="telefoni yo'q"
    )
    record = att_mod.get_attendance(db, employee.id, DAY)
    assert record.source == EventSource.MANUAL


def test_purge_old_tokens(db, employee, location):
    from datetime import timedelta

    from app.models import UsedToken
    from app.timeutil import now_local

    db.add(
        UsedToken(
            nonce="eskitoken",
            location_id=location.id,
            issued_at_epoch=0,
            used_at=now_local() - timedelta(days=5),
        )
    )
    db.add(
        UsedToken(
            nonce="yangitoken",
            location_id=location.id,
            issued_at_epoch=0,
            used_at=now_local(),
        )
    )
    db.flush()
    assert att_mod.purge_old_tokens(db, older_than_hours=48) == 1
    assert db.get(UsedToken, "yangitoken") is not None
