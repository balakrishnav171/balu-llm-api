"""
Pydantic v2 request / response models for the chat API.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single turn in a conversation."""

    role: Literal["system", "user", "assistant"] = Field(
        ...,
        description="Role of the message author: 'system', 'user', or 'assistant'.",
    )
    content: str = Field(..., description="Text content of the message.")

    model_config = {"json_schema_extra": {"example": {"role": "user", "content": "Hello!"}}}


class ChatRequest(BaseModel):
    """Payload for POST /v1/chat."""

    messages: list[ChatMessage] = Field(
        ...,
        min_length=1,
        description="Conversation history.  The last message must be from the user.",
    )
    stream: bool = Field(
        default=False,
        description="If true, stream tokens as Server-Sent Events.",
    )
    max_tokens: Optional[int] = Field(
        default=None,
        ge=1,
        le=32768,
        description="Override the server default for maximum tokens to generate.",
    )
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Sampling temperature override.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "messages": [{"role": "user", "content": "Explain LangChain in one sentence."}],
                "stream": False,
                "max_tokens": 256,
            }
        }
    }


class UsageInfo(BaseModel):
    """Token usage reported by the LLM (best-effort)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    """Payload returned by POST /v1/chat (non-streaming)."""

    id: str = Field(
        default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex}",
        description="Unique identifier for this completion.",
    )
    object: str = "chat.completion"
    message: ChatMessage = Field(..., description="The assistant's reply.")
    model: str = Field(..., description="Model / deployment name used.")
    usage: Dict[str, Any] = Field(
        default_factory=dict,
        description="Token usage statistics.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "chatcmpl-abc123",
                "object": "chat.completion",
                "message": {"role": "assistant", "content": "LangChain is a framework …"},
                "model": "orca-mini",
                "usage": {"prompt_tokens": 12, "completion_tokens": 20, "total_tokens": 32},
            }
        }
    }


class HealthResponse(BaseModel):
    """Payload returned by GET /health."""

    status: Literal["ok", "degraded", "error"] = Field(
        ..., description="Overall health status."
    )
    model: str = Field(..., description="Active model / deployment name.")
    backend: str = Field(..., description="LLM backend in use: 'ollama' or 'azure_openai'.")
    version: str = Field(..., description="Application version string.")
    llm_reachable: bool = Field(
        ..., description="Whether the LLM backend responded to a ping."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "ok",
                "model": "orca-mini",
                "backend": "ollama",
                "version": "1.0.0",
                "llm_reachable": True,
            }
        }
    }


class ErrorResponse(BaseModel):
    """Standard error envelope."""

    detail: str
    error_type: Optional[str] = None
    request_id: Optional[str] = None
