"""Конфигурация Jarvis: читается из переменных окружения."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

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
    # utf-8-sig: Блокнот и PowerShell любят ставить BOM в начало файла.
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _int_set(raw: str) -> frozenset[int]:
    return frozenset(int(part) for part in raw.replace(",", " ").split() if part.strip())


def _dirs(raw: str) -> list[Path]:
    """Папки компьютера, к которым Jarvis получает доступ помимо песочницы."""
    result = []
    for part in raw.split(";"):
        part = part.strip().strip('"')
        if not part:
            continue
        path = Path(os.path.expandvars(part)).expanduser()
        if path.is_dir():
            result.append(path.resolve())
        else:
            log.warning("Папки нет, пропускаю: %s", path)
    return result


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
    whisper_model: str
    tts_voice: str
    tts_max_chars: int
    tts_mode: str
    max_files_per_reply: int
    memory_days: float
    extra_dirs: list[Path]
    persona: str = field(repr=False, default="")

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Config:
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

        # Bash нужен для навыков вроде pptx/xlsx: они собирают документы
        # python-скриптами. Уберите его, если такая возможность не нужна.
        tools_raw = os.environ.get(
            "JARVIS_ALLOWED_TOOLS", "Read,Write,Edit,Glob,Grep,Bash,WebSearch,WebFetch"
        )
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
            # Пусто = голосовые не распознаём. tiny/base/small/medium/large-v3
            whisper_model=os.environ.get("JARVIS_WHISPER_MODEL", "small").strip(),
            # Пусто = отвечать только текстом, без голосовых.
            tts_voice=os.environ.get("JARVIS_TTS_VOICE", "ru-RU-DmitryNeural").strip(),
            tts_max_chars=int(os.environ.get("JARVIS_TTS_MAX_CHARS", "700")),
            # auto = отвечать тем же способом, каким спросили. always | never
            tts_mode=os.environ.get("JARVIS_TTS_MODE", "auto").strip().lower(),
            max_files_per_reply=int(os.environ.get("JARVIS_MAX_FILES", "5")),
            # 0 = помнить бессрочно. Число = забывать разговор через столько дней.
            memory_days=float(os.environ.get("JARVIS_MEMORY_DAYS", "0")),
            extra_dirs=_dirs(os.environ.get("JARVIS_EXTRA_DIRS", "")),
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
- У тебя есть инструменты для файлов, команд и веба. Рабочая папка — песочница;
  кроме неё могут быть открыты настоящие папки компьютера собеседника.
- В чужих папках будь осторожен: читать и создавать — свободно, изменять и
  удалять чужие файлы — только когда об этом попросили прямо и однозначно.
- Предохранитель проверяет и команды, и содержимое скриптов, которые ты
  запускаешь. Получив отказ, не ищи обход — ни через скрипт, ни через
  вложенную команду: объясни, что и почему не вышло, и предложи безопасный
  путь. Обход предохранителя это не решение задачи, а нарушение доверия.
- Не выходи за рамки просьбы: не рефактори, не добавляй лишнего.
- Если чего-то не знаешь или инструмент недоступен — скажи прямо, не выдумывай.

Файлы от собеседника:
- Присланные файлы, фотографии и скриншоты бот кладёт в подпапку `inbox` и
  сообщает тебе путь. Открой файл и работай с ним: разбери, объясни, переведи,
  посчитай — смотря о чём просят. Фотографии тоже открывай, ты их видишь.
- Если к файлу нет вопроса, коротко скажи, что это, и спроси, что с ним делать.

Файлы:
- Всё, что ты сохранишь в рабочей папке, бот сам отправит собеседнику в чат.
- Поэтому готовый результат — презентацию, таблицу, документ — просто сохрани
  файлом с понятным именем. Не пересказывай его содержимое текстом и не пиши
  «файл сохранён по пути…»: человек получит его следующим сообщением.
- Черновики и промежуточные файлы держи в подпапке `tmp`, её бот не отправляет.

Память:
- Разговор продолжается бессрочно, но старые сообщения со временем сжимаются
  в пересказ. Поэтому важное храни дословно в файле `tmp/memory.md`.
- Туда записывай то, что должно пережить любое сжатие: факты о собеседнике,
  его предпочтения, решения, договорённости, имена и цифры, к которым вы
  возвращаетесь. Одна строка — один факт, с датой.
- Прочитай `tmp/memory.md` в начале разговора и всякий раз, когда собеседник
  ссылается на что-то из прошлого. Не заставляй его повторять сказанное.
- Обновляй существующие записи вместо дублирования, устаревшее удаляй.
  Не записывай пароли и коды.
"""
