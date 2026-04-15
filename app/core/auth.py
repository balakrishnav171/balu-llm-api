"""
API key authentication dependency.

Callers must include the header:
    X-API-Key: <value matching settings.API_KEY>

Returns HTTP 401 if the header is missing or the value is wrong.
"""
from __future__ import annotations

import logging

from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import settings

logger = logging.getLogger(__name__)

# OpenAPI security scheme declaration
api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    x_api_key: str | None = Security(api_key_header_scheme),
) -> str:
    """
    FastAPI dependency that validates the X-API-Key header.

    Usage
    -----
    @router.post("/endpoint", dependencies=[Depends(require_api_key)])
    async def my_endpoint(): ...

    Or, if you need the key value in the handler:
    @router.post("/endpoint")
    async def my_endpoint(api_key: str = Depends(require_api_key)): ...
    """
    if not x_api_key:
        logger.warning("Request rejected: X-API-Key header is missing")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header is required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if x_api_key != settings.API_KEY:
        logger.warning("Request rejected: invalid API key provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return x_api_key
