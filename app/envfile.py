"""`.env` faylini xavfsiz o'qish va yangilash.

NEGA ALOHIDA MODUL
------------------
Sozlamani brauzerdan saqlaganda faylni butunlay qayta yozib yuborish oson —
va shu bilan birga foydalanuvchi qo'lda yozgan izohlar, `DATABASE_URL`,
`ADMIN_PASSWORD` kabi qatorlar yo'qoladi. Bu yerdagi `update_env` faqat
kerakli kalitlarni almashtiradi, qolgan hamma narsani joyida qoldiradi.

Yozish atomik: avval yonidagi vaqtinchalik faylga yoziladi, so'ng
`os.replace` bilan almashtiriladi. Shunda yozish yarmida uzilib qolsa ham
eski `.env` buzilmaydi — server keyingi safar bo'sh faylni o'qib, hamma
sozlamani standart qiymatga qaytarib yubormaydi.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# `.env` da qiymat tirnoqsiz yoziladi. Qiymat ichida yangi qator bo'lsa
# fayl buziladi, shuning uchun bunday qiymatni umuman qabul qilmaymiz.
_FORBIDDEN = ("\n", "\r", "\0")


class EnvWriteError(RuntimeError):
    """Faylni yozib bo'lmadi (huquq yo'q, disk to'la va h.k.)."""


def _split_key(line: str) -> str | None:
    """Qatordagi kalitni qaytaradi; izoh yoki bo'sh qator bo'lsa — `None`."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    return stripped.split("=", 1)[0].strip()


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key = _split_key(line)
        if key:
            values[key] = line.split("=", 1)[1].strip()
    return values


def update_env(path: Path, changes: dict[str, str]) -> None:
    """Berilgan kalitlarni yangilaydi, qolgan qatorlarga tegmaydi.

    Fayl yo'q bo'lsa — yaratiladi. Kalit faylda yo'q bo'lsa — oxiriga
    qo'shiladi.
    """
    for key, value in changes.items():
        if any(bad in value for bad in _FORBIDDEN):
            raise EnvWriteError(f"{key} qiymatida yangi qator belgisi bor")

    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(changes)

    for index, line in enumerate(lines):
        key = _split_key(line)
        if key in remaining:
            lines[index] = f"{key}={remaining.pop(key)}"

    if remaining and lines and lines[-1].strip():
        lines.append("")
    for key, value in remaining.items():
        lines.append(f"{key}={value}")

    text = "\n".join(lines).rstrip("\n") + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        Path(temporary).unlink(missing_ok=True)
        raise EnvWriteError(str(exc)) from exc
