"""Telegram-слой Jarvis."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .agent import Reply, SessionRegistry
from .config import Config

log = logging.getLogger(__name__)

TELEGRAM_MSG_LIMIT = 4096

GREETING = (
    "Jarvis на связи.\n\n"
    "Пишите обычным текстом — отвечу и, если нужно, поработаю с файлами в "
    "рабочей папке.\n\n"
    "/new — начать разговор заново\n"
    "/stop — прервать текущую работу\n"
    "/id — показать ваш Telegram ID"
)


def split_message(text: str, limit: int = TELEGRAM_MSG_LIMIT) -> list[str]:
    """Режет длинный ответ на части по границам строк, не ломая слова."""
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = window.rfind("\n")
        if cut < limit // 2:
            cut = window.rfind(" ")
        if cut < limit // 2:
            cut = limit
        parts.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts


@contextlib.asynccontextmanager
async def typing(bot, chat_id: int):
    """Держит индикатор «печатает…», пока агент работает."""

    async def loop() -> None:
        while True:
            with contextlib.suppress(Exception):
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(4)

    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


class JarvisBot:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.sessions = SessionRegistry(config)

    # ---------- доступ ----------

    def _authorized(self, update: Update) -> bool:
        user = update.effective_user
        return user is not None and user.id in self.config.owner_ids

    async def _deny(self, update: Update) -> None:
        user = update.effective_user
        log.warning("Отклонён доступ: id=%s username=%s", getattr(user, "id", "?"), getattr(user, "username", "?"))
        if update.effective_message:
            await update.effective_message.reply_text(
                "Этот бот работает на личной подписке владельца и отвечает только ему."
            )

    # ---------- команды ----------

    async def cmd_id(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if user and update.effective_message:
            await update.effective_message.reply_text(f"Ваш Telegram ID: {user.id}")

    async def cmd_start(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return await self._deny(update)
        await update.effective_message.reply_text(GREETING)

    async def cmd_new(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return await self._deny(update)
        await self.sessions.reset(update.effective_chat.id)
        await update.effective_message.reply_text("Контекст очищен. Слушаю.")

    async def cmd_stop(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return await self._deny(update)
        session = self.sessions.get(update.effective_chat.id)
        stopped = await session.interrupt()
        await update.effective_message.reply_text(
            "Остановил." if stopped else "Сейчас нечего останавливать."
        )

    # ---------- сообщения ----------

    async def on_text(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return await self._deny(update)

        message = update.effective_message
        prompt = (message.text or message.caption or "").strip()
        if not prompt:
            return

        session = self.sessions.get(update.effective_chat.id)
        async with typing(message.get_bot(), update.effective_chat.id):
            reply = await session.ask(prompt)

        await self._send(message, reply)

    async def on_voice(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return await self._deny(update)
        await update.effective_message.reply_text(
            "Голосовые пока не расшифровываю — напишите текстом."
        )

    async def _send(self, message, reply: Reply) -> None:
        if reply.error:
            await message.reply_text(f"Сбой: {reply.error}")
            return

        text = reply.text or "(пустой ответ)"
        if self.config.show_tools and reply.tools_used:
            unique = list(dict.fromkeys(reply.tools_used))
            text = f"{text}\n\n— использовал: {', '.join(unique)}"

        for part in split_message(text):
            await message.reply_text(part)

    # ---------- сборка ----------

    def build(self) -> Application:
        app = (
            Application.builder()
            .token(self.config.telegram_token)
            .post_shutdown(self._on_shutdown)
            .build()
        )
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_start))
        app.add_handler(CommandHandler("new", self.cmd_new))
        app.add_handler(CommandHandler("stop", self.cmd_stop))
        app.add_handler(CommandHandler("id", self.cmd_id))
        app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.on_voice))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))
        return app

    async def _on_shutdown(self, _app: Application) -> None:
        await self.sessions.shutdown()
