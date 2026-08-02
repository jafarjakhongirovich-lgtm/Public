"""Brauzerdan botni ulash: `.env` yozuvchisi va `/admin/setup` sahifasi.

Bu yo'l `.env` ni qo'lda tahrirlashni almashtirish uchun bor, shuning uchun
asosiy talab — u boshqa sozlamalarni buzmasligi va username'ni odamdan
so'ramasligi (aynan o'sha maydon eng ko'p xato qilingan joy edi).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import bot as bot_mod
from app.envfile import EnvWriteError, read_env, update_env
from app.main import app
from tests.conftest import ADMIN_AUTH


@pytest.fixture()
def client(db):
    from app.db import get_db

    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# .env yozuvchisi
# --------------------------------------------------------------------------- #


def test_update_env_keeps_other_lines_and_comments(tmp_path):
    """Eng muhim talab: bir kalitni yozganda qolgan sozlamalar yo'qolmasin."""
    env = tmp_path / ".env"
    env.write_text(
        "# Sozlamalar\n"
        "SECRET_KEY=juda-uzun-kalit\n"
        "DATABASE_URL=postgresql://u:p@host/db\n"
        "\n"
        "# Telegram\n"
        "BOT_TOKEN=\n"
        "BOT_USERNAME=\n",
        encoding="utf-8",
    )

    update_env(env, {"BOT_TOKEN": "111:AAA", "BOT_USERNAME": "TabelBot"})

    text = env.read_text(encoding="utf-8")
    assert "# Sozlamalar" in text
    assert "# Telegram" in text
    values = read_env(env)
    assert values["SECRET_KEY"] == "juda-uzun-kalit"
    assert values["DATABASE_URL"] == "postgresql://u:p@host/db"
    assert values["BOT_TOKEN"] == "111:AAA"
    assert values["BOT_USERNAME"] == "TabelBot"


def test_update_env_appends_missing_keys(tmp_path):
    env = tmp_path / ".env"
    env.write_text("SECRET_KEY=abc\n", encoding="utf-8")

    update_env(env, {"BOT_USERNAME": "TabelBot"})

    assert read_env(env) == {"SECRET_KEY": "abc", "BOT_USERNAME": "TabelBot"}


def test_update_env_creates_the_file(tmp_path):
    env = tmp_path / "sub" / ".env"
    update_env(env, {"BOT_USERNAME": "TabelBot"})
    assert read_env(env)["BOT_USERNAME"] == "TabelBot"


def test_update_env_rejects_newline_in_value(tmp_path):
    """Qiymat ichidagi yangi qator faylni buzardi va keyingi kalitni yutardi."""
    env = tmp_path / ".env"
    env.write_text("SECRET_KEY=abc\n", encoding="utf-8")

    with pytest.raises(EnvWriteError):
        update_env(env, {"BOT_TOKEN": "111:AAA\nADMIN_PASSWORD=hacked"})

    assert read_env(env) == {"SECRET_KEY": "abc"}


def test_update_env_leaves_no_temporary_files(tmp_path):
    env = tmp_path / ".env"
    update_env(env, {"BOT_USERNAME": "TabelBot"})
    assert [item.name for item in tmp_path.iterdir()] == [".env"]


# --------------------------------------------------------------------------- #
# /admin/setup
# --------------------------------------------------------------------------- #


def test_setup_page_requires_auth(client):
    assert client.get("/admin/setup").status_code == 401
    assert client.post("/admin/setup", data={"bot_token": "x"}).status_code == 401


def test_setup_page_renders(client):
    page = client.get("/admin/setup", auth=ADMIN_AUTH)
    assert page.status_code == 200
    assert "BOT_TOKEN" in page.text
    # Username maydoni ATAYLAB yo'q: uni Telegram'ning o'zidan olamiz
    assert 'name="bot_username"' not in page.text


