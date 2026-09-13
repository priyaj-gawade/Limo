"""Unit tests for Phase D4.4: Granular permissions and concrete approval resume lifecycle."""

import pytest
from app.agent.contracts import PermissionType
from app.agent.permissions.policy import (
    ApprovalManager,
    ApprovalStatus,
    PermissionManager,
    PermissionPolicy,
    UnauthorizedActionError,
)
from app.agent.tools.source_tool import SourceReadTool, SourceRegisterTool


def test_permission_policy_defaults():
    policy = PermissionPolicy()
    assert policy.check_permission(PermissionType.READ) == "allow"
    assert policy.check_permission(PermissionType.WRITE) == "requires_approval"
    assert policy.check_permission(PermissionType.TRANSFORM) == "allow"

    with pytest.raises(UnauthorizedActionError):
        policy.check_permission(PermissionType.EXECUTE)


def test_approval_lifecycle_resume_and_cancel():
    mgr = ApprovalManager()
    req = mgr.request_approval(
        session_id="sess_123",
        tool_name="source_register",
        arguments={"name": "test.txt", "content": "hello"},
        reason="Writing new source requires approval",
    )

    assert req.status == ApprovalStatus.PENDING
    assert req.approval_id.startswith("appr_")

    # Verify retrieval
    fetched = mgr.get_approval(req.approval_id)
    assert fetched is not None
    assert fetched.tool_name == "source_register"

    # Concrete resume: approve
    approved = mgr.approve(req.approval_id, comment="User confirmed action")
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.resolved_at is not None
    assert approved.resolution_comment == "User confirmed action"

    # Second approval request: reject / cancel
    req2 = mgr.request_approval(
        session_id="sess_123",
        tool_name="transform_contract",
        arguments={"format": "presentation"},
    )
    rejected = mgr.reject(req2.approval_id, reason="User rejected generation")
    assert rejected.status == ApprovalStatus.REJECTED
    assert rejected.resolution_comment == "User rejected generation"


def test_permission_manager_tool_check():
    mgr = PermissionManager()
    read_tool = SourceReadTool()
    write_tool = SourceRegisterTool()

    assert mgr.check_tool(read_tool, "sess_1", {}) == "allow"
    assert mgr.check_tool(write_tool, "sess_1", {"name": "doc.txt"}) == "requires_approval"
