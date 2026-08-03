"""Baza ulanishi va sessiya."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings


def _is_transaction_pooler(url: str) -> bool:
    """URL pgbouncer'ning "transaction" rejimiga ishora qiladimi?

    Supabase (va boshqa bulutlar) serverless uchun aynan shu rejimni tavsiya
    qiladi: 6543-port yoki `pooler.` hostli manzil, ba'zan `?pgbouncer=true`.
    """
    lowered = url.lower()
    return ":6543" in lowered or "pgbouncer=true" in lowered or "pooler." in lowered


def _engine_options(url: str) -> dict:
    """Ulanish sozlamalari — muhitga qarab.

    NEGA BU KERAK
    -------------
    Transaction rejimidagi pgbouncer har bir tranzaksiyadan keyin ulanishni
    boshqa mijozga beradi. psycobg esa takrorlanadigan so'rovlarni server
    tomonida "prepared statement" qilib saqlaydi va keyin ularga nom bilan
    murojaat qiladi — u nom endi boshqa ulanishda mavjud emas. Natijada
    "prepared statement ... already exists" xatolari **vaqti-vaqti bilan**
    chiqadi: dastlab hammasi ishlaydi, yuk oshgach buziladi. Diagnostikasi
    og'ir, shuning uchun oldindan o'chirib qo'yamiz.
    """
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}, "pool_pre_ping": True}

    if _is_transaction_pooler(url):
        return {
            # prepare_threshold=None — prepared statement umuman ishlatilmaydi.
            "connect_args": {"prepare_threshold": None},
            # Pool'ni pgbouncer yuritadi; serverless'da har chaqiruv qisqa umr
            # ko'rgani uchun o'z pool'imizni saqlashning ma'nosi yo'q.
            "poolclass": NullPool,
        }

    return {"pool_pre_ping": True, "pool_recycle": 1800}


engine = create_engine(settings.database_url, **_engine_options(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Tranzaksiya bilan sessiya: xatolik bo'lsa rollback."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401  (modellar registrga tushishi uchun)

    models.Base.metadata.create_all(engine)