def test_setup_saves_token_and_derives_username(client, tmp_path, monkeypatch):
    from app.config import settings as app_settings

    env = tmp_path / ".env"
    env.write_text("SECRET_KEY=abc\n", encoding="utf-8")
    monkeypatch.setattr("app.main.ENV_FILE", env)
    # Saqlash ishlab turgan sozlamalarni ham o'zgartiradi (bu ataylab shunday),
    # shuning uchun ularni monkeypatch orqali qaytariladigan qilamiz.
    monkeypatch.setattr(app_settings, "bot_token", "")
    monkeypatch.setattr(app_settings, "bot_username", "")

    async def fake_identify(token):
        assert token == "8123456789:AAHrealtoken"
        return {"username": "DavomatTizimiBot", "name": "Davomat", "id": 8123456789}

    monkeypatch.setattr(bot_mod, "identify", fake_identify)

    response = client.post(
        "/admin/setup",
        auth=ADMIN_AUTH,
        data={"bot_token": "  8123456789:AAHrealtoken  "},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "saved=DavomatTizimiBot" in response.headers["location"]

    values = read_env(env)
    assert values["BOT_TOKEN"] == "8123456789:AAHrealtoken"
    assert values["BOT_USERNAME"] == "DavomatTizimiBot"
    assert values["SECRET_KEY"] == "abc"


def test_setup_applies_without_restart(client, tmp_path, monkeypatch, kiosk):
    """Saqlagandan keyin QR darhol ishlashi kerak — aks holda odam «saqlandi»
    yozuvini ko'radi-yu, ekranda hech narsa o'zgarmaydi."""
    from app.config import settings as app_settings

    monkeypatch.setattr("app.main.ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(app_settings, "bot_username", "")
    monkeypatch.setattr(app_settings, "bot_token", "")

    async def fake_identify(token):
        return {"username": "DavomatTizimiBot", "name": "Davomat", "id": 1}

    monkeypatch.setattr(bot_mod, "identify", fake_identify)

    assert client.get(f"/kiosk/{kiosk.api_key}/qr.svg").status_code == 503

    client.post(
        "/admin/setup", auth=ADMIN_AUTH, data={"bot_token": "1:AA"}, follow_redirects=False
    )

    assert app_settings.bot_username == "DavomatTizimiBot"
    assert client.get(f"/kiosk/{kiosk.api_key}/qr.svg").status_code == 200


def test_setup_reports_a_rejected_token_without_writing(client, tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("BOT_TOKEN=\n", encoding="utf-8")
    monkeypatch.setattr("app.main.ENV_FILE", env)

    async def fake_identify(token):
        raise bot_mod.BotTokenError("Telegram bu tokenni qabul qilmadi.")

    monkeypatch.setattr(bot_mod, "identify", fake_identify)

    response = client.post(
        "/admin/setup", auth=ADMIN_AUTH, data={"bot_token": "1:xato"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]
    # Xato token saqlanmaydi — aks holda ishlayotgan sozlama buzilardi
    assert read_env(env)["BOT_TOKEN"] == ""


def test_setup_rejects_an_empty_token(client, monkeypatch):
    async def explode(token):
        raise AssertionError("bo'sh token uchun Telegram'ga murojaat qilinmasin")

    monkeypatch.setattr(bot_mod, "identify", explode)

    response = client.post(
        "/admin/setup", auth=ADMIN_AUTH, data={"bot_token": "   "}, follow_redirects=False
    )
    assert response.status_code == 303
    assert "error=" in response.headers["location"]


@pytest.mark.parametrize("token", ["salom", "", "AAH-token-siz-raqam", ":AAH"])
def test_identify_rejects_malformed_tokens_offline(token):
    """Shakli noto'g'ri token uchun tarmoqqa umuman chiqmaymiz."""
    import asyncio

    with pytest.raises(bot_mod.BotTokenError):
        asyncio.run(bot_mod.identify(token))
