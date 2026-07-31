"""Vercel uchun kirish nuqtasi.

Vercel `api/` papkasidagi fayllarni serverless funksiya sifatida ishga
tushiradi va ASGI ilovasini `app` nomi bilan qidiradi.

DIQQAT — serverless muhitning ikki farqi bor:

  * **Doimiy disk yo'q.** SQLite fayli saqlanmaydi, shuning uchun bu yerda
    faqat PostgreSQL ishlaydi (`DATABASE_URL` muhit o'zgaruvchisida).
  * **Doimiy jarayon yo'q.** Bot long polling qila olmaydi — Telegram o'zi
    `/telegram/<secret>` manziliga murojaat qiladi (webhook).

Jadval yaratish ham bu yerda emas: `AUTO_CREATE_TABLES=false` qo'yiladi va
baza bir marta lokal kompyuterdan tayyorlanadi:

    DATABASE_URL="postgresql+psycopg://..." python manage.py init
"""

import sys
from pathlib import Path

# Loyiha ildizini import yo'liga qo'shamiz: Vercel funksiyani `api/` ichidan
# ishga tushiradi va `app` paketi aks holda topilmaydi.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

__all__ = ["app"]
