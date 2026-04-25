from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        log = logger.bind(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        log.info("request_started")
        try:
            response = await call_next(request)
        except Exception as exc:
            log.exception("request_failed", error=str(exc))
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            log.info(
                "request_finished",
                status_code=getattr(response, "status_code", None),
                duration_ms=round(duration_ms, 2),
            )

        response.headers["X-Request-ID"] = request_id
        return response
