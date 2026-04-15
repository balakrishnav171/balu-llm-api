"""
Chat router.

POST /v1/chat — requires X-API-Key header.

Supports:
- Standard (non-streaming) JSON response
- Server-Sent Events (SSE) streaming when request.stream is True
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.auth import require_api_key
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse, ErrorResponse
from app.services.llm_service import LLMService, get_llm_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["Chat"])


# ---------------------------------------------------------------------------
# Helper: SSE formatting
# ---------------------------------------------------------------------------

def _sse_data(data: dict) -> str:
    """Format a dict as a single SSE 'data: ...' line."""
    return f"data: {json.dumps(data)}\n\n"


def _sse_done() -> str:
    return "data: [DONE]\n\n"


async def _token_stream_generator(
    llm_service: LLMService,
    request: ChatRequest,
    completion_id: str,
) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted chunks from the LLM stream."""
    try:
        async for chunk in llm_service.stream(
            messages=request.messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        ):
            payload = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "delta": {"role": "assistant", "content": chunk},
                "model": llm_service.model_name,
            }
            yield _sse_data(payload)
    except Exception as exc:  # noqa: BLE001
        logger.error("Streaming error: %s", exc, exc_info=True)
        error_payload = {"error": {"message": str(exc), "type": "stream_error"}}
        yield _sse_data(error_payload)
    finally:
        yield _sse_done()


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post(
    "/chat",
    summary="Chat completion",
    description=(
        "Send a list of messages and receive an assistant reply.  "
        "Set `stream=true` to receive tokens progressively via Server-Sent Events."
    ),
    response_model=ChatResponse,
    responses={
        200: {
            "description": "Successful completion (non-streaming)",
            "model": ChatResponse,
        },
        206: {"description": "Streaming response (text/event-stream)"},
        401: {"description": "Missing or invalid API key"},
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
        503: {"description": "LLM backend unavailable"},
    },
)
async def chat_completion(
    chat_request: ChatRequest,
    _api_key: str = Depends(require_api_key),
    llm_service: LLMService = Depends(get_llm_service),
) -> StreamingResponse | JSONResponse:
    """
    Main chat endpoint.

    - **Non-streaming** (`stream=false`, default): returns a `ChatResponse` JSON object.
    - **Streaming** (`stream=true`): returns `text/event-stream` (SSE) where each
      event carries a JSON chunk and the final event is `data: [DONE]`.
    """
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"

    logger.info(
        "Chat request received",
        extra={
            "completion_id": completion_id,
            "stream": chat_request.stream,
            "n_messages": len(chat_request.messages),
            "backend": llm_service.backend,
        },
    )

    # ---------------------------------------------------------------
    # Streaming path
    # ---------------------------------------------------------------
    if chat_request.stream:
        generator = _token_stream_generator(llm_service, chat_request, completion_id)
        return StreamingResponse(
            generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # Disable Nginx buffering
                "X-Completion-Id": completion_id,
            },
            status_code=status.HTTP_200_OK,
        )

    # ---------------------------------------------------------------
    # Non-streaming path
    # ---------------------------------------------------------------
    try:
        response_text = await llm_service.chat(
            messages=chat_request.messages,
            max_tokens=chat_request.max_tokens,
            temperature=chat_request.temperature,
        )
    except ConnectionError as exc:
        logger.error("LLM backend connection error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM backend is unreachable: {exc}",
        ) from exc
    except TimeoutError as exc:
        logger.error("LLM request timed out: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM backend timed out",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected LLM error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM error: {exc}",
        ) from exc

    response = ChatResponse(
        id=completion_id,
        message=ChatMessage(role="assistant", content=response_text),
        model=llm_service.model_name,
        usage={},  # LangChain Community doesn't always expose usage; set to {} for now
    )

    logger.info(
        "Chat response sent",
        extra={
            "completion_id": completion_id,
            "response_length": len(response_text),
        },
    )

    return JSONResponse(
        content=response.model_dump(),
        status_code=status.HTTP_200_OK,
    )
