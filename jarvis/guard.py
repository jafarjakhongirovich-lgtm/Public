"""Предохранитель на команды.

Две задачи. Первая — не дать выполнить необратимое: спросить подтверждение
в Telegram агент не может, поэтому опасное запрещаем сразу, с объяснением
причины — Claude её прочитает и предложит безопасный вариант.

Вторая — не пускать его к личным файлам. Инструменты чтения и записи и так
ограничены разрешёнными папками, но `bash` этих границ не знает: `type`,
`cat` или `copy` дотянутся куда угодно. Здесь мы эту дыру и закрываем.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

# --- необратимое ---------------------------------------------------------

DANGEROUS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\s+(-\w*\s+)*-?\w*[rf]", re.I), "рекурсивное удаление"),
    (re.compile(r"\b(del|erase)\s+.*(/s|/q)", re.I), "массовое удаление файлов"),
    (re.compile(r"\b(rd|rmdir)\s+.*/s", re.I), "удаление папки со всем содержимым"),
    (re.compile(r"\bformat\s+[a-z]:", re.I), "форматирование диска"),
    (re.compile(r"\b(mkfs|diskpart|fdisk)\b", re.I), "операции с разделами диска"),
    (re.compile(r"\bdd\s+if=", re.I), "низкоуровневая запись на диск"),
    (re.compile(r"\breg\s+(delete|add)\b", re.I), "правка реестра Windows"),
    (re.compile(r"\b(shutdown|reboot)\b", re.I), "выключение компьютера"),
    (re.compile(r"\bcipher\s+/w", re.I), "затирание свободного места"),
    (re.compile(r":\s*\(\s*\)\s*\{.*\|.*&\s*\}\s*;", re.S), "форк-бомба"),
    (
        re.compile(r"\b(curl|wget|iwr|irm)\b.*\|\s*(sh|bash|iex|powershell)", re.I),
        "запуск скачанного скрипта без проверки",
    ),
]

# --- личное --------------------------------------------------------------

# Секреты: сюда нельзя, даже если папка формально разрешена.
SECRETS = re.compile(
    r"(\.ssh\b|id_rsa|id_ed25519|\.aws\b|\.gnupg\b|\.claude[\\/]|credentials\.json"
    r"|\.env\b|passwords?\.|wallet\.dat|Login\s*Data|Cookies)",
    re.I,
)

# Пути, похожие на личные или системные.
_WIN_PATH = re.compile(r"[a-zA-Z]:[\\/][^\s\"'|<>&;]*")
_UNIX_PATH = re.compile(r"(?<![\w.])(/(?:home|Users|root|etc|var)/[^\s\"'|<>&;]*)")
_HOME_SHORTHAND = re.compile(
    r"(%USERPROFILE%|%APPDATA%|%LOCALAPPDATA%|\$env:USERPROFILE|\$HOME|(?<![\w.])~[\\/])",
    re.I,
)

REFUSAL = (
    "Команда заблокирована предохранителем бота: {reason}. "
    "Подтвердить вживую собеседник не может, поэтому такие вещи запрещены сразу. "
    "Не ищи обход: объясни, что именно не вышло, и предложи безопасный путь."
)


def _normalize(path_text: str) -> str:
    """Путь к единому виду для сравнения.

    Через строки, а не через `Path`: `Path` разбирает пути по правилам той
    системы, где запущен код, и windows-путь на linux (или наоборот) считает
    относительным — проверка молча пропускала бы чужие файлы.
    """
    text = path_text.strip().strip("\"'").replace("\\", "/").rstrip("/")
    return text.lower()


def _inside(path_text: str, roots: list[Path]) -> bool:
    """Лежит ли путь внутри одной из разрешённых папок.

    Сюда попадают только абсолютные пути — относительные под регулярки
    не подходят и считаются своими: рабочая папка это cwd агента.
    """
    candidate = _normalize(path_text)
    for root in roots:
        base = _normalize(str(root))
        if base and (candidate == base or candidate.startswith(base + "/")):
            return True
    return False


def check_command(command: str, allowed_dirs: list[Path] | None = None) -> str | None:
    """Причина отказа или None, если команда безопасна."""
    for pattern, reason in DANGEROUS:
        if pattern.search(command):
            return reason

    if SECRETS.search(command):
        return "обращение к паролям, ключам или личным данным"

    # Без resolve(): пути уже абсолютные (config их разрешает при старте),
    # а повторный resolve() исказил бы их относительно текущего каталога.
    roots = list(allowed_dirs or [])
    if _HOME_SHORTHAND.search(command):
        return "обращение к личной папке пользователя"

    for match in list(_WIN_PATH.finditer(command)) + list(_UNIX_PATH.finditer(command)):
        if not _inside(match.group(0), roots):
            return "обращение к файлам за пределами рабочей папки"

    return None


def make_hooks(allowed_dirs: list[Path] | None = None) -> dict:
    """Хуки для ClaudeAgentOptions.hooks.

    Именно хук, а не `can_use_tool`: инструмент, перечисленный в
    `allowed_tools`, одобряется раньше, чем callback успевает вмешаться —
    SDK честно предупреждает об этом. PreToolUse срабатывает всегда.
    """
    from claude_agent_sdk import HookMatcher

    async def before_bash(input_data: dict, _tool_use_id, _context) -> dict:
        command = str(input_data.get("tool_input", {}).get("command", ""))
        reason = check_command(command, allowed_dirs)
        if not reason:
            return {}
        log.warning("Заблокирована команда (%s): %s", reason, command[:200])
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": REFUSAL.format(reason=reason),
            }
        }

    return {"PreToolUse": [HookMatcher(matcher="Bash", hooks=[before_bash])]}
