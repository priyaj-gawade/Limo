"""Unit tests for Phase D6.5 Transformation Lifecycle Event Models and Sanitization."""

import json
import pytest
from app.models.enums import OutputFormat
from app.models.transformation_events import (
    TransformationEventType,
    TransformationLifecycleEvent,
)
from app.services.transformation.event_broker import sanitize_public_payload


def test_transformation_event_type_enumeration():
    """Verify all required D6.5 lifecycle event types are present and uniquely identified."""
    expected_types = {
        "job.created",
        "job.started",
        "task.started",
        "task.completed",
        "task.failed",
        "artifact.created",
        "job.completed",
        "job.waiting_external",
        "job.partially_completed",
        "job.failed",
        "job.cancelled",
    }
    actual_types = {e.value for e in TransformationEventType}
    assert expected_types.issubset(actual_types)


def test_transformation_lifecycle_event_creation_and_fields():
    """Verify event model structure, timestamp format, and sequence numbering."""
    event = TransformationLifecycleEvent(
        event_id="evt_01test00000000000000000001",
        job_id="job_01test00000000000000000002",
        event_type=TransformationEventType.TASK_STARTED,
        sequence=3,
        payload={"deliverable_id": "deliv_1", "format": OutputFormat.MARKDOWN.value},
    )

    assert event.event_id.startswith("evt_")
    assert event.id == event.event_id
    assert event.job_id.startswith("job_")
    assert event.event_type == TransformationEventType.TASK_STARTED
    assert event.sequence == 3
    assert event.payload["format"] == "markdown"
    assert event.timestamp is not None


def test_sanitize_event_payload_scrubs_sensitive_keys():
    """Verify zero-leakage security boundary scrubs API keys, CoT, tracebacks, and secrets."""
    raw_payload = {
        "deliverable_id": "deliv_safe_1",
        "format": "html",
        "api_key": "sk-secret-token-12345",
        "secret": "super_secret_value",
        "system_prompt": "You are an internal system prompt...",
        "chain_of_thought": "Step 1: thinking about secret internal details...",
        "traceback": "Traceback (most recent call last):\nFile 'internal.py'...",
        "password": "my_password",
        "prompt_template": "Template with private instructions",
        "nested": {
            "safe_nested": "ok",
            "api_key": "nested-token",
            "chain_of_thought": "nested thinking",
        },
    }

    sanitized = sanitize_public_payload(raw_payload)

    # Safe keys preserved
    assert sanitized["deliverable_id"] == "deliv_safe_1"
    assert sanitized["format"] == "html"
    assert sanitized["nested"]["safe_nested"] == "ok"

    # Sensitive keys completely stripped
    forbidden_keys = {
        "api_key",
        "secret",
        "system_prompt",
        "chain_of_thought",
        "traceback",
        "password",
        "prompt_template",
    }
    for k in forbidden_keys:
        assert k not in sanitized
        assert k not in sanitized["nested"]


def test_to_sse_frame_formatting():
    """Verify event correctly serializes into a standard Server-Sent Events (SSE) wire frame."""
    event = TransformationLifecycleEvent(
        event_id="evt_01test00000000000000000003",
        job_id="job_01test00000000000000000004",
        event_type=TransformationEventType.ARTIFACT_CREATED,
        sequence=5,
        payload={"artifact_id": "art_123", "size_bytes": 450},
    )

    sse_frame = event.to_sse_frame()
    lines = sse_frame.strip().split("\n")

    assert lines[0] == f"id: {event.event_id}"
    assert lines[1] == "event: artifact.created"
    assert lines[2].startswith("data: ")

    # Verify data line is valid JSON representing the event model
    data_json = json.loads(lines[2][len("data: "):])
    assert data_json["event_id"] == event.event_id
    assert data_json["job_id"] == event.job_id
    assert data_json["event_type"] == "artifact.created"
    assert data_json["sequence"] == 5
    assert data_json["payload"]["artifact_id"] == "art_123"
