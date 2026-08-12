"""Распознавание голосовых сообщений — локально, через faster-whisper.

Подписка Claude покрывает только текст, поэтому речь распознаём на машине
пользователя: без API-ключей, без интернета и без дополнительной оплаты.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger(__name__)

INSTALL_HINT = (
    "Распознавание голоса не установлено. В папке бота выполните:\n"
    "  .venv\\Scripts\\pip install faster-whisper"
)


class Transcriber:
    """Ленивая обёртка над Whisper: модель грузится при первом голосовом."""

    def __init__(self, model_size: str = "small", compute_type: str = "int8") -> None:
        self._model_size = model_size
        self._compute_type = compute_type
        self._model = None
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self._model_size)

    @staticmethod
    def installed() -> bool:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False
        return True

    def _load(self):
        """Грузит модель. Первый раз качает её (~0.5 ГБ для small)."""
        from faster_whisper import WhisperModel

        log.info("Загружаю модель распознавания '%s' (первый раз — скачивание)", self._model_size)
        model = WhisperModel(self._model_size, device="cpu", compute_type=self._compute_type)
        log.info("Модель распознавания готова")
        return model

    def _transcribe_sync(self, path: Path) -> str:
        if self._model is None:
            self._model = self._load()
        segments, _info = self._model.transcribe(
            str(path),
            beam_size=5,
            vad_filter=True,  # отсекает тишину — заметно быстрее и точнее
        )
        return "".join(segment.text for segment in segments).strip()

    async def transcribe(self, path: Path) -> str:
        """Распознаёт файл. Whisper блокирующий, поэтому уводим его в поток."""
        if not self.enabled:
            raise RuntimeError("Распознавание отключено")
        # Одна модель на процесс — параллельные запуски только съедят память.
        async with self._lock:
            return await asyncio.to_thread(self._transcribe_sync, path)
