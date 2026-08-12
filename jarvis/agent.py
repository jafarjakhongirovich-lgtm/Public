"""Обёртка над Claude Agent SDK: одна сессия на чат, авторизация — подписка."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)

try:  # ToolUseBlock появился не во всех версиях SDK
    from claude_agent_sdk import ToolUseBlock
except ImportError:  # pragma: no cover
    ToolUseBlock = ()  # type: ignore[assignment]

from .config import Config

log = logging.getLogger(__name__)


@dataclass
class Reply:
    """Ответ агента на одно сообщение."""

    text: str
    tools_used: list[str]
    cost_usd: float | None = None
    error: str | None = None


def build_options(config: Config) -> ClaudeAgentOptions:
    """Опции агента.

    Ключевой момент для подписки: мы не передаём ANTHROPIC_API_KEY.
    SDK запускает Claude Code CLI, а тот берёт OAuth-креды из `claude auth login`.
    """
    kwargs: dict = {
        "system_prompt": {
            "type": "preset",
            "preset": "claude_code",
            "append": config.persona,
        },
        "cwd": str(config.workspace),
        "permission_mode": config.permission_mode,
        "allowed_tools": config.allowed_tools,
        # Подхватываем личные скиллы и память из ~/.claude, но не настройки
        # случайного проекта, в папке которого запущен бот.
        "setting_sources": ["user"],
    }
    if config.model:
        kwargs["model"] = config.model
    if config.max_turns:
        kwargs["max_turns"] = config.max_turns
    if config.max_budget_usd:
        kwargs["max_budget_usd"] = config.max_budget_usd
    return ClaudeAgentOptions(**kwargs)


class JarvisSession:
    """Живая сессия Claude для одного Telegram-чата.

    Контекст сохраняется между сообщениями. Блокировка гарантирует, что
    два сообщения подряд не полезут в одну сессию одновременно.
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._client: ClaudeSDKClient | None = None
        self._lock = asyncio.Lock()

    async def _ensure_client(self) -> ClaudeSDKClient:
        if self._client is None:
            client = ClaudeSDKClient(options=build_options(self._config))
            await client.connect()
            self._client = client
        return self._client

    async def ask(self, prompt: str) -> Reply:
        async with self._lock:
            try:
                client = await self._ensure_client()
                await client.query(prompt)
                return await self._collect(client)
            except Exception as exc:  # noqa: BLE001 — наверх отдаём текстом
                log.exception("Ошибка при обращении к агенту")
                await self.reset()
                return Reply(text="", tools_used=[], error=str(exc))

    async def _collect(self, client: ClaudeSDKClient) -> Reply:
        chunks: list[str] = []
        tools: list[str] = []
        cost: float | None = None

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        chunks.append(block.text)
                    elif ToolUseBlock and isinstance(block, ToolUseBlock):
                        tools.append(block.name)
            elif isinstance(message, ResultMessage):
                cost = getattr(message, "total_cost_usd", None)

        return Reply(text="\n".join(c for c in chunks if c).strip(), tools_used=tools, cost_usd=cost)

    async def interrupt(self) -> bool:
        """Прерывает текущую работу агента. True — если было что прерывать."""
        if self._client is None or not self._lock.locked():
            return False
        try:
            await self._client.interrupt()
            return True
        except Exception:  # noqa: BLE001
            log.exception("Не удалось прервать сессию")
            return False

    async def reset(self) -> None:
        """Закрывает сессию — следующий вопрос начнёт разговор с нуля."""
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                log.exception("Не удалось закрыть сессию")


class SessionRegistry:
    """Сессии по chat_id."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._sessions: dict[int, JarvisSession] = {}

    def get(self, chat_id: int) -> JarvisSession:
        if chat_id not in self._sessions:
            self._sessions[chat_id] = JarvisSession(self._config)
        return self._sessions[chat_id]

    async def reset(self, chat_id: int) -> None:
        session = self._sessions.pop(chat_id, None)
        if session is not None:
            await session.reset()

    async def shutdown(self) -> None:
        for session in list(self._sessions.values()):
            await session.reset()
        self._sessions.clear()
