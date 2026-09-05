"""Optional API-key auth + simple per-key rate limit (default off)."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from sniper_quant.config import Settings

OPEN_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})


class ApiKeyRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in OPEN_PATHS or path.startswith("/docs") or request.scope["type"] == "websocket":
            return await call_next(request)
        key_required = bool(self.settings.api_key)
        presented = request.headers.get("x-api-key") or request.headers.get("X-API-Key")
        if key_required and presented != self.settings.api_key:
            return JSONResponse({"detail": "invalid or missing X-API-Key"}, status_code=401)
        limit = int(self.settings.rate_limit_per_min or 0)
        if limit > 0:
            bucket = presented or (request.client.host if request.client else "anon")
            now = time.time()
            window = [t for t in self._hits[bucket] if now - t < 60.0]
            if len(window) >= limit:
                return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
            window.append(now)
            self._hits[bucket] = window
        return await call_next(request)
