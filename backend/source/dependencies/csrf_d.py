from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from source.db.config import get_cors_allow_origins

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
EXEMPT_PATHS = {
    "/payments/webhook/mercadopago",
    # Server-to-server maintenance trigger (external cron ping). It carries no
    # browser Origin/Referer; it is authenticated by a bearer token instead.
    "/internal/maintenance/run",
}


def _normalize_origin(raw: str) -> str:
    value = str(raw or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return value


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method.upper() not in UNSAFE_METHODS:
            return await call_next(request)
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        allowed = {_normalize_origin(origin) for origin in get_cors_allow_origins()}
        origin = _normalize_origin(request.headers.get("origin", ""))
        if origin and origin in allowed:
            return await call_next(request)

        referer = request.headers.get("referer", "")
        referer_origin = _normalize_origin(referer)
        if referer_origin and referer_origin in allowed:
            return await call_next(request)

        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "csrf origin check failed"},
        )
