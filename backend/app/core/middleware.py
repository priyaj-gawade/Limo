"""Request correlation and diagnostics middleware for Limo Backend."""

from contextvars import ContextVar
import logging
import re
import time
from typing import Optional
import uuid
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("limo.access")

# Context variable to propagate request_id across async call stacks
current_request_id: ContextVar[Optional[str]] = ContextVar("current_request_id", default=None)

# Validation regex for incoming X-Request-ID headers (4-64 alphanumeric, dash, underscore, dot, colon)
REQUEST_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.:]{4,64}$")


def validate_request_id(req_id: Optional[str]) -> Optional[str]:
    """Validate incoming request ID format against safe pattern.
    
    Rejects overly long strings, invalid characters, or injection attempts.
    Returns the sanitized string if valid, or None if invalid.
    """
    if not req_id or not isinstance(req_id, str):
        return None
    cleaned = req_id.strip()
    if REQUEST_ID_REGEX.match(cleaned):
        return cleaned
    return None


class RequestDiagnosticsMiddleware(BaseHTTPMiddleware):
    """Middleware attaching a validated request correlation ID to state, context, and headers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming_header = request.headers.get("X-Request-ID")
        valid_id = validate_request_id(incoming_header)

        # Fallback to generated ID if missing or invalid
        request_id = valid_id if valid_id else f"req_{uuid.uuid4().hex[:16]}"

        request.state.request_id = request_id
        token = current_request_id.set(request_id)
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            response.headers["X-Request-ID"] = request_id

            logger.info(
                "request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
                request_id,
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
            return response
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "request_id=%s method=%s path=%s status=500 duration_ms=%.2f error=%s",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
                str(exc),
                exc_info=True,
            )
            raise
        finally:
            # Guarantee ContextVar cleanup across async task boundaries
            current_request_id.reset(token)
