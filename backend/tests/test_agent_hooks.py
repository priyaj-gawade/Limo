"""Unit tests for Phase D4.4: HookRegistry and builtin lifecycle interceptors."""

import pytest
from app.agent.contracts import HookEvent
from app.agent.hooks.builtin_hooks import (
    PostArtifactCreationHook,
    PostToolUseSanitizerHook,
    PreToolUseValidationHook,
    StopDeliverableCheckHook,
)
from app.agent.hooks.registry import HookRegistry, SecurityViolationError


@pytest.mark.asyncio
async def test_hook_registration_and_trigger():
    registry = HookRegistry()
    hook = PreToolUseValidationHook()
    registry.register_hook(hook)

    assert len(registry.list_hooks(HookEvent.PRE_TOOL_USE)) == 1
    assert len(registry.list_hooks(HookEvent.AGENT_STOP)) == 0

    # Normal argument payload passes cleanly
    payload = {"tool_name": "source_read", "arguments": {"source_id": "src_123"}}
    result = await registry.trigger(HookEvent.PRE_TOOL_USE, payload)
    assert result["arguments"]["source_id"] == "src_123"


@pytest.mark.asyncio
async def test_pre_tool_use_validation_blocks_path_traversal():
    registry = HookRegistry()
    registry.register_hook(PreToolUseValidationHook())

    # Path traversal argument triggers SecurityViolationError
    malicious_payload = {
        "tool_name": "storage_tool",
        "arguments": {"file_path": "../../../etc/passwd"},
    }
    with pytest.raises(SecurityViolationError) as exc_info:
        await registry.trigger(HookEvent.PRE_TOOL_USE, malicious_payload)
    assert "Security boundary violation" in str(exc_info.value)


@pytest.mark.asyncio
async def test_post_tool_use_sanitizer_redacts_tokens():
    registry = HookRegistry()
    registry.register_hook(PostToolUseSanitizerHook())

    payload = {
        "tool_name": "external_api",
        "output": "Connected with api_key=FAKE_TEST_API_KEY_FOR_TESTING_PURPOSES_ONLY_12345",
        "metadata": {
            "token": "secret_session_token_12345",
            "status": "ok",
        },
    }
    sanitized = await registry.trigger(HookEvent.POST_TOOL_USE, payload)
    assert "[REDACTED]" in sanitized["output"]
    assert sanitized["metadata"]["token"] == "[REDACTED]"
    assert sanitized["metadata"]["status"] == "ok"


@pytest.mark.asyncio
async def test_post_artifact_creation_computes_sha256():
    registry = HookRegistry()
    registry.register_hook(PostArtifactCreationHook())

    payload = {
        "artifact_id": "art_123",
        "content": "Report summary content for quarterly earnings.",
    }
    result = await registry.trigger(HookEvent.POST_ARTIFACT_CREATION, payload)
    assert "sha256" in result
    assert result["size_bytes"] == len("Report summary content for quarterly earnings.")
    assert len(result["sha256"]) == 64


@pytest.mark.asyncio
async def test_stop_deliverable_check_hook():
    registry = HookRegistry()
    registry.register_hook(StopDeliverableCheckHook())

    payload = {"response_text": "", "artifact_ids": []}
    result = await registry.trigger(HookEvent.AGENT_STOP, payload)
    assert "Task completed without deliverable output" in result["response_text"]
