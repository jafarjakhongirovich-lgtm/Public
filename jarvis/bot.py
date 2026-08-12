"""Telegram-слой Jarvis."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import tempfile
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import outbox
from .agent import Reply, SessionRegistry
from .config import Config
from .voice import INSTALL_HINT, Transcriber

log = logging.getLogger(__name__)

TELEGRAM_MSG_LIMIT = 4096

GREETING = (
    "Jarvis на связи.\n\n"
    "Пишите текстом или наговаривайте голосовые — понимаю и то, и другое.\n"
    "Могу собрать презентацию, таблицу или документ и прислать файлом.\n"
    "Разговор помню, даже если бот перезапускался.\n\n"
    "/new — забыть всё и начать заново\n"
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
        self.transcriber = Transcriber(config.whisper_model) if config.whisper_model else None

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
        await update.effective_message.reply_text(
            "Разговор забыт, начинаем с чистого листа.\n"
            "Заметки в tmp/memory.md остались — их я помню в любом случае."
        )

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
        if prompt:
            await self._run(message, prompt)

    async def on_voice(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return await self._deny(update)

        message = update.effective_message
        if self.transcriber is None:
            await message.reply_text("Распознавание голоса выключено — напишите текстом.")
            return
        if not Transcriber.installed():
            await message.reply_text(INSTALL_HINT)
            return

        text = await self._transcribe(message)
        if not text:
            return

        # Показываем расшифровку: видно, что именно бот услышал.
        await message.reply_text(f"Услышал: {text}")
        await self._run(message, text)

    async def _transcribe(self, message) -> str | None:
        voice = message.voice or message.audio
        async with typing(message.get_bot(), message.chat_id):
            with tempfile.TemporaryDirectory() as tmpdir:
                path = Path(tmpdir) / "voice.ogg"
                try:
                    tg_file = await voice.get_file()
                    await tg_file.download_to_drive(path)
                    text = await self.transcriber.transcribe(path)
                except Exception as exc:  # noqa: BLE001
                    log.exception("Не удалось распознать голосовое")
                    await message.reply_text(f"Не смог разобрать голосовое: {exc}")
                    return None

        if not text:
            await message.reply_text("Ничего не расслышал — попробуйте ещё раз.")
            return None
        return text

    async def _run(self, message, prompt: str) -> None:
        """Общий путь для текста и расшифрованного голоса."""
        session = self.sessions.get(message.chat_id)
        workspace = self.config.workspace

        before = outbox.snapshot(workspace)
        async with typing(message.get_bot(), message.chat_id):
            reply = await session.ask(prompt)
        produced = outbox.new_files(
            before, outbox.snapshot(workspace), limit=self.config.max_files_per_reply
        )

        await self._send(message, reply)
        await self._send_files(message, produced)

    async def _send_files(self, message, paths: list[Path]) -> None:
        """Отправляет то, что агент сохранил в рабочей папке."""
        for path in paths:
            try:
                async with typing(message.get_bot(), message.chat_id):
                    with path.open("rb") as handle:
                        await message.reply_document(document=handle, filename=path.name)
                log.info("Отправлен файл: %s", path.name)
            except Exception:  # noqa: BLE001
                log.exception("Не удалось отправить файл %s", path)
                await message.reply_text(f"Файл {path.name} готов, но отправить не получилось.")

    async def _send(self, message, reply: Reply) -> None:
        if reply.error:
            await message.reply_text(f"Сбой: {reply.error}")
            return

        # Пустой текст — нормально, когда весь ответ это файл: он придёт следом.
        text = reply.text
        if not text:
            return
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
