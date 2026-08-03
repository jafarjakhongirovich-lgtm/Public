"""Web qatlami: kiosk sahifasi, QR endpoint, admin panel va to'liq zanjir.

Bu yerdagi asosiy test — `test_qr_from_endpoint_is_accepted_by_scan`: kiosk
endpoint bergan **haqiqiy** token davomat tizimidan o'tishini tekshiradi.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app import attendance as att_mod
from app import security
from app.main import app
from app.models import EventType
from tests.conftest import ADMIN_AUTH


@pytest.fixture()
def client(db):
    """Ilova test sessiyasining o'zidan foydalanadi.

    Aks holda endpoint'lar boshqa ulanish ochib, fixture'lar hali commit
    qilinmagan ma'lumotni ko'rmay qolardi (va SQLite qulflanib qolardi).
    """
    from app.db import get_db

    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Kiosk
# --------------------------------------------------------------------------- #


def test_kiosk_page_renders(client, kiosk):
    response = client.get(f"/kiosk/{kiosk.api_key}")
    assert response.status_code == 200
    assert "Bosh ofis" in response.text
    assert f"/kiosk/{kiosk.api_key}/qr.svg" in response.text


def test_kiosk_requires_valid_key(client, kiosk):
    assert client.get("/kiosk/butunlay-yolgon-kalit").status_code == 404


def test_inactive_kiosk_is_hidden(client, db, kiosk):
    kiosk.is_active = False
    db.flush()
    assert client.get(f"/kiosk/{kiosk.api_key}").status_code == 404


def test_qr_endpoint_returns_uncached_svg(client, kiosk):
    response = client.get(f"/kiosk/{kiosk.api_key}/qr.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    # Kesh QR ni "muzlatib" qo'ysa, muddati o'tgan token ekranda qolib ketardi.
    assert "no-store" in response.headers["cache-control"]
    assert response.content.lstrip().startswith(b"<?xml") or b"<svg" in response.content


def test_each_qr_request_is_a_new_code(client, kiosk):
    first = client.get(f"/kiosk/{kiosk.api_key}/qr.svg").content
    second = client.get(f"/kiosk/{kiosk.api_key}/qr.svg").content
    assert first != second


def test_qr_requires_valid_key(client):
    assert client.get("/kiosk/yolgon/qr.svg").status_code == 404


def test_ip_allowlist_blocks_foreign_network(client, db, kiosk, location):
    location.ip_allowlist = "10.99.0.0/24"
    db.flush()
    # TestClient standart holatda "testclient" hostidan keladi -> ro'yxatga tushmaydi
    assert client.get(f"/kiosk/{kiosk.api_key}").status_code == 403
    # Ofis tarmog'idagi IP o'tadi
    allowed = client.get(
        f"/kiosk/{kiosk.api_key}", headers={"X-Forwarded-For": "10.99.0.7"}
    )
    assert allowed.status_code == 200


def test_ip_allowlist_empty_means_no_restriction(client, db, kiosk, location):
    location.ip_allowlist = ""
    db.flush()
    assert client.get(f"/kiosk/{kiosk.api_key}").status_code == 200


# --------------------------------------------------------------------------- #
# To'liq zanjir: kiosk endpoint -> token -> davomat
# --------------------------------------------------------------------------- #


def _capture_token(monkeypatch) -> list[str]:
    """`issue_token` chaqiruvlarini ushlab qoladi (QR ichidagi tokenni bilish uchun)."""
    captured: list[str] = []
    original = security.issue_token

    def spy(location_id, **kwargs):
        token = original(location_id, **kwargs)
        captured.append(token)
        return token

    monkeypatch.setattr(security, "issue_token", spy)
    # main.py `security` modulini import qilgani uchun bitta patch yetarli,
    # lekin aniqlik uchun ikkalasini ham tekshiramiz.
    monkeypatch.setattr("app.main.security.issue_token", spy, raising=False)
    return captured


def test_qr_from_endpoint_is_accepted_by_scan(client, db, kiosk, employee, monkeypatch):
    """Kiosk bergan haqiqiy QR bilan xodim davomatga tushadi."""
    captured = _capture_token(monkeypatch)
    assert client.get(f"/kiosk/{kiosk.api_key}/qr.svg").status_code == 200
    assert len(captured) == 1

    result = att_mod.scan(db, employee.telegram_user_id, captured[0])
    assert result.event_type == EventType.IN
    assert result.attendance.check_in_at is not None


def test_qr_from_endpoint_cannot_be_reused(client, db, kiosk, employee, monkeypatch):
    captured = _capture_token(monkeypatch)
    client.get(f"/kiosk/{kiosk.api_key}/qr.svg")
    token = captured[0]

    att_mod.scan(db, employee.telegram_user_id, token)
    with pytest.raises(att_mod.TokenAlreadyUsed):
        att_mod.scan(db, employee.telegram_user_id, token)


def test_qr_encodes_the_telegram_deep_link(client, kiosk, monkeypatch):
    """QR ichida aynan `https://t.me/<bot>?start=<token>` bo'lishi kerak.

    SVG ni dekodlash o'rniga: xuddi shu havolani mustaqil ravishda QR ga
    aylantiramiz va natija endpoint bergani bilan bayt-baytga mos kelishini
    tekshiramiz. Bu QR aynan shu ma'lumotni tashiyotganini isbotlaydi.
    """
    import io

    import qrcode
    from qrcode.image.svg import SvgPathImage

    captured = _capture_token(monkeypatch)
    response = client.get(f"/kiosk/{kiosk.api_key}/qr.svg")
    token = captured[0]

    expected_link = f"https://t.me/TestTabelBot?start={token}"
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=2,
        image_factory=SvgPathImage,
    )
    qr.add_data(expected_link)
    qr.make(fit=True)
    buffer = io.BytesIO()
    qr.make_image().save(buffer)

    assert response.content == buffer.getvalue()


# --------------------------------------------------------------------------- #
# Admin panel
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "path",
    ["/admin", "/admin/employees", "/admin/settings", "/admin/payroll", "/admin/payroll.xlsx"],
)
def test_admin_requires_auth(client, path):
    assert client.get(path).status_code == 401


def test_admin_rejects_wrong_password(client):
    assert client.get("/admin", auth=("admin", "xato")).status_code == 401


def test_admin_day_lists_employees(client, employee):
    response = client.get("/admin", auth=ADMIN_AUTH)
    assert response.status_code == 200
    assert "Aliyev Aziz" in response.text


def test_admin_manual_event_creates_attendance(client, db, employee):
    response = client.post(
        "/admin/manual",
        auth=ADMIN_AUTH,
        data={
            "employee_id": employee.id,
            "event_type": "IN",
            "happened_at": "2026-07-15T09:25",
            "note": "telefoni yo'q edi",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db.expire_all()
    from datetime import date

    record = att_mod.get_attendance(db, employee.id, date(2026, 7, 15))
    assert record is not None
    assert record.late_minutes == 25
    assert record.billable_late_minutes == 20


def test_admin_manual_event_rejects_bad_time(client, employee):
    response = client.post(
        "/admin/manual",
        auth=ADMIN_AUTH,
        data={"employee_id": employee.id, "event_type": "IN", "happened_at": "salom"},
    )
    assert response.status_code == 400


def test_admin_creates_employee(client, db, schedule):
    response = client.post(
        "/admin/employees",
        auth=ADMIN_AUTH,
        data={
            "employee_id": "",
            "full_name": "Yangi Xodim",
            "position": "Sotuvchi",
            "telegram_user_id": "777001",
            "telegram_username": "@yangi",
            "monthly_salary": "6000000",
            "schedule_id": schedule.id,
            "location_id": "",
            "hired_at": "",
            "is_active": "on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db.expire_all()
    created = att_mod.employee_by_telegram(db, 777001)
    assert created is not None
    assert created.full_name == "Yangi Xodim"
    assert created.telegram_username == "yangi"  # @ tozalanadi


def test_admin_kiosk_key_rotation_invalidates_old_link(client, db, kiosk):
    old_key = kiosk.api_key
    response = client.post(
        f"/admin/kiosks/{kiosk.id}/rotate", auth=ADMIN_AUTH, follow_redirects=False
    )
    assert response.status_code == 303

    db.expire_all()
    assert client.get(f"/kiosk/{old_key}").status_code == 404
    refreshed = db.get(type(kiosk), kiosk.id)
    assert client.get(f"/kiosk/{refreshed.api_key}").status_code == 200


def test_admin_rejects_leave_with_reversed_dates(client, employee):
    response = client.post(
        "/admin/leaves",
        auth=ADMIN_AUTH,
        data={
            "employee_id": employee.id,
            "start_date": "2026-07-20",
            "end_date": "2026-07-10",
            "kind": "VACATION",
            "is_paid": "on",
        },
    )
    assert response.status_code == 400


def test_payroll_page_and_export(client, employee):
    page = client.get("/admin/payroll?period=2026-07", auth=ADMIN_AUTH)
    assert page.status_code == 200
    assert "Aliyev Aziz" in page.text

    xlsx = client.get("/admin/payroll.xlsx?period=2026-07", auth=ADMIN_AUTH)
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK"
    assert "oylik-2026-07.xlsx" in xlsx.headers["content-disposition"]

    tabel = client.get("/admin/tabel.xlsx?period=2026-07", auth=ADMIN_AUTH)
    assert tabel.status_code == 200
    assert tabel.content[:2] == b"PK"


def test_payroll_save_persists_items(client, db, employee):
    response = client.post(
        "/admin/payroll/save",
        auth=ADMIN_AUTH,
        data={"period": "2026-07"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    from sqlalchemy import select

    from app.models import PayrollItem

    db.expire_all()
    items = db.scalars(select(PayrollItem).where(PayrollItem.period == "2026-07")).all()
    assert len(items) == 1


def test_audit_log_records_manual_changes(client, db, employee):
    client.post(
        "/admin/manual",
        auth=ADMIN_AUTH,
        data={
            "employee_id": employee.id,
            "event_type": "IN",
            "happened_at": "2026-07-15T09:00",
            "note": "",
        },
    )
    from sqlalchemy import select

    from app.models import AuditLog

    db.expire_all()
    entries = db.scalars(select(AuditLog)).all()
    assert any(e.action == "manual_event" and e.actor == "admin" for e in entries)


def test_healthz_is_public(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_root_redirects_to_admin(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/admin"


def test_token_charset_is_url_safe_in_deep_link(client, kiosk, monkeypatch):
    """QR havolasi hech qanday qochirish (escaping) talab qilmasligi kerak."""
    captured = _capture_token(monkeypatch)
    client.get(f"/kiosk/{kiosk.api_key}/qr.svg")
    link = security.deep_link(captured[0])
    assert re.fullmatch(r"https://t\.me/[A-Za-z0-9_]+\?start=[A-Za-z0-9_-]+", link)


# --------------------------------------------------------------------------- #
# BOT_USERNAME xato bo'lganda kiosk
# --------------------------------------------------------------------------- #


def test_kiosk_refuses_to_draw_qr_with_broken_username(client, kiosk, monkeypatch):
    """Probelli username'dan yasalgan havola telefonda ochilmaydi. Bunday QR
    chizish — jimgina buziladigan xatolik, shuning uchun 503 qaytaramiz."""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "bot_username", "Davomat tizimi")
    assert client.get(f"/kiosk/{kiosk.api_key}/qr.svg").status_code == 503


def test_kiosk_page_explains_broken_username(client, kiosk, monkeypatch):
    """Ekranda aniq sabab yozilishi kerak, shunda xatoni topish oson bo'ladi."""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "bot_username", "Davomat tizimi")
    page = client.get(f"/kiosk/{kiosk.api_key}")
    assert page.status_code == 200
    assert 'class="warn"' in page.text
    # Xato qiymatning o'zi ko'rsatiladi — nimani tuzatish kerakligi ravshan bo'lsin
    assert "Davomat tizimi" in page.text
    # QR elementi umuman chizilmaydi
    assert '<img id="qr"' not in page.text


