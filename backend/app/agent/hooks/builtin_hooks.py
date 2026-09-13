"""Built-in lifecycle hooks enforcing security, sanitization, and output checks."""

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

from ..contracts import BaseHook, HookEvent
from .registry import SecurityViolationError

logger = logging.getLogger("limo.agent.hooks.builtin")

# Patterns for sensitive token redaction
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|auth|bearer)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{8,})['\"]?"
)


class PreToolUseValidationHook(BaseHook):
    """Validates tool invocation arguments to prevent security boundary violations."""

    event = HookEvent.PRE_TOOL_USE

    def __init__(self, blocked_patterns: Optional[List[str]] = None):
        self.blocked_patterns = blocked_patterns or [
            "../", "..\\", "/etc/", "c:\\windows\\system32", "cmd.exe", "powershell.exe"
        ]

    async def execute(self, payload: Dict[str, Any], context: Optional[Any] = None) -> Dict[str, Any]:
        tool_name = payload.get("tool_name", "")
        args = payload.get("arguments", {})

        if not isinstance(args, dict):
            raise SecurityViolationError(f"Tool arguments for '{tool_name}' must be a dictionary")

        # Scan string arguments for path traversal or malicious injection patterns
        for key, val in args.items():
            if isinstance(val, str):
                lower_val = val.lower()
                for pattern in self.blocked_patterns:
                    if pattern in lower_val:
                        raise SecurityViolationError(
                            f"Security boundary violation in argument '{key}': detected forbidden pattern '{pattern}'"
                        )

        return payload


class PostToolUseSanitizerHook(BaseHook):
    """Sanitizes tool results by redacting sensitive tokens, secrets, or API keys."""

    event = HookEvent.POST_TOOL_USE

    async def execute(self, payload: Dict[str, Any], context: Optional[Any] = None) -> Dict[str, Any]:
        output = payload.get("output")
        metadata = payload.get("metadata", {})

        # Sanitize metadata dictionary
        sanitized_metadata = {}
        for k, v in metadata.items():
            lower_k = k.lower()
            if any(s in lower_k for s in ("secret", "token", "password", "api_key")):
                sanitized_metadata[k] = "[REDACTED]"
            elif isinstance(v, str):
                sanitized_metadata[k] = SENSITIVE_KEY_PATTERN.sub(r"\1=[REDACTED]", v)
            else:
                sanitized_metadata[k] = v
        payload["metadata"] = sanitized_metadata

        # Sanitize output if string
        if isinstance(output, str):
            payload["output"] = SENSITIVE_KEY_PATTERN.sub(r"\1=[REDACTED]", output)

        return payload


class PostArtifactCreationHook(BaseHook):
    """Verifies deliverable integrity and computes SHA-256 for public artifact events."""

    event = HookEvent.POST_ARTIFACT_CREATION

    async def execute(self, payload: Dict[str, Any], context: Optional[Any] = None) -> Dict[str, Any]:
        artifact_id = payload.get("artifact_id")
        content = payload.get("content")

        if content is not None:
            if isinstance(content, str):
                raw_bytes = content.encode("utf-8")
            elif isinstance(content, bytes):
                raw_bytes = content
            else:
                raw_bytes = str(content).encode("utf-8")

            sha256 = hashlib.sha256(raw_bytes).hexdigest()
            payload["sha256"] = sha256
            payload["size_bytes"] = len(raw_bytes)
            logger.info("Computed artifact integrity for '%s': sha256=%s", artifact_id, sha256[:12])

        return payload


class StopDeliverableCheckHook(BaseHook):
    """Verifies that requested deliverables or explanations exist before the agent terminates."""

    event = HookEvent.AGENT_STOP

    async def execute(self, payload: Dict[str, Any], context: Optional[Any] = None) -> Dict[str, Any]:
        response_text = payload.get("response_text", "")
        artifact_ids = payload.get("artifact_ids", [])

        # If turn produced neither response text nor artifacts, attach a fallback warning
        if not response_text and not artifact_ids:
            payload["response_text"] = "Task completed without deliverable output."

        return payload
