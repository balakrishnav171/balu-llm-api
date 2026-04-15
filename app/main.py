"""
Balu LLM API — FastAPI application entry point.

Startup order:
1. Logging is configured.
2. LLM service singleton is initialised and warm-up probe is attempted.
3. Routers are already mounted at import time (module-level).

Shutdown:
- The LLM service is torn down gracefully.
"""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import setup_logging
from app.routers import chat as chat_router
from app.routers import health as health_router
from app.services.llm_service import get_llm_service, reset_llm_service

# ---------------------------------------------------------------------------
# Logging — must be first so all subsequent imports can log
# ---------------------------------------------------------------------------
setup_logging(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown."""
    # ---- Startup ----
    logger.info(
        "Starting %s v%s (backend=%s)",
        settings.APP_TITLE,
        settings.APP_VERSION,
        settings.LLM_BACKEND,
    )

    try:
        svc = get_llm_service()
        logger.info(
            "LLM service initialised",
            extra={"model": svc.model_name, "backend": svc.backend},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to initialise LLM service: %s — the API will start but "
            "/v1/chat will be unavailable until the backend is reachable.",
            exc,
            exc_info=True,
        )

    yield  # Application is running

    # ---- Shutdown ----
    logger.info("Shutting down %s", settings.APP_TITLE)
    reset_llm_service(None)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title=settings.APP_TITLE,
        version=settings.APP_VERSION,
        description=settings.APP_DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ----------------------------------------------------------------
    # CORS middleware
    # ----------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ----------------------------------------------------------------
    # Request-ID middleware (adds X-Request-Id to every response)
    # ----------------------------------------------------------------
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):  # type: ignore[return]
        request_id = request.headers.get("X-Request-Id", uuid.uuid4().hex)
        logger.debug(
            "Incoming request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            },
        )
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    # ----------------------------------------------------------------
    # Global exception handlers
    # ----------------------------------------------------------------
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning("Validation error: %s", exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors(), "error_type": "validation_error"},
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An unexpected internal error occurred.",
                "error_type": type(exc).__name__,
            },
        )

    # ----------------------------------------------------------------
    # Routers
    # ----------------------------------------------------------------
    app.include_router(health_router.router)
    app.include_router(chat_router.router)

    # ----------------------------------------------------------------
    # Root redirect
    # ----------------------------------------------------------------
    @app.get("/", include_in_schema=False)
    async def root() -> JSONResponse:
        return JSONResponse(
            {
                "message": f"Welcome to {settings.APP_TITLE}",
                "version": settings.APP_VERSION,
                "docs": "/docs",
                "health": "/health",
            }
        )

    return app


# ---------------------------------------------------------------------------
# Application instance (used by uvicorn / gunicorn)
# ---------------------------------------------------------------------------
app = create_app()


# ---------------------------------------------------------------------------
# Dev runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_config=None,  # We manage logging ourselves
    )