def test_kiosk_page_explains_missing_username(client, kiosk, monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "bot_username", "")
    page = client.get(f"/kiosk/{kiosk.api_key}")
    assert 'class="warn"' in page.text
    assert '<img id="qr"' not in page.text
    # Ekran nima qilish kerakligini aytadi, sababni ta'riflab qo'ymaydi
    assert "/admin/setup" in page.text


def test_kiosk_names_the_env_file_it_read(client, kiosk, monkeypatch):
    """Papka nusxalanganda odam bir `.env` ni tahrirlaydi, server esa boshqasini
    o'qiydi. Yo'lni ekranga chiqarmasa, buni topish deyarli imkonsiz."""
    from app.config import ENV_FILE
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "bot_username", "")
    page = client.get(f"/kiosk/{kiosk.api_key}")
    assert str(ENV_FILE) in page.text


def test_kiosk_draws_qr_when_username_is_valid(client, kiosk, monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "bot_username", "DavomatTizimiBot")
    page = client.get(f"/kiosk/{kiosk.api_key}")
    assert '<img id="qr"' in page.text
    assert 'class="warn"' not in page.text
    assert client.get(f"/kiosk/{kiosk.api_key}/qr.svg").status_code == 200


def test_kiosk_shows_bot_address(client, kiosk, monkeypatch):
    """Ekranda bot manzili yozilib tursin — QR ichida nima borligini tekshirishning
    eng oson yo'li shu, kodni skanerlab ko'rish shart emas."""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "bot_username", "@DavomatTizimiBot")
    page = client.get(f"/kiosk/{kiosk.api_key}")
    assert "t.me/DavomatTizimiBot" in page.text
    # Token ko'rsatilmaydi: har 15 sekundda o'zgaradi va foyda bermaydi
    assert "?start=" not in page.text


