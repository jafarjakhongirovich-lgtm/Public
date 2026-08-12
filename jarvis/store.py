"""Хранилище сессий: чтобы разговор продолжался после перезапуска бота.

Claude Code держит историю сессий у себя на диске, нам достаточно запомнить
их идентификаторы и передать при следующем подключении.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)


class SessionStore:
    """chat_id -> id сессии Claude, с ограничением по сроку жизни."""

    def __init__(self, path: Path, ttl_days: float = 0.0) -> None:
        self._path = path
        # 0 или меньше — срока нет, разговор живёт бессрочно.
        self._ttl = ttl_days * 86400 if ttl_days > 0 else None
        self._data: dict[str, dict] = self._read()

    def _read(self) -> dict[str, dict]:
        if not self._path.is_file():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            log.warning("Файл сессий повреждён, начинаю с чистого листа: %s", self._path)
            return {}

    def _write(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except OSError:
            log.exception("Не удалось сохранить файл сессий")

    def get(self, chat_id: int) -> str | None:
        """Живой id сессии или None, если её нет или срок вышел."""
        entry = self._data.get(str(chat_id))
        if not entry:
            return None
        if self._ttl is not None and time.time() - entry.get("updated_at", 0) > self._ttl:
            log.info("Сессия чата %s старше срока хранения — начинаю новую", chat_id)
            self.clear(chat_id)
            return None
        return entry.get("session_id")

    def put(self, chat_id: int, session_id: str) -> None:
        current = self._data.get(str(chat_id), {})
        if current.get("session_id") == session_id:
            current["updated_at"] = time.time()
        else:
            self._data[str(chat_id)] = {"session_id": session_id, "updated_at": time.time()}
        self._write()

    def clear(self, chat_id: int) -> None:
        if self._data.pop(str(chat_id), None) is not None:
            self._write()
