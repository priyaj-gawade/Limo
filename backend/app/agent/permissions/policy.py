"""Granular permission enforcement and interactive human-in-the-loop approval management."""

from datetime import datetime, timezone
from enum import StrEnum
import logging
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from ..contracts import BaseTool, PermissionType

logger = logging.getLogger("limo.agent.permissions")


class UnauthorizedActionError(Exception):
    """Raised when an agent turn attempts an action exceeding its granted permissions."""
    pass


class ApprovalStatus(StrEnum):
    """Status lifecycle of an approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalRequest(BaseModel):
    """Container tracking an action paused waiting for human authorization."""
    approval_id: str = Field(default_factory=lambda: f"appr_{uuid.uuid4().hex[:12]}")
    session_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    reason: str = "High-impact action requires user confirmation"
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    resolution_comment: Optional[str] = None


class PermissionPolicy:
    """Configurable policy defining auto-allowed, restricted, and approval-requiring capabilities."""

    def __init__(
        self,
        auto_allowed: Optional[List[PermissionType]] = None,
        requires_approval: Optional[List[PermissionType]] = None,
        blocked: Optional[List[PermissionType]] = None,
    ):
        self.auto_allowed = auto_allowed or [PermissionType.READ, PermissionType.TRANSFORM]
        self.requires_approval = requires_approval or [
            PermissionType.WRITE,
            PermissionType.EXTERNAL_DISPATCH,
        ]
        self.blocked = blocked or [PermissionType.EXECUTE]

    def check_permission(self, permission: PermissionType) -> str:
        """Evaluate permission. Returns 'allow', 'requires_approval', or raises UnauthorizedActionError."""
        if permission in self.blocked:
            raise UnauthorizedActionError(f"Permission '{permission.value}' is explicitly blocked by policy")
        if permission in self.auto_allowed:
            return "allow"
        if permission in self.requires_approval:
            return "requires_approval"
        raise UnauthorizedActionError(f"Permission '{permission.value}' is unhandled and not authorized")


class ApprovalManager:
    """Manages the concrete resume mechanism for WAITING_APPROVAL state machine."""

    def __init__(self):
        self._requests: Dict[str, ApprovalRequest] = {}

    def request_approval(
        self,
        session_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        reason: Optional[str] = None,
    ) -> ApprovalRequest:
        """Create and store a pending approval request."""
        req = ApprovalRequest(
            session_id=session_id,
            tool_name=tool_name,
            arguments=arguments,
            reason=reason or f"Invocation of '{tool_name}' requires confirmation",
        )
        self._requests[req.approval_id] = req
        logger.info(
            "Created approval request %s for session %s (tool: %s)",
            req.approval_id,
            session_id,
            tool_name,
        )
        return req

    def get_approval(self, approval_id: str) -> Optional[ApprovalRequest]:
        """Retrieve approval request by ID."""
        return self._requests.get(approval_id)

    def approve(self, approval_id: str, comment: Optional[str] = None) -> ApprovalRequest:
        """Mark request APPROVED to resume the exact paused action."""
        req = self._requests.get(approval_id)
        if not req:
            raise KeyError(f"Approval request '{approval_id}' not found")
        if req.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval request '{approval_id}' is already {req.status.value}")

        req.status = ApprovalStatus.APPROVED
        req.resolved_at = datetime.now(timezone.utc)
        req.resolution_comment = comment or "Approved by user"
        logger.info("Approved action %s for tool %s", approval_id, req.tool_name)
        return req

    def reject(self, approval_id: str, reason: Optional[str] = None) -> ApprovalRequest:
        """Mark request REJECTED to cancel the paused action."""
        req = self._requests.get(approval_id)
        if not req:
            raise KeyError(f"Approval request '{approval_id}' not found")
        if req.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval request '{approval_id}' is already {req.status.value}")

        req.status = ApprovalStatus.REJECTED
        req.resolved_at = datetime.now(timezone.utc)
        req.resolution_comment = reason or "Rejected by user"
        logger.info("Rejected action %s for tool %s", approval_id, req.tool_name)
        return req

    def list_pending(self, session_id: Optional[str] = None) -> List[ApprovalRequest]:
        """List all pending approval requests, optionally filtered by session."""
        pending = [r for r in self._requests.values() if r.status == ApprovalStatus.PENDING]
        if session_id:
            pending = [r for r in pending if r.session_id == session_id]
        return pending


class PermissionManager:
    """Coordinates policy checks and approval request lifecycle."""

    def __init__(
        self,
        policy: Optional[PermissionPolicy] = None,
        approval_mgr: Optional[ApprovalManager] = None,
    ):
        self.policy = policy or PermissionPolicy()
        self.approval_mgr = approval_mgr or ApprovalManager()

    def check_tool(self, tool: BaseTool, session_id: str, args: Dict[str, Any]) -> str:
        """Evaluate if tool can run immediately, needs approval, or is blocked."""
        decision = self.policy.check_permission(tool.permission_type)
        return decision
