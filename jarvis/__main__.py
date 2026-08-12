"""Точка входа: python -m jarvis"""

from __future__ import annotations

import logging
import shutil
import sys

from .bot import JarvisBot
from .config import Config, force_subscription_auth

log = logging.getLogger("jarvis")


def preflight() -> None:
    """Проверяет, что Claude Code CLI на месте и авторизация — по подписке."""
    if shutil.which("claude") is None:
        raise SystemExit(
            "Claude Code CLI не найден. Установите его и войдите под своей подпиской:\n"
            "  npm install -g @anthropic-ai/claude-code\n"
            "  claude login"
        )

    removed = force_subscription_auth()
    if removed:
        log.warning(
            "Убрал из окружения %s — иначе запросы шли бы по API-ключу с оплатой "
            "за токены, а не по вашей подписке.",
            " и ".join(removed),
        )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    preflight()
    config = Config.from_env()

    log.info("Рабочая папка: %s", config.workspace)
    log.info("Доступ разрешён для ID: %s", ", ".join(str(i) for i in sorted(config.owner_ids)))
    log.info("Авторизация: подписка Claude (через claude login), API-ключ не используется")

    JarvisBot(config).build().run_polling(drop_pending_updates=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
