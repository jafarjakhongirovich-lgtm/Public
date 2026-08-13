"""Поиск файлов, которые агент создал за время одного запроса.

Claude пишет презентации, таблицы и документы в рабочую папку. Бот сравнивает
её состояние до и после запроса и отправляет всё новое в чат.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Лимит Telegram на документ от бота.
TELEGRAM_FILE_LIMIT = 50 * 1024 * 1024

# Служебное: шумит и пользователю не нужно.
# tmp — черновики агента; inbox — то, что прислал сам собеседник.
# Ни то, ни другое отправлять обратно не нужно.
SKIP_DIRS = {
    "tmp", "inbox", ".git", "__pycache__", ".venv", "node_modules", ".cache", ".ipynb_checkpoints"
}
SKIP_SUFFIXES = {".pyc", ".pyo", ".tmp", ".part", ".crdownload", ".lock"}

Snapshot = dict[Path, tuple[float, int]]


def _interesting(path: Path) -> bool:
    if path.name.startswith("."):
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    return not any(part in SKIP_DIRS for part in path.parts)


def snapshot(root: Path) -> Snapshot:
    """Состояние папки: путь -> (время изменения, размер)."""
    state: Snapshot = {}
    if not root.is_dir():
        return state
    for path in root.rglob("*"):
        try:
            if not path.is_file() or not _interesting(path.relative_to(root)):
                continue
            stat = path.stat()
        except OSError:
            continue
        state[path] = (stat.st_mtime, stat.st_size)
    return state


def new_files(before: Snapshot, after: Snapshot, limit: int = 5) -> list[Path]:
    """Файлы, появившиеся или изменившиеся между двумя снимками.

    Возвращает самые свежие, не больше `limit` — чтобы бот не завалил чат,
    если агент сгенерировал полсотни промежуточных файлов.
    """
    changed = [path for path, meta in after.items() if before.get(path) != meta]
    too_big = [p for p in changed if after[p][1] > TELEGRAM_FILE_LIMIT]
    for path in too_big:
        log.warning("Файл %s больше 50 МБ — Telegram не примет, пропускаю", path.name)

    sendable = [p for p in changed if p not in too_big and after[p][1] > 0]
    sendable.sort(key=lambda p: after[p][0], reverse=True)
    return sendable[:limit]
