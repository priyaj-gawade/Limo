"""Domain exceptions and global exception handlers for Limo."""

from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


class LimoException(Exception):
    """Base exception for all Limo application errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "LIMO_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Any] = None,
        resource_id: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details
        self.resource_id = resource_id


class EntityNotFoundError(LimoException):
    """Raised when an entity or resource cannot be located."""

    def __init__(self, entity_name: str, entity_id: str):
        super().__init__(
            message=f"{entity_name} with id '{entity_id}' not found",
            error_code="ENTITY_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"entity": entity_name, "id": entity_id},
            resource_id=entity_id,
        )
        self.entity_name = entity_name


class EntityConflictError(LimoException):
    """Raised when an entity conflict occurs (e.g. duplicate key)."""

    def __init__(self, message: str, details: Optional[Any] = None, resource_id: Optional[str] = None):
        super().__init__(
            message=message,
            error_code="ENTITY_CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            details=details,
            resource_id=resource_id,
        )


class StorageError(LimoException):
    """Raised when an underlying filesystem or storage operation fails."""

    def __init__(self, message: str, details: Optional[Any] = None, resource_id: Optional[str] = None):
        super().__init__(
            message=message,
            error_code="STORAGE_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
            resource_id=resource_id,
        )


class BadRequestError(LimoException):
    """Raised when a client request or parameter is invalid."""

    def __init__(self, message: str, details: Optional[Any] = None, resource_id: Optional[str] = None):
        super().__init__(
            message=message,
            error_code="BAD_REQUEST",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
            resource_id=resource_id,
        )


class InvalidStateError(LimoException):
    """Raised when an entity operation is forbidden in its current lifecycle state."""

    def __init__(self, message: str, details: Optional[Any] = None, resource_id: Optional[str] = None):
        super().__init__(
            message=message,
            error_code="INVALID_STATE",
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
            resource_id=resource_id,
        )


class QueueFullError(LimoException):
    """Raised when the transformation worker queue has reached capacity (429 Backpressure)."""

    def __init__(
        self,
        message: str = "Transformation worker queue is at capacity. Please retry shortly.",
        details: Optional[Any] = None,
        retry_after_sec: int = 5,
    ):
        super().__init__(
            message=message,
            error_code="QUEUE_FULL",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details or {"retry_after_sec": retry_after_sec},
        )


class UnsupportedFormatError(BadRequestError):
    """Raised when an output format is not in the recognized OutputFormat registry."""

    def __init__(self, raw_format: str, supported_formats: list[str]):
        super().__init__(
            message=f"Unsupported deliverable format '{raw_format}'. Supported formats: {supported_formats}",
            details={"requested_format": raw_format, "supported_formats": supported_formats},
        )


class UnimplementedEngineError(LimoException):
    """Raised when an execution dispatch is attempted on an unbuilt engine (D6.3+, D7, D8)."""

    def __init__(self, engine_type: str, target_phase: str):
        super().__init__(
            message=(
                f"Execution engine '{engine_type}' is scheduled for Phase {target_phase} "
                f"and is not yet available in Phase D6. Zero fake artifacts will be generated."
            ),
            error_code="UNIMPLEMENTED_ENGINE",
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            details={"engine_type": engine_type, "target_phase": target_phase},
        )


def _extract_request_id(request: Request) -> Optional[str]:
    """Extract validated request correlation ID from request state, contextvar, or header."""
    state_id = getattr(getattr(request, "state", None), "request_id", None)
    if state_id:
        return state_id
    try:
        from .core.middleware import current_request_id
        ctx_id = current_request_id.get()
        if ctx_id:
            return ctx_id
    except Exception:
        pass
    return request.headers.get("X-Request-ID")


async def limo_exception_handler(request: Request, exc: LimoException) -> JSONResponse:
    """Handle custom Limo domain exceptions with structured error payload."""
    request_id = _extract_request_id(request)
    payload = {
        "error": {
            "code": exc.error_code,
            "message": exc.message,
            "status": exc.status_code,
            "request_id": request_id,
            "resource_id": exc.resource_id,
            "details": exc.details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }
    return JSONResponse(status_code=exc.status_code, content=payload)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle request payload validation errors cleanly."""
    request_id = _extract_request_id(request)
    payload = {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request body or parameter validation failed",
            "status": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "request_id": request_id,
            "resource_id": None,
            "details": exc.errors(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=payload)


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all fallback exception handler for unexpected server errors.
    
    Logs the full exception and traceback internally while keeping the client
    response sanitized to avoid exposing internal server details.
    """
    import logging
    logger = logging.getLogger("limo.error")
    request_id = _extract_request_id(request)
    logger.error(
        "Unhandled internal server error [request_id=%s]: %s",
        request_id,
        exc,
        exc_info=True,
    )

    payload = {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An internal server error occurred.",
            "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "request_id": request_id,
            "resource_id": None,
            "details": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload)
