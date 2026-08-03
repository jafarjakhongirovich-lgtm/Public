"""Telegram webhook va deploy tekshiruvlari.

Webhook — tizimning internetdan ochiq yagona nuqtasi, shuning uchun uni
himoyalaydigan har bir shart alohida tekshiriladi.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.main import app

SECRET = "webhook-secret-for-tests-0123456789"

UPDATE = {
    "update_id": 1,
    "message": {
        "message_id": 1,
        "date": 1767225600,
        "chat": {"id": 555001, "type": "private"},
        "from": {"id": 555001, "is_bot": False, "first_name": "Aziz"},
        "text": "/holat",
    },
}


@pytest.fixture()
def client(db, monkeypatch):
    from app.db import get_db

    monkeypatch.setattr(settings, "webhook_secret", SECRET)
    monkeypatch.setattr(settings, "bot_token", "123456:FAKE-TOKEN-FOR-TESTS")
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Kirish himoyasi
# --------------------------------------------------------------------------- #


def test_wrong_path_secret_is_rejected(client):
    response = client.post(
        "/telegram/butunlay-boshqa-secret",
        json=UPDATE,
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )
    assert response.status_code == 404


def test_missing_header_is_rejected(client):
    """Maxfiy yo'lni bilgan, lekin sarlavhasi yo'q so'rov o'tmasligi kerak."""
    response = client.post(f"/telegram/{SECRET}", json=UPDATE)
    assert response.status_code == 404


def test_wrong_header_is_rejected(client):
    response = client.post(
        f"/telegram/{SECRET}",
        json=UPDATE,
        headers={"X-Telegram-Bot-Api-Secret-Token": "yolg'on"},
    )
    assert response.status_code == 404


def test_rejection_does_not_reveal_the_reason(client):
    """Yo'l xatomi yoki sarlavhami — javob bir xil bo'lishi kerak, aks holda
    tanlab-tanlab topib olish mumkin bo'lardi."""
    bad_path = client.post(
        "/telegram/xato", json=UPDATE, headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}
    )
    bad_header = client.post(
        f"/telegram/{SECRET}", json=UPDATE, headers={"X-Telegram-Bot-Api-Secret-Token": "xato"}
    )
    assert bad_path.status_code == bad_header.status_code == 404


def test_webhook_disabled_when_secret_not_set(client, monkeypatch):
    monkeypatch.setattr(settings, "webhook_secret", "")
    response = client.post(
        "/telegram/", json=UPDATE, headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}
    )
    assert response.status_code == 404


def test_missing_bot_token_returns_404_not_500(client, monkeypatch):
    """BOT_TOKEN yo'q bo'lsa 500 EMAS, 404 qaytishi kerak.

    Telegram 500 olgan yangilanishni to'xtovsiz qayta yuboradi, ya'ni bitta
    sozlanmagan deploy butun navbatni tiqib qo'yadi.
    """
    monkeypatch.setattr(settings, "bot_token", "")
    response = client.post(
        f"/telegram/{SECRET}",
        json=UPDATE,
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )
    assert response.status_code == 404


def test_bot_construction_failure_returns_200(client, monkeypatch):
    """Bot yasashda xato chiqsa ham 200 qaytadi — navbat tiqilmasligi uchun."""

    def broken_build():
        raise RuntimeError("bot yasalmadi")

    monkeypatch.setattr("app.bot.build_bot", broken_build)
    response = client.post(
        f"/telegram/{SECRET}",
        json=UPDATE,
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )
    assert response.status_code == 200


