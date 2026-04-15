"""
Health-check router.

GET /health — no authentication required.
Returns the overall status of the service, including whether the LLM backend
is reachable.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.schemas.chat import HealthResponse
from app.services.llm_service import LLMService, get_llm_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description=(
        "Returns the current health of the API and whether the configured "
        "LLM backend is reachable.  No API key required."
    ),
    responses={
        200: {"description": "Service is healthy or degraded"},
        503: {"description": "Service is in an error state"},
    },
)
async def health_check(llm_service: LLMService = Depends(get_llm_service)) -> JSONResponse:
    """
    Ping the LLM backend and report overall health.

    Status values:
    - **ok** — everything is running normally
    - **degraded** — API is up but LLM backend is unreachable
    - **error** — unexpected exception during health check
    """

    try:
        llm_reachable = await llm_service.ping()
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error during health ping: %s", exc, exc_info=True)
        payload = HealthResponse(
            status="error",
            model=llm_service.model_name,
            backend=llm_service.backend,
            version=settings.APP_VERSION,
            llm_reachable=False,
        )
        return JSONResponse(
            content=payload.model_dump(),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    overall_status = "ok" if llm_reachable else "degraded"
    http_status = status.HTTP_200_OK

    logger.info(
        "Health check complete",
        extra={
            "status": overall_status,
            "llm_reachable": llm_reachable,
            "backend": llm_service.backend,
        },
    )

    payload = HealthResponse(
        status=overall_status,
        model=llm_service.model_name,
        backend=llm_service.backend,
        version=settings.APP_VERSION,
        llm_reachable=llm_reachable,
    )
    return JSONResponse(content=payload.model_dump(), status_code=http_status)
