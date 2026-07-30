"""Test uchun izolyatsiyalangan baza va fixture'lar.

DIQQAT: `app.config` import qilinishidan OLDIN muhit o'zgaruvchilari
o'rnatilishi kerak — sozlamalar import paytida o'qiladi.
"""

from __future__ import annotations

import os
import tempfile
from datetime import date, time
from pathlib import Path

import pytest

_TMP_DIR = tempfile.mkdtemp(prefix="tabel-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP_DIR) / 'test.db'}"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["TIMEZONE"] = "Asia/Tashkent"
os.environ["QR_TTL_SECONDS"] = "25"
os.environ["BOT_USERNAME"] = "TestTabelBot"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "test-admin-parol"

from app.db import SessionLocal, engine  # noqa: E402
from app.models import Base, Employee, Kiosk, Location, Schedule  # noqa: E402
from app.security import new_api_key  # noqa: E402

ADMIN_AUTH = ("admin", "test-admin-parol")


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture()
def schedule(db) -> Schedule:
    """09:00–18:00, tushlik 13:00–14:00 (60 daq), grace 5 daq, Du–Ju."""
    item = Schedule(
        name="Asosiy",
        start_time=time(9, 0),
        end_time=time(18, 0),
        lunch_start=time(13, 0),
        lunch_end=time(14, 0),
        lunch_minutes=60,
        work_days="1,2,3,4,5",
        grace_minutes=5,
    )
    db.add(item)
    db.flush()
    return item


@pytest.fixture()
def location(db) -> Location:
    item = Location(name="Bosh ofis")
    db.add(item)
    db.flush()
    return item


@pytest.fixture()
def kiosk(db, location) -> Kiosk:
    item = Kiosk(name="Kirish eshigi", location_id=location.id, api_key=new_api_key())
    db.add(item)
    db.flush()
    return item


@pytest.fixture()
def employee(db, schedule, location) -> Employee:
    item = Employee(
        full_name="Aliyev Aziz",
        position="Menejer",
        telegram_user_id=555001,
        monthly_salary=10_000_000,
        schedule_id=schedule.id,
        location_id=location.id,
        hired_at=date(2020, 1, 1),
    )
    db.add(item)
    db.flush()
    return item
