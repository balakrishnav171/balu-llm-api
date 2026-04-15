"""
LLM service layer.

Wraps LangChain's ChatOllama (local) and AzureChatOpenAI (cloud) behind a
uniform interface so the rest of the application never needs to know which
backend is active.
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator, List, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from app.core.config import settings
from app.schemas.chat import ChatMessage

logger = logging.getLogger(__name__)


def _to_langchain_messages(messages: List[ChatMessage]) -> List[BaseMessage]:
    """Convert our schema ChatMessage list into LangChain message objects."""
    lc_messages: List[BaseMessage] = []
    for msg in messages:
        if msg.role == "system":
            lc_messages.append(SystemMessage(content=msg.content))
        elif msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            lc_messages.append(AIMessage(content=msg.content))
        else:
            # Fallback: treat unknown roles as human turns
            logger.warning("Unknown message role '%s'; treating as 'user'", msg.role)
            lc_messages.append(HumanMessage(content=msg.content))
    return lc_messages


class LLMService:
    """
    Unified LLM service.

    Instantiate once at startup and reuse for the lifetime of the process.
    """

    def __init__(
        self,
        backend: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> None:
        self._backend = backend or settings.LLM_BACKEND
        self._max_tokens = max_tokens if max_tokens is not None else settings.MAX_TOKENS
        self._temperature = temperature if temperature is not None else settings.TEMPERATURE
        self._llm = self._build_llm()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_llm(self):  # type: ignore[return]
        """Initialise and return the appropriate LangChain chat model."""
        if self._backend == "ollama":
            return self._build_ollama()
        if self._backend == "azure_openai":
            return self._build_azure_openai()
        raise ValueError(
            f"Unknown LLM_BACKEND '{self._backend}'. "
            "Valid choices: 'ollama', 'azure_openai'."
        )

    def _build_ollama(self):
        """Build a ChatOllama instance."""
        try:
            from langchain_ollama import ChatOllama  # type: ignore[import]
        except ImportError:
            from langchain_community.chat_models import ChatOllama  # type: ignore[import]

        logger.info(
            "Initialising Ollama backend",
            extra={
                "model": settings.OLLAMA_MODEL,
                "base_url": settings.OLLAMA_BASE_URL,
            },
        )
        return ChatOllama(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=self._temperature,
            num_predict=self._max_tokens,
        )

    def _build_azure_openai(self):
        """Build an AzureChatOpenAI instance."""
        from langchain_openai import AzureChatOpenAI  # type: ignore[import]

        if not settings.AZURE_OPENAI_ENDPOINT or not settings.AZURE_OPENAI_KEY:
            raise RuntimeError(
                "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY must be set "
                "when LLM_BACKEND=azure_openai."
            )

        logger.info(
            "Initialising Azure OpenAI backend",
            extra={
                "deployment": settings.AZURE_OPENAI_DEPLOYMENT,
                "endpoint": settings.AZURE_OPENAI_ENDPOINT,
            },
        )
        return AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            azure_deployment=settings.AZURE_OPENAI_DEPLOYMENT,
            openai_api_key=settings.AZURE_OPENAI_KEY,
            openai_api_version=settings.AZURE_OPENAI_API_VERSION,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        """Return a human-readable model identifier."""
        if self._backend == "ollama":
            return settings.OLLAMA_MODEL
        return settings.AZURE_OPENAI_DEPLOYMENT

    @property
    def backend(self) -> str:
        return self._backend

    async def chat(
        self,
        messages: List[ChatMessage],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """
        Send a chat request and return the full response text.

        Parameters
        ----------
        messages:
            Conversation history.
        max_tokens / temperature:
            Per-request overrides; fall back to instance defaults.
        """
        lc_messages = _to_langchain_messages(messages)

        # Build an ephemeral LLM with overridden params if needed
        llm = self._maybe_override_llm(max_tokens, temperature)

        logger.debug(
            "Sending chat request",
            extra={"backend": self._backend, "n_messages": len(lc_messages)},
        )

        # LangChain's ainvoke is async
        response = await llm.ainvoke(lc_messages)
        content: str = response.content if hasattr(response, "content") else str(response)
        logger.debug("Chat response received", extra={"length": len(content)})
        return content

    async def stream(
        self,
        messages: List[ChatMessage],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream response tokens as an async generator.

        Yields individual text chunks as they arrive from the model.
        """
        lc_messages = _to_langchain_messages(messages)
        llm = self._maybe_override_llm(max_tokens, temperature)

        logger.debug(
            "Starting streaming chat",
            extra={"backend": self._backend, "n_messages": len(lc_messages)},
        )

        async for chunk in llm.astream(lc_messages):
            text = chunk.content if hasattr(chunk, "content") else str(chunk)
            if text:
                yield text

    async def ping(self) -> bool:
        """
        Check whether the configured LLM backend is reachable.

        Returns True on success, False on any error.
        """
        try:
            probe_messages = [ChatMessage(role="user", content="ping")]
            response = await asyncio.wait_for(
                self.chat(probe_messages),
                timeout=10.0,
            )
            return bool(response)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "LLM ping failed",
                extra={"backend": self._backend, "error": str(exc)},
            )
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _maybe_override_llm(
        self,
        max_tokens: Optional[int],
        temperature: Optional[float],
    ):
        """Return self._llm, or a fresh instance with overridden params."""
        needs_override = (max_tokens is not None and max_tokens != self._max_tokens) or (
            temperature is not None and temperature != self._temperature
        )
        if not needs_override:
            return self._llm

        # Build a lightweight override without touching self
        return LLMService(
            backend=self._backend,
            max_tokens=max_tokens or self._max_tokens,
            temperature=temperature if temperature is not None else self._temperature,
        )._llm


# ---------------------------------------------------------------------------
# Module-level singleton — imported by routers
# ---------------------------------------------------------------------------
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Return (or lazily create) the shared LLMService singleton."""
    global _llm_service  # noqa: PLW0603
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


def reset_llm_service(service: Optional[LLMService] = None) -> None:
    """
    Replace the singleton — used in tests to inject a mock service.

    Call with no argument to clear the singleton so it is recreated on next access.
    """
    global _llm_service  # noqa: PLW0603
    _llm_service = service
