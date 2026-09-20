"""Stable domain ID generators with human-readable prefixes."""

import uuid


def generate_id(prefix: str, length: int = 16) -> str:
    """Generate a stable, unique ID prefixed with the domain entity identifier."""
    unique_hex = uuid.uuid4().hex[:length]
    return f"{prefix}_{unique_hex}"


def generate_project_id() -> str:
    return generate_id("proj")


def generate_source_id() -> str:
    return generate_id("src")


def generate_chat_id() -> str:
    return generate_id("chat")


def generate_message_id() -> str:
    return generate_id("msg")


def generate_job_id() -> str:
    return generate_id("job")


def generate_canonical_id() -> str:
    return generate_id("can")


def generate_artifact_id() -> str:
    return generate_id("art")


def generate_version_id() -> str:
    return generate_id("ver")


def generate_validation_id() -> str:
    return generate_id("val")


def generate_provenance_id() -> str:
    return generate_id("prov")


def generate_request_id() -> str:
    return generate_id("req")


def generate_deliverable_id() -> str:
    return generate_id("del")


def generate_plan_id() -> str:
    return generate_id("plan")


def generate_workflow_id() -> str:
    return generate_id("wf")


def generate_task_id() -> str:
    return generate_id("task")


def generate_event_id() -> str:
    return generate_id("evt")


def generate_user_id() -> str:
    return generate_id("usr")


# Backward compatibility alias
generate_prefixed_id = generate_id

