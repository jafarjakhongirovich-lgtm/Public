"""Telegram-слой Jarvis."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import tempfile
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction, ChatType
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
from .speech import Speaker, should_speak
from .voice import INSTALL_HINT, Transcriber

log = logging.getLogger(__name__)

TELEGRAM_MSG_LIMIT = 4096
# Боты не могут скачивать файлы крупнее — ограничение Bot API.
TELEGRAM_DOWNLOAD_LIMIT = 20 * 1024 * 1024

GREETING = (
    "Jarvis на связи.\n\n"
    "Пишите текстом или наговаривайте голосовые — понимаю и то, и другое.\n"
    "Отвечаю так же, как спросили: на голосовое — голосом.\n"
    "Могу собрать презентацию, таблицу или документ и прислать файлом.\n"
    "Разговор помню, даже если бот перезапускался.\n\n"
    "/new — забыть всё и начать заново\n"
    "/stop — прервать текущую работу\n"
    "/voice — когда отвечать голосом\n"
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
        self.speaker = (
            Speaker(config.tts_voice, config.tts_max_chars) if config.tts_voice else None
        )
        # Режим озвучки на чат: auto | always | never. Меняется командой /voice.
        self.voice_mode: dict[int, str] = {}
        # Про кого из посторонних уже доложили владельцу.
        self._reported: set[int] = set()

    # ---------- доступ ----------

    def _authorized(self, update: Update) -> bool:
        """Владелец, и только в личной переписке.

        Групповой чат отсекаем отдельно: там владельца могли добавить без его
        ведома, и любой участник видел бы ответы бота.
        """
        user = update.effective_user
        chat = update.effective_chat
        if user is None or chat is None:
            return False
        if chat.type != ChatType.PRIVATE:
            return False
        return user.id in self.config.owner_ids

    async def _deny(self, update: Update) -> None:
        """Посторонним не отвечаем ничего.

        Ответ — это подтверждение, что бот жив, и повод продолжать. Молчание
        не даёт ни того, ни другого. Владельцу сообщаем один раз про каждого,
        чтобы он знал, что кто-то стучится.
        """
        user = update.effective_user
        chat = update.effective_chat
        user_id = getattr(user, "id", None)
        log.warning(
            "Отклонён доступ: id=%s username=%s чат=%s",
            user_id,
            getattr(user, "username", "?"),
            getattr(chat, "type", "?"),
        )
        if user_id is None or user_id in self._reported:
            return
        self._reported.add(user_id)
        name = getattr(user, "full_name", None) or getattr(user, "username", "") or "без имени"
        for owner in self.config.owner_ids:
            with contextlib.suppress(Exception):
                await update.get_bot().send_message(
                    owner,
                    f"К боту постучался посторонний: {name} (ID {user_id}). "
                    "Я ему не ответил.",
                )

    # ---------- команды ----------

    async def cmd_id(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Единственная команда для всех: без неё владелец не узнает свой ID."""
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

    async def cmd_voice(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return await self._deny(update)

        chat_id = update.effective_chat.id
        arg = (ctx.args[0].lower() if ctx.args else "").strip()
        aliases = {
            "auto": "auto", "авто": "auto",
            "on": "always", "вкл": "always", "да": "always", "always": "always",
            "off": "never", "выкл": "never", "нет": "never", "never": "never",
        }

        if arg not in aliases:
            current = self.voice_mode.get(chat_id, self.config.tts_mode)
            names = {
                "auto": "по обстановке — голосом отвечаю на голосовые",
                "always": "всегда голосом",
                "never": "только текстом",
            }
            await update.effective_message.reply_text(
                f"Сейчас: {names.get(current, current)}.\n\n"
                "/voice авто — отвечать так же, как спросили\n"
                "/voice вкл — озвучивать всё\n"
                "/voice выкл — только текст"
            )
            return

        self.voice_mode[chat_id] = aliases[arg]
        replies = {
            "auto": "Буду отвечать так же, как вы спросите.",
            "always": "Буду озвучивать ответы.",
            "never": "Только текст.",
        }
        await update.effective_message.reply_text(replies[aliases[arg]])

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

        if not self.transcriber.ready:
            # Молчание на несколько минут выглядит как зависший бот.
            await message.reply_text(
                "Первое голосовое: скачиваю модель распознавания, это разово "
                "и займёт пару минут. Дальше будет быстро."
            )

        text = await self._transcribe(message)
        if not text:
            return

        # Показываем расшифровку: видно, что именно бот услышал.
        await message.reply_text(f"Услышал: {text}")
        await self._run(message, text, by_voice=True)

    async def on_file(self, update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Пользователь прислал документ или фото — кладём в inbox и разбираем."""
        if not self._authorized(update):
            return await self._deny(update)

        message = update.effective_message
        try:
            path = await self._save_incoming(message)
        except Exception as exc:  # noqa: BLE001
            log.exception("Не удалось принять файл")
            await message.reply_text(f"Не смог принять файл: {exc}")
            return

        question = (message.caption or "").strip()
        prompt = (
            f"Собеседник прислал файл: {path}\n"
            + (f"И спрашивает: {question}" if question else "Вопроса не задал.")
        )
        await self._run(message, prompt)

    async def _save_incoming(self, message) -> Path:
        """Скачивает присланное в inbox под понятным именем."""
        source = message.document or message.video or message.audio
        size = getattr(source, "file_size", None) if source else None
        if size and size > TELEGRAM_DOWNLOAD_LIMIT:
            # Ограничение Telegram, обойти его на нашей стороне нельзя.
            raise ValueError(
                f"файл {size // 1024 // 1024} МБ, а боты в Telegram могут "
                "скачивать не больше 20 МБ. Пришлите файл поменьше или "
                "положите его в рабочую папку сами."
            )

        inbox = self.config.workspace / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)

        if message.photo:
            # В photo лежит лесенка размеров, последний — самый крупный.
            tg_file = await message.photo[-1].get_file()
            name = f"photo_{message.message_id}.jpg"
        else:
            tg_file = await source.get_file()
            name = getattr(source, "file_name", None) or f"file_{message.message_id}"

        path = inbox / Path(name).name
        async with typing(message.get_bot(), message.chat_id):
            await tg_file.download_to_drive(path)
        log.info("Принят файл: %s", path.name)
        return path

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

    async def _run(self, message, prompt: str, *, by_voice: bool = False) -> None:
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
        await self._speak(message, reply.text, by_voice)
        await self._send_files(message, produced)

    async def _speak(self, message, text: str, by_voice: bool) -> None:
        """Присылает голосовую версию ответа, когда это уместно."""
        if self.speaker is None:
            return
        mode = self.voice_mode.get(message.chat_id, self.config.tts_mode)
        if not should_speak(
            text, asked_by_voice=by_voice, mode=mode, limit=self.config.tts_max_chars
        ):
            return
        if not Speaker.installed():
            log.warning("edge-tts не установлен — озвучка пропущена")
            return
        try:
            async with typing(message.get_bot(), message.chat_id):
                audio = await self.speaker.synthesize(text)
            if audio:
                await message.reply_voice(voice=audio)
        except Exception:  # noqa: BLE001
            # Текст собеседник уже получил, молчание тут лучше ошибки.
            log.exception("Не удалось озвучить ответ")

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
        app.add_handler(CommandHandler("voice", self.cmd_voice))
        app.add_handler(MessageHandler(filters.VOICE, self.on_voice))
        app.add_handler(
            MessageHandler(filters.Document.ALL | filters.PHOTO | filters.AUDIO, self.on_file)
        )
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))
        return app

    async def _on_shutdown(self, _app: Application) -> None:
        await self.sessions.shutdown()
