"""QR token: yasash va tekshirish.

MAQSAD
------
Token xodimning **jismonan ofisda** ekanining isboti. Ofisdagi ekranda QR har
`QR_REFRESH_SECONDS` sekundda yangilanadi va har bir token `QR_TTL_SECONDS`
sekunddan keyin kuchini yo'qotadi. Shu sababli:

* QR ni bir marta rasmga olib, keyin uydan ishlatib bo'lmaydi — muddati o'tadi;
* rasmni hamkasbiga yuborsa ham, u yetib borguncha token o'ladi;
* bitta token faqat bir marta ishlaydi (`used_tokens` jadvali — replay himoyasi);
* tokenni server imzolaydi (HMAC-SHA256), shuning uchun uni o'zi yasab olib
  bo'lmaydi.

FORMAT (17 bayt -> base64url, 23 belgi)
---------------------------------------
    [1 bayt ] location_id
    [4 bayt ] issued_at — UTC epoch sekund (big-endian uint32)
    [4 bayt ] nonce — tasodifiy
    [8 bayt ] HMAC-SHA256(secret, oldingi 9 bayt) ning boshi

23 belgi Telegram `start` parametrining 64 belgilik cheklovidan ancha kichik va
faqat `A-Za-z0-9-_` belgilardan iborat — bu Telegram ruxsat bergan to'plam.
"""

from __future__ import annotations

import base64
import hmac
import os
import re
import secrets
import struct
import time as _time
from dataclasses import dataclass
from hashlib import sha256

from app.config import settings

_HEADER = struct.Struct(">BII")  # location_id, issued_at, nonce
_SIG_BYTES = 8
_TOKEN_BYTES = _HEADER.size + _SIG_BYTES  # 9 + 8 = 17

# Kiosk va telefon soatlari biroz farq qilishi mumkin — kelajakka shuncha yon beramiz.
_CLOCK_SKEW_SECONDS = 5


class TokenError(Exception):
    """QR token bilan bog'liq umumiy xatolik."""

    user_message = "QR kod yaroqsiz. Ekrandagi QR ni qaytadan skanerlang."


class MalformedToken(TokenError):
    user_message = "QR kod tanib olinmadi. Ekrandagi QR ni qaytadan skanerlang."


class BadSignature(TokenError):
    user_message = "QR kod bu tizimga tegishli emas."


class ExpiredToken(TokenError):
    user_message = "QR kodning muddati o'tgan. Ekranda yangilanganini skanerlang."


@dataclass(frozen=True)
class TokenPayload:
    location_id: int
    issued_at_epoch: int
    nonce_hex: str

    @property
    def replay_key(self) -> str:
        """`used_tokens.nonce` uchun kalit — lokatsiya + vaqt + nonce."""
        return f"{self.location_id:02x}{self.issued_at_epoch:08x}{self.nonce_hex}"

    def age_seconds(self, at_epoch: int | None = None) -> int:
        return (at_epoch if at_epoch is not None else int(_time.time())) - self.issued_at_epoch


def _sign(body: bytes) -> bytes:
    return hmac.new(settings.secret_key.encode(), body, sha256).digest()[:_SIG_BYTES]


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(token: str) -> bytes:
    padding = "=" * (-len(token) % 4)
    return base64.urlsafe_b64decode(token + padding)


def issue_token(location_id: int, *, issued_at_epoch: int | None = None) -> str:
    """Lokatsiya uchun yangi imzolangan token yasaydi."""
    if not 0 <= location_id <= 255:
        raise ValueError("location_id 0..255 oralig'ida bo'lishi kerak")
    issued = int(issued_at_epoch if issued_at_epoch is not None else _time.time())
    nonce = int.from_bytes(os.urandom(4), "big")
    body = _HEADER.pack(location_id, issued, nonce)
    return _b64encode(body + _sign(body))


def verify_token(
    token: str, *, at_epoch: int | None = None, ttl_seconds: int | None = None
) -> TokenPayload:
    """Tokenni tekshiradi va yuklamasini qaytaradi.

    Replay (ikkinchi marta ishlatish) tekshiruvi bu yerda EMAS — u bazaga
    yozishni talab qiladi, `app.attendance.consume_token` da bajariladi.
    """
    token = (token or "").strip()
    if not token:
        raise MalformedToken("token bo'sh")

    try:
        raw = _b64decode(token)
    except Exception as exc:  # noqa: BLE001 — har qanday dekod xatosi bir xil natija
        raise MalformedToken("base64 dekodlanmadi") from exc

    if len(raw) != _TOKEN_BYTES:
        raise MalformedToken(f"uzunlik {len(raw)}, kutilgani {_TOKEN_BYTES}")

    body, signature = raw[: _HEADER.size], raw[_HEADER.size :]
    if not hmac.compare_digest(signature, _sign(body)):
        raise BadSignature("imzo mos kelmadi")

    location_id, issued, nonce = _HEADER.unpack(body)
    payload = TokenPayload(
        location_id=location_id,
        issued_at_epoch=issued,
        nonce_hex=f"{nonce:08x}",
    )

    ttl = settings.qr_ttl_seconds if ttl_seconds is None else ttl_seconds
    age = payload.age_seconds(at_epoch)
    if age > ttl:
        raise ExpiredToken(f"token {age} sekundlik, ruxsat {ttl} sekund")
    if age < -_CLOCK_SKEW_SECONDS:
        # Kelajakdan kelgan token — soat buzilgan yoki token qalbaki.
        raise MalformedToken(f"token kelajakdan ({age} sekund)")

    return payload


def new_api_key() -> str:
    """Kiosk uchun maxfiy kalit."""
    return secrets.token_urlsafe(24)


# Telegram username qoidasi: 5-32 belgi, faqat harf/raqam/pastki chiziq.
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


def clean_username(raw: str) -> str:
    """`BOT_USERNAME` ni tozalab, to'g'riligini tekshiradi. Xato bo'lsa "" qaytadi.

    NEGA ALOHIDA TEKSHIRUV
    ----------------------
    Bu maydonga ko'pincha botning KO'RINADIGAN NOMI yoziladi ("Davomat tizimi")
    — unda probel bor. Undan yasalgan havola `https://t.me/Davomat tizimi?...`
    bo'lib chiqadi: telefon bunday QR ni skanerlaydi-yu, hech narsa qilmaydi,
    chunki manzil yaroqsiz. Xatolik jimgina yuz beradi va sababini topish
    qiyin — shuning uchun formatni oldindan tekshiramiz.
    """
    candidate = (raw or "").strip().lstrip("@")
    return candidate if _USERNAME_RE.fullmatch(candidate) else ""


def deep_link(token: str) -> str:
    """QR ichiga yoziladigan havola: skanerlangan zahoti Telegram ochiladi.

    Username yaroqsiz bo'lsa "" qaytaradi — chaqiruvchi QR chizmasligi va
    o'rniga ogohlantirish ko'rsatishi kerak. Buzuq havolali QR chizishdan
    ko'ra hech narsa chizmaslik yaxshiroq: birinchisi ishlayotgandek
    ko'rinadi-yu, aslida ishlamaydi.
    """
    username = clean_username(settings.bot_username)
    return f"https://t.me/{username}?start={token}" if username else ""