def test_broken_json_is_rejected(client):
    response = client.post(
        f"/telegram/{SECRET}",
        content=b"bu json emas",
        headers={
            "X-Telegram-Bot-Api-Secret-Token": SECRET,
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 400


def test_valid_update_reaches_the_dispatcher(client, employee, monkeypatch):
    """To'g'ri so'rov bot dispetcheriga yetib borishi kerak."""
    seen: list[dict] = []

    async def fake_handle(bot, payload):
        seen.append(payload)

    monkeypatch.setattr("app.bot.handle_webhook_update", fake_handle)
    monkeypatch.setattr("app.bot.build_bot", lambda: _FakeBot())

    response = client.post(
        f"/telegram/{SECRET}",
        json=UPDATE,
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert seen == [UPDATE]


def test_handler_failure_still_returns_200(client, monkeypatch):
    """Xato javob qaytarsak, Telegram o'sha xabarni qayta-qayta yuboraveradi va
    navbat tiqilib qoladi. Shuning uchun xato logga yoziladi, javob esa 200."""

    async def boom(bot, payload):
        raise ValueError("sinov uchun xato")

    monkeypatch.setattr("app.bot.handle_webhook_update", boom)
    monkeypatch.setattr("app.bot.build_bot", lambda: _FakeBot())

    response = client.post(
        f"/telegram/{SECRET}",
        json=UPDATE,
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )
    assert response.status_code == 200


class _FakeBot:
    """Haqiqiy Bot Telegram'ga ulanadi — testda kerak emas."""

    class _Session:
        async def close(self) -> None:
            return None

    session = _Session()


# --------------------------------------------------------------------------- #
# Sozlamalar
# --------------------------------------------------------------------------- #


def _deploy_settings(**overrides) -> Settings:
    base = {
        "secret_key": "a" * 40,
        "admin_password": "juda-kuchli-parol-2026",
        "database_url": "postgresql+psycopg://u:p@host:5432/db",
        "webhook_secret": "w" * 24,
        "public_base_url": "https://tabel.example.com",
    }
    base.update(overrides)
    return Settings(**base)


def test_healthy_deployment_has_no_problems():
    assert _deploy_settings().deployment_problems() == []


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("secret_key", "dev-insecure-secret-key", "SECRET_KEY"),
        ("secret_key", "qisqa", "SECRET_KEY"),
        ("admin_password", "admin", "ADMIN_PASSWORD"),
        ("admin_password", "change-me", "ADMIN_PASSWORD"),
        ("admin_password", "qisqa1", "ADMIN_PASSWORD"),
        ("database_url", "sqlite:///./tabel.db", "SQLite"),
        ("webhook_secret", "", "WEBHOOK_SECRET"),
        ("webhook_secret", "qisqa", "WEBHOOK_SECRET"),
        ("public_base_url", "http://tabel.example.com", "https"),
    ],
)
def test_weak_settings_are_caught(field, value, fragment):
    problems = _deploy_settings(**{field: value}).deployment_problems()
    assert any(fragment in p for p in problems), problems


def test_is_public_follows_base_url():
    assert _deploy_settings().is_public is True
    assert _deploy_settings(public_base_url="").is_public is False


def test_webhook_url_is_built_from_base_and_secret():
    config = _deploy_settings(public_base_url="https://tabel.example.com/")
    assert config.webhook_path == "/telegram/" + "w" * 24
    assert config.webhook_url == "https://tabel.example.com/telegram/" + "w" * 24


def test_public_mode_refuses_to_start_with_weak_settings(monkeypatch):
    """Zaif sozlamalar bilan internetga chiqib ketmasligi kerak — panelda
    oyliklar ko'rinadi, keyin tuzataman degani ish bermaydi."""
    monkeypatch.setattr(settings, "public_base_url", "https://tabel.example.com")
    monkeypatch.setattr(settings, "admin_password", "admin")
    monkeypatch.setattr(settings, "auto_create_tables", False)

    with pytest.raises(RuntimeError, match="sozlamalar yetarli emas"), TestClient(app):
        pass


def test_local_mode_starts_with_simple_password(monkeypatch):
    """Lokal ishlashda oddiy parol muammo emas — sayt uy tarmog'idan ko'rinadi."""
    monkeypatch.setattr(settings, "public_base_url", "")
    monkeypatch.setattr(settings, "admin_password", "admin")
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200


# --------------------------------------------------------------------------- #
# PostgreSQL turlari
# --------------------------------------------------------------------------- #


def test_telegram_user_id_is_64_bit():
    """Telegram 2^31 dan katta ID beradi.

    SQLite'da tur dinamik, shuning uchun bu xato faqat PostgreSQL'da chiqadi va
    "yangi xodim qo'shilmayapti" ko'rinishida namoyon bo'ladi. Shu sababli
    ustun turini to'g'ridan-to'g'ri tekshiramiz.
    """
    from sqlalchemy.dialects import postgresql

    from app.models import Employee

    column = Employee.__table__.c.telegram_user_id
    ddl = column.type.compile(dialect=postgresql.dialect())
    assert ddl == "BIGINT", f"telegram_user_id turi {ddl}, BIGINT bo'lishi kerak"


def test_issued_at_epoch_is_64_bit():
    """Token ichidagi vaqt uint32 (2106 yilgacha), signed INTEGER 2038 da tugaydi."""
    from sqlalchemy.dialects import postgresql

    from app.models import UsedToken

    column = UsedToken.__table__.c.issued_at_epoch
    assert column.type.compile(dialect=postgresql.dialect()) == "BIGINT"


def test_large_telegram_id_round_trips(db, schedule):
    """2^31 dan katta ID saqlanib, qaytib o'qilishi kerak."""
    from app import attendance as att_mod
    from app.models import Employee

    big_id = 7_123_456_789  # haqiqiy Telegram ID'lari shu oraliqda
    assert big_id > 2**31 - 1

    db.add(
        Employee(
            full_name="Katta ID",
            telegram_user_id=big_id,
            monthly_salary=1_000_000,
            schedule_id=schedule.id,
        )
    )
    db.flush()

    found = att_mod.employee_by_telegram(db, big_id)
    assert found is not None
    assert found.telegram_user_id == big_id


def test_transaction_pooler_is_detected():
    """Supabase serverless uchun 6543-portni tavsiya qiladi — o'sha rejimda
    prepared statement'lar o'chirilishi kerak."""
    from app.db import _engine_options, _is_transaction_pooler

    pooler_urls = [
        "postgresql+psycopg://u:p@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres",
        "postgresql+psycopg://u:p@host:5432/db?pgbouncer=true",
        "postgresql+psycopg://u:p@aws-0-eu.pooler.supabase.com:5432/postgres",
    ]
    for url in pooler_urls:
        assert _is_transaction_pooler(url), url
        assert _engine_options(url)["connect_args"]["prepare_threshold"] is None


def test_direct_connection_keeps_normal_pooling():
    from app.db import _engine_options, _is_transaction_pooler

    url = "postgresql+psycopg://u:p@db.xtlegrdxgakegrfmezdj.supabase.co:5432/postgres"
    assert not _is_transaction_pooler(url)
    options = _engine_options(url)
    assert options["pool_pre_ping"] is True
    assert "connect_args" not in options


def test_sqlite_options_unchanged():
    from app.db import _engine_options

    options = _engine_options("sqlite:///./tabel.db")
    assert options["connect_args"]["check_same_thread"] is False