# --------------------------------------------------------------------------- #
# Xodim formasi: "ID" va Telegram raqamini chalkashtirish
# --------------------------------------------------------------------------- #


def test_employee_form_rejects_unknown_id(client, schedule):
    """«ID» maydoniga Telegram raqami yozilsa, jimgina yangi xodim yaratilmasin.

    Ikkala maydon ham son qabul qiladi, shuning uchun ularni almashtirib
    yuborish oson. Ilgari bunday holatda xodim yaratilar, kiritilgan raqam
    yo'qolar va Telegram ulanmagan qolar edi — natijada QR skanerlanganda
    "siz tizimda yo'qsiz" chiqardi, sababi esa ko'rinmasdi.
    """
    response = client.post(
        "/admin/employees",
        auth=ADMIN_AUTH,
        data={
            "employee_id": "2003632983",
            "full_name": "Yangi Xodim",
            "schedule_id": schedule.id,
        },
    )
    assert response.status_code == 404
    assert "Telegram user_id" in response.json()["detail"]


def test_employee_form_creates_when_id_is_blank(client, schedule):
    response = client.post(
        "/admin/employees",
        auth=ADMIN_AUTH,
        data={
            "employee_id": "",
            "full_name": "Yangi Xodim",
            "telegram_user_id": "2003632983",
            "schedule_id": schedule.id,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    page = client.get("/admin/employees", auth=ADMIN_AUTH)
    assert "Yangi Xodim" in page.text


def test_employee_form_still_edits_an_existing_record(client, employee, schedule):
    response = client.post(
        "/admin/employees",
        auth=ADMIN_AUTH,
        data={
            "employee_id": str(employee.id),
            "full_name": "Aliyev Aziz (tuzatildi)",
            "schedule_id": schedule.id,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert employee.full_name == "Aliyev Aziz (tuzatildi)"
