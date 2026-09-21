"""Shared repository helpers for dialect-neutral data parsing."""

from datetime import datetime
import json
from typing import Any, Optional


def parse_dt(val: Any) -> Optional[datetime]:
    """Parse a datetime from either an ISO string or a native datetime object."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    return datetime.fromisoformat(str(val))


def parse_json(val: Any, default: Any = None) -> Any:
    """Parse JSON from either a raw string or an already deserialized dict/list."""
    if val is None:
        return default if default is not None else {}
    if isinstance(val, (dict, list)):
        return val
    return json.loads(str(val))
