"""QR token: imzo, muddat, format testlari."""

from __future__ import annotations

import base64
import re
import time as _time

import pytest

from app import security


def test_roundtrip_returns_same_location():
    token = security.issue_token(7)
    payload = security.verify_token(token)
    assert payload.location_id == 7


def test_token_fits_telegram_start_param():
    """Telegram `start` parametri 64 belgidan oshmasligi va faqat
    A-Za-z0-9_- belgilardan iborat bo'lishi kerak."""
    for location_id in (0, 1, 42, 255):
        token = security.issue_token(location_id)
        assert len(token) <= 64, f"token juda uzun: {len(token)}"
        assert re.fullmatch(r"[A-Za-z0-9_-]+", token), f"noto'g'ri belgi: {token}"


def test_each_token_is_unique():
    """Bir sekundda yasalgan tokenlar ham har xil bo'lishi kerak (nonce)."""
    tokens = {security.issue_token(1) for _ in range(200)}
    assert len(tokens) == 200


def _remint(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(token: str) -> bytearray:
    return bytearray(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))


@pytest.mark.parametrize("index", range(9, 17))
def test_tampered_signature_rejected(index):
    """Imzoning har bir baytini o'zgartirib ko'ramiz — hammasi rad etilishi kerak.

    DIQQAT: bu yerda base64 satrining oxirgi belgisini o'zgartirish YETARLI EMAS.
    17 bayt 23 belgiga sig'adi va oxirgi belgining 2 biti to'ldirish (padding)
    biti — ularni o'zgartirsa dekodlangan baytlar o'zgarmaydi. Shuning uchun
    baytlar darajasida buzamiz.
    """
    raw = _decode(security.issue_token(3))
    raw[index] ^= 0xFF
    with pytest.raises(security.BadSignature):
        security.verify_token(_remint(bytes(raw)))


@pytest.mark.parametrize("index", range(0, 9))
def test_tampered_payload_rejected(index):
    """Yuklamaning (location_id, issued_at, nonce) har bir bayti himoyalangan."""
    raw = _decode(security.issue_token(3))
    raw[index] ^= 0xFF
    with pytest.raises(security.TokenError):
        security.verify_token(_remint(bytes(raw)))


def test_tampered_location_rejected():
    """Lokatsiya baytini o'zgartirib boshqa ofis nomidan kirib bo'lmaydi."""
    raw = _decode(security.issue_token(1))
    raw[0] = 2  # location_id -> 2
    with pytest.raises(security.BadSignature):
        security.verify_token(_remint(bytes(raw)))


def test_truncated_token_rejected():
    raw = _decode(security.issue_token(1))
    with pytest.raises(security.MalformedToken):
        security.verify_token(_remint(bytes(raw[:-1])))


def test_padded_token_rejected():
    raw = _decode(security.issue_token(1))
    with pytest.raises(security.MalformedToken):
        security.verify_token(_remint(bytes(raw) + b"\x00"))


def test_foreign_secret_rejected(monkeypatch):
    """Boshqa kalit bilan imzolangan token qabul qilinmaydi."""
    token = security.issue_token(1)
    monkeypatch.setattr(security.settings, "secret_key", "butunlay-boshqa-kalit")
    with pytest.raises(security.BadSignature):
        security.verify_token(token)


def test_expired_token_rejected():
    now = int(_time.time())
    token = security.issue_token(1, issued_at_epoch=now - 60)
    with pytest.raises(security.ExpiredToken):
        security.verify_token(token, at_epoch=now, ttl_seconds=25)


def test_token_valid_right_up_to_ttl():
    now = int(_time.time())
    token = security.issue_token(1, issued_at_epoch=now - 25)
    assert security.verify_token(token, at_epoch=now, ttl_seconds=25).location_id == 1


def test_token_from_future_rejected():
    """Soati o'zgartirilgan qurilma yasagan token o'tmaydi."""
    now = int(_time.time())
    token = security.issue_token(1, issued_at_epoch=now + 3600)
    with pytest.raises(security.MalformedToken):
        security.verify_token(token, at_epoch=now)


def test_small_clock_skew_tolerated():
    now = int(_time.time())
    token = security.issue_token(1, issued_at_epoch=now + 3)
    assert security.verify_token(token, at_epoch=now).location_id == 1


@pytest.mark.parametrize("value", ["", "   ", "salom", "!!!!!!", "A" * 100])
def test_garbage_rejected(value):
    with pytest.raises(security.TokenError):
        security.verify_token(value)


def test_replay_key_is_stable_and_unique():
    token_a = security.issue_token(1)
    token_b = security.issue_token(1)
    key_a = security.verify_token(token_a).replay_key
    assert key_a == security.verify_token(token_a).replay_key
    assert key_a != security.verify_token(token_b).replay_key


def test_location_id_range_enforced():
    """Token formatida location_id 1 bayt — chegara tekshirilishi kerak."""
    with pytest.raises(ValueError):
        security.issue_token(256)
    with pytest.raises(ValueError):
        security.issue_token(-1)


def test_deep_link_shape():
    token = security.issue_token(1)
    assert security.deep_link(token) == f"https://t.me/TestTabelBot?start={token}"
