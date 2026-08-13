"""Озвучка ответов: текст -> голосовое сообщение Telegram.

Голоса берём у edge-tts: бесплатно, без ключей и заметно живее, чем
встроенный синтезатор Windows. Telegram принимает голосовые только в
OGG/Opus, поэтому mp3 перекодируем через PyAV — он уже стоит вместе
с распознаванием, отдельный ffmpeg не нужен.
"""

from __future__ import annotations

import io
import logging
import re

log = logging.getLogger(__name__)

# Мужской русский голос — ближе к Джарвису. Женский: ru-RU-SvetlanaNeural
DEFAULT_VOICE = "ru-RU-DmitryNeural"

_CODE_BLOCK = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`[^`]*`")
_URL = re.compile(r"https?://\S+")
_MARKUP = re.compile(r"[*_#>|]+")
_SPACES = re.compile(r"[ \t]{2,}")


def speakable(text: str, limit: int) -> str:
    """Готовит текст к произнесению.

    Код, ссылки и разметку вслух читать бессмысленно — вырезаем.
    Длинный ответ обрезаем по границе предложения: слушать десять минут
    синтезированной речи никто не станет, текст рядом никуда не денется.
    """
    text = _CODE_BLOCK.sub(" ", text)
    text = _INLINE_CODE.sub(" ", text)
    text = _URL.sub(" ссылка ", text)
    text = _MARKUP.sub(" ", text)
    text = _SPACES.sub(" ", text).strip()

    if len(text) <= limit:
        return text

    cut = text[:limit]
    for end in ("\n", ". ", "! ", "? "):
        pos = cut.rfind(end)
        if pos > limit // 2:
            return cut[: pos + 1].strip()
    return cut.rsplit(" ", 1)[0].strip()


def _to_ogg_opus(mp3: bytes) -> bytes:
    """Перекодирует mp3 в OGG/Opus — единственный формат голосовых Telegram."""
    import av

    source = av.open(io.BytesIO(mp3))
    buffer = io.BytesIO()
    target = av.open(buffer, mode="w", format="ogg")
    stream = target.add_stream("libopus", rate=48000)
    stream.layout = "mono"
    resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)

    try:
        for frame in source.decode(audio=0):
            for resampled in resampler.resample(frame):
                for packet in stream.encode(resampled):
                    target.mux(packet)
        for resampled in resampler.resample(None):
            for packet in stream.encode(resampled):
                target.mux(packet)
        for packet in stream.encode(None):
            target.mux(packet)
    finally:
        target.close()
        source.close()

    return buffer.getvalue()


def should_speak(text: str, *, asked_by_voice: bool, mode: str, limit: int) -> bool:
    """Озвучивать ли этот ответ.

    В режиме `auto` бот отвечает тем же способом, каким к нему обратились:
    наговорили голосом — ответит голосом, напечатали — ответит текстом.
    Код вслух не читается никогда: слушать его невозможно.
    """
    if mode == "never" or not text.strip():
        return False
    if "```" in text:
        return False
    if mode == "always":
        return True
    if not asked_by_voice:
        return False
    # Ответ во много раз длиннее лимита озвучки — слушать огрызок бессмысленно.
    return len(text) <= limit * 3


class Speaker:
    """Синтез речи. Молча отключается, если что-то не так — текст всё равно уйдёт."""

    def __init__(self, voice: str = DEFAULT_VOICE, max_chars: int = 700) -> None:
        self._voice = voice
        self._max_chars = max_chars

    @property
    def enabled(self) -> bool:
        return bool(self._voice)

    @staticmethod
    def installed() -> bool:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return False
        return True

    async def synthesize(self, text: str) -> bytes | None:
        """Возвращает голосовое в OGG/Opus или None, если озвучивать нечего."""
        if not self.enabled:
            return None

        spoken = speakable(text, self._max_chars)
        if len(spoken) < 2:
            return None

        import asyncio

        import edge_tts

        communicate = edge_tts.Communicate(spoken, self._voice)
        chunks = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.extend(chunk["data"])

        if not chunks:
            return None
        # Перекодирование упирается в процессор — уводим из основного потока.
        return await asyncio.to_thread(_to_ogg_opus, bytes(chunks))
