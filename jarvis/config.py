"""Конфигурация Jarvis: читается из переменных окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Переменные, через которые SDK ушёл бы на оплату по API-ключу.
# Снимаем их до старта, чтобы Claude Code CLI использовал OAuth-подписку.
SUBSCRIPTION_BLOCKERS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def force_subscription_auth() -> list[str]:
    """Убирает API-ключи из окружения. Возвращает имена снятых переменных."""
    removed = []
    for name in SUBSCRIPTION_BLOCKERS:
        if os.environ.pop(name, None):
            removed.append(name)
    return removed


def _load_dotenv(path: Path) -> None:
    """Минимальный .env-загрузчик, чтобы не тянуть лишнюю зависимость."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _int_set(raw: str) -> frozenset[int]:
    return frozenset(int(part) for part in raw.replace(",", " ").split() if part.strip())


@dataclass(frozen=True)
class Config:
    telegram_token: str
    owner_ids: frozenset[int]
    workspace: Path
    model: str | None
    permission_mode: str
    allowed_tools: list[str]
    show_tools: bool
    max_turns: int | None
    max_budget_usd: float | None
    persona: str = field(repr=False, default="")

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Config":
        _load_dotenv(env_file or Path(".env"))

        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise SystemExit(
                "TELEGRAM_BOT_TOKEN не задан. Получите токен у @BotFather "
                "и положите его в .env (см. .env.example)."
            )

        owners = _int_set(os.environ.get("JARVIS_OWNER_IDS", ""))
        if not owners:
            raise SystemExit(
                "JARVIS_OWNER_IDS не задан. Бот работает на вашей личной подписке, "
                "поэтому отвечать он должен только вам. Узнать свой ID: напишите "
                "боту /id после первого запуска с временным значением 0."
            )

        workspace = Path(os.environ.get("JARVIS_WORKSPACE", "./workspace")).expanduser()
        workspace.mkdir(parents=True, exist_ok=True)

        tools_raw = os.environ.get("JARVIS_ALLOWED_TOOLS", "Read,Write,Edit,Glob,Grep,WebSearch,WebFetch")
        allowed_tools = [t.strip() for t in tools_raw.split(",") if t.strip()]

        max_turns = os.environ.get("JARVIS_MAX_TURNS", "").strip()
        budget = os.environ.get("JARVIS_MAX_BUDGET_USD", "").strip()

        return cls(
            telegram_token=token,
            owner_ids=owners,
            workspace=workspace.resolve(),
            model=os.environ.get("JARVIS_MODEL", "").strip() or None,
            permission_mode=os.environ.get("JARVIS_PERMISSION_MODE", "acceptEdits").strip(),
            allowed_tools=allowed_tools,
            show_tools=os.environ.get("JARVIS_SHOW_TOOLS", "1").strip() not in ("0", "false", ""),
            max_turns=int(max_turns) if max_turns else None,
            max_budget_usd=float(budget) if budget else None,
            persona=os.environ.get("JARVIS_PERSONA", DEFAULT_PERSONA),
        )


DEFAULT_PERSONA = """\
Ты — Jarvis, личный ассистент своего владельца, работающий в Telegram.

Стиль общения:
- Отвечай на языке собеседника (русский, узбекский или английский).
- Коротко и по делу: Telegram — не терминал, длинные простыни здесь неудобны.
- Никаких преамбул вроде «Конечно!» или «Вот ваш ответ». Сразу суть.
- Если задача выполнена — скажи результат одним предложением, детали ниже.

Формат:
- Обычный текст. Заголовки и таблицы не используй — Telegram их не рендерит.
- Код — в тройных обратных кавычках, коротко.
- Списки — только когда пунктов действительно несколько.

Работа:
- У тебя есть инструменты для файлов и веба. Рабочая папка — твоя песочница.
- Не выходи за рамки просьбы: не рефактори, не добавляй лишнего.
- Если чего-то не знаешь или инструмент недоступен — скажи прямо, не выдумывай.
"""
