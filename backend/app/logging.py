"""Logging configuration and diagnostics for Limo Backend."""

import logging
import sys
from typing import Any, Dict, List, Optional, Set, Union
from .config import settings

# Explicit sensitive key set to avoid broad false-positive masking (e.g. "keywords", "key_findings")
EXPLICIT_SENSITIVE_KEYS: Set[str] = {
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "auth_token",
    "authorization",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "credential",
    "credentials",
    "cookie",
    "cookies",
    "token",
    "private_key",
}

SENSITIVE_SUFFIXES = ("_api_key", "_token", "_secret", "_password", "_credential")
SENSITIVE_PREFIXES = ("api_key_", "auth_")


def is_sensitive_key(key: str) -> bool:
    """Check if a dictionary key represents sensitive credentials or secrets."""
    if not isinstance(key, str):
        return False
    lower_key = key.lower().strip()
    if lower_key in EXPLICIT_SENSITIVE_KEYS:
        return True
    if lower_key.endswith(SENSITIVE_SUFFIXES):
        return True
    if lower_key.startswith(SENSITIVE_PREFIXES):
        return True
    return False


def mask_sensitive_data(data: Any) -> Any:
    """Recursively mask sensitive values in dictionaries and lists.
    
    Preserves general keys like 'keywords', 'key_points', or 'primary_key'.
    """
    if isinstance(data, dict):
        masked: Dict[str, Any] = {}
        for k, v in data.items():
            if is_sensitive_key(str(k)):
                masked[k] = "***REDACTED***"
            else:
                masked[k] = mask_sensitive_data(v)
        return masked
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(mask_sensitive_data(item) for item in data)
    return data


def log_operation(
    logger: logging.Logger,
    service: str,
    operation: str,
    status: str,
    error: Optional[str] = None,
    resource_id: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """Record a structured operational log entry for diagnostics.
    
    Format:
    [request_id] [service:operation] status=<status> [resource_id=<id>] [error=<error>] [extra_keys]
    """
    try:
        from .core.middleware import current_request_id
        req_id = current_request_id.get() or "-"
    except Exception:
        req_id = "-"

    parts = [f"[{req_id}]", f"[{service}:{operation}]", f"status={status}"]
    if resource_id:
        parts.append(f"resource_id={resource_id}")
    if error:
        parts.append(f"error='{error}'")

    if kwargs:
        sanitized = mask_sensitive_data(kwargs)
        for k, v in sanitized.items():
            parts.append(f"{k}={v}")

    log_msg = " ".join(parts)
    if status.lower() in ("failed", "error"):
        logger.error(log_msg)
    elif status.lower() in ("warn", "warning"):
        logger.warning(log_msg)
    else:
        logger.info(log_msg)


def setup_logging() -> None:
    """Configure structured logging for development and production."""
    log_format = (
        "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
        if settings.debug
        else "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    # Suppress excessive verbosity from noisy 3rd party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
