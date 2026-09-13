"""Transformation job monitoring and inspection tool for Limo Agent Infrastructure."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from ..contracts import BaseTool, ToolResult, PermissionType
from ..context import AgentContext
from ...services.job_service import JobService, job_service
from ...exceptions import EntityNotFoundError, InvalidStateError


class JobArgs(BaseModel):
    action: str = Field(description="Action to perform: 'get_job', 'list_jobs', or 'cancel_job'")
    job_id: Optional[str] = Field(default=None, description="Job ID (required for 'get_job' and 'cancel_job')")
    project_id: Optional[str] = Field(default=None, description="Project ID (for filtering in 'list_jobs')")
    limit: Optional[int] = Field(default=10, description="Max jobs to return in 'list_jobs'")


class JobTool(BaseTool):
    """Monitor, inspect, or cancel transformation jobs."""

    name: str = "job_tool"
    description: str = "Query status, progress, and stages of transformation jobs."
    permission_type: PermissionType = PermissionType.READ

    def __init__(self, service: Optional[JobService] = None) -> None:
        self.service = service or job_service

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return JobArgs.model_json_schema()

    async def execute(self, args: Dict[str, Any], context: Optional[AgentContext] = None) -> ToolResult:
        try:
            parsed = JobArgs(**args)
        except Exception as e:
            return ToolResult.fail(f"Invalid arguments for job_tool: {str(e)}")

        if parsed.action == "get_job":
            if not parsed.job_id:
                return ToolResult.fail("Missing required 'job_id'")
            try:
                job = self.service.get_job(parsed.job_id)
                return ToolResult.ok({
                    "id": job.id,
                    "state": job.state.value if hasattr(job.state, "value") else str(job.state),
                    "progress": job.progress,
                    "current_stage": job.current_stage,
                    "requested_formats": [f.value if hasattr(f, "value") else str(f) for f in job.requested_formats],
                    "error": job.error,
                    "created_at": job.created_at.isoformat() if job.created_at else None,
                })
            except EntityNotFoundError:
                return ToolResult.fail(f"Job '{parsed.job_id}' not found")

        elif parsed.action == "list_jobs":
            project_id = parsed.project_id or (context.project_id if context else None)
            jobs = self.service.list_jobs(project_id=project_id, limit=parsed.limit)
            summaries = [
                {
                    "id": j.id,
                    "state": j.state.value if hasattr(j.state, "value") else str(j.state),
                    "progress": j.progress,
                    "current_stage": j.current_stage,
                    "requested_formats": [f.value if hasattr(f, "value") else str(f) for f in j.requested_formats],
                }
                for j in jobs
            ]
            return ToolResult.ok({"jobs": summaries, "count": len(summaries)})

        elif parsed.action == "cancel_job":
            if not parsed.job_id:
                return ToolResult.fail("Missing required 'job_id'")
            try:
                cancelled = self.service.cancel_job(parsed.job_id)
                return ToolResult.ok({"id": cancelled.id, "state": cancelled.state.value, "cancelled": True})
            except (EntityNotFoundError, InvalidStateError) as e:
                return ToolResult.fail(str(e))

        else:
            return ToolResult.fail(f"Unknown action '{parsed.action}'. Supported: 'get_job', 'list_jobs', 'cancel_job'")
