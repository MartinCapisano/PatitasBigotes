from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from source.db.config import get_auth_cookie_secure

# Swagger/Redoc load their assets from a CDN, so a strict CSP would break them visually.
DOC_PATHS = {"/docs", "/redoc", "/openapi.json"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.url.path not in DOC_PATHS:
            response.headers.setdefault(
                "Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'"
            )
        if get_auth_cookie_secure():
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response
