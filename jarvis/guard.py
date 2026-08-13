"""Предохранитель на команды.

Как только Jarvis получает доступ к настоящим папкам, у ошибки появляется цена.
Спросить подтверждение в Telegram агент не может — он ждёт ответа не от нас,
а от протокола. Поэтому необратимое запрещаем сразу, с объяснением: Claude
прочитает причину отказа и предложит безопасный вариант.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

# Каждая пара: что ищем в команде и как объяснить отказ.
DANGEROUS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\s+(-\w*\s+)*-?\w*[rf]", re.I), "рекурсивное удаление"),
    (re.compile(r"\b(del|erase)\s+.*(/s|/q)", re.I), "массовое удаление файлов"),
    (re.compile(r"\b(rd|rmdir)\s+.*/s", re.I), "удаление папки со всем содержимым"),
    (re.compile(r"\bformat\s+[a-z]:", re.I), "форматирование диска"),
    (re.compile(r"\b(mkfs|diskpart|fdisk)\b", re.I), "операции с разделами диска"),
    (re.compile(r"\bdd\s+if=", re.I), "низкоуровневая запись на диск"),
    (re.compile(r"\breg\s+delete\b", re.I), "удаление из реестра Windows"),
    (re.compile(r"\b(shutdown|reboot)\b", re.I), "выключение компьютера"),
    (re.compile(r"\bcipher\s+/w", re.I), "затирание свободного места"),
    (re.compile(r":\s*\(\s*\)\s*\{.*\|.*&\s*\}\s*;", re.S), "форк-бомба"),
    (re.compile(r"\b(curl|wget|iwr|irm)\b.*\|\s*(sh|bash|iex|powershell)", re.I),
     "запуск скачанного скрипта без проверки"),
]

REFUSAL = (
    "Команда заблокирована предохранителем бота: {reason}. "
    "Это необратимо, а подтвердить вживую собеседник не может. "
    "Предложи ему сделать это самому или выбери безопасный путь "
    "(например, перенести в отдельную папку вместо удаления)."
)


def check_command(command: str) -> str | None:
    """Возвращает причину отказа или None, если команда безопасна."""
    for pattern, reason in DANGEROUS:
        if pattern.search(command):
            return reason
    return None


def make_hooks() -> dict:
    """Хуки для ClaudeAgentOptions.hooks.

    Именно хук, а не `can_use_tool`: инструмент, перечисленный в
    `allowed_tools`, одобряется раньше, чем callback успевает вмешаться —
    SDK честно предупреждает об этом. PreToolUse срабатывает всегда.
    """
    from claude_agent_sdk import HookMatcher

    async def before_bash(input_data: dict, _tool_use_id, _context) -> dict:
        command = str(input_data.get("tool_input", {}).get("command", ""))
        reason = check_command(command)
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
