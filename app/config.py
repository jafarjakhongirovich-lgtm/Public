"""Ilova sozlamalari (.env faylidan o'qiladi)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

# `.env` loyiha ildizida turadi. Nisbiy yo'l ("./.env") ishlagan katalogga
# bog'liq bo'lardi: serverni boshqa katalogdan ishga tushirsa, fayl umuman
# topilmaydi va hamma sozlama jimgina standart qiymatga qaytadi — ya'ni QR
# ishlamay qoladi, sababi esa hech qayerda ko'rinmaydi.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    secret_key: str = "dev-insecure-secret-key"
    database_url: str = "sqlite:///./tabel.db"
    timezone: str = "Asia/Tashkent"

    bot_token: str = ""
    bot_username: str = ""
    report_chat_id: str = ""

    qr_refresh_seconds: int = 15
    qr_ttl_seconds: int = 25

    admin_username: str = "admin"
    admin_password: str = "change-me"

    # ---- Internetga chiqarish (deploy) ----
    # Sayt qaysi manzilda turadi: "https://tabel.example.com". Webhook havolasi
    # va QR ichidagi havolalar shundan yasaladi. Lokal ishlashda bo'sh qoladi.
    public_base_url: str = ""
    # Telegram webhook uchun maxfiy yo'l va sarlavha. `manage.py secret` yasaydi.
    webhook_secret: str = ""
    # Serverless muhitda (Vercel) har bir "sovuq start" da jadval yaratishga
    # urinish keraksiz va xavfli — bir marta `manage.py init` qilinadi.
    auto_create_tables: bool = True

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def is_public(self) -> bool:
        """Sayt internetga chiqarilganmi? Xavfsizlik tekshiruvlari shunga bog'liq."""
        return bool(self.public_base_url.strip())

    @property
    def webhook_path(self) -> str:
        """Telegram murojaat qiladigan yo'l. Maxfiy qism yo'lning o'zida —
        tasodifiy so'rovlar 404 oladi va logni to'ldirmaydi."""
        return f"/telegram/{self.webhook_secret}"

    @property
    def webhook_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}{self.webhook_path}"

    def deployment_problems(self) -> list[str]:
        """Internetga chiqarishdan oldin albatta tuzatilishi kerak bo'lgan narsalar.

        Lokal ishlashda bularning ba'zilari muammo emas (masalan, oddiy parol
        faqat uy tarmog'idan ko'rinadi), shuning uchun tekshiruv `is_public`
        bo'lganda qattiqlashadi.
        """
        problems: list[str] = []
        default_keys = (
            "dev-insecure-secret-key",
            "change-me-please-use-a-long-random-string",
        )
        if self.secret_key in default_keys:
            problems.append("SECRET_KEY standart qiymatda — QR tokenlarini soxtalashtirish mumkin")
        elif len(self.secret_key) < 32:
            problems.append("SECRET_KEY juda qisqa (kamida 32 belgi bo'lsin)")

        if self.admin_password in ("change-me", "admin", "parol", "12345"):
            problems.append("ADMIN_PASSWORD juda oddiy — panelda oyliklar ko'rinadi")
        elif len(self.admin_password) < 12:
            problems.append("ADMIN_PASSWORD 12 belgidan qisqa")

        if self.database_url.startswith("sqlite"):
            problems.append(
                "SQLite serverless muhitda saqlanmaydi — PostgreSQL ulang (DATABASE_URL)"
            )
        if not self.webhook_secret or len(self.webhook_secret) < 16:
            problems.append("WEBHOOK_SECRET yo'q yoki qisqa — bot webhook'i himoyalanmaydi")

        from app.security import clean_username

        if not clean_username(self.bot_username):
            problems.append(
                "BOT_USERNAME yo'q yoki xato (probel/belgi bor) — QR ichidagi havola ishlamaydi"
            )
        if not self.public_base_url.startswith("https://"):
            problems.append("PUBLIC_BASE_URL https:// bilan boshlanishi kerak")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
