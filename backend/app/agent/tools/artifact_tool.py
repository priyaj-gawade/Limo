"""Artifact inspection and validation recording tool for Limo Agent Infrastructure."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ..contracts import BaseTool, ToolResult, PermissionType
from ..context import AgentContext
from ...services.artifact_service import ArtifactService, artifact_service
from ...exceptions import EntityNotFoundError


class ArtifactArgs(BaseModel):
    action: str = Field(description="Action: 'get_artifact', 'list_artifacts', or 'record_validation'")
    artifact_id: Optional[str] = Field(default=None, description="Artifact ID (for get_artifact and record_validation)")
    project_id: Optional[str] = Field(default=None, description="Project ID (for filtering in list_artifacts)")
    job_id: Optional[str] = Field(default=None, description="Job ID (for filtering in list_artifacts)")
    # Validation fields
    is_valid: Optional[bool] = Field(default=None, description="Whether artifact passed validation")
    score: Optional[float] = Field(default=None, description="Validation confidence score (0.0 - 1.0)")
    hallucination_check_passed: Optional[bool] = Field(default=True, description="Whether hallucination check passed")
    warnings: Optional[List[str]] = Field(default_factory=list, description="Validation warning strings")
    errors: Optional[List[str]] = Field(default_factory=list, description="Validation error strings")


class ArtifactTool(BaseTool):
    """Query deliverable artifacts and record compliance/validation reports."""

    name: str = "artifact_tool"
    description: str = "Inspect registered deliverables and record validation audits."
    permission_type: PermissionType = PermissionType.READ

    def __init__(self, service: Optional[ArtifactService] = None) -> None:
        self.service = service or artifact_service

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return ArtifactArgs.model_json_schema()

    async def execute(self, args: Dict[str, Any], context: Optional[AgentContext] = None) -> ToolResult:
        try:
            parsed = ArtifactArgs(**args)
        except Exception as e:
            return ToolResult.fail(f"Invalid arguments for artifact_tool: {str(e)}")

        if parsed.action == "get_artifact":
            if not parsed.artifact_id:
                return ToolResult.fail("Missing required 'artifact_id'")
            try:
                art = self.service.get_artifact(parsed.artifact_id)
                return ToolResult.ok({
                    "id": art.id,
                    "title": art.title,
                    "artifact_type": art.artifact_type.value if hasattr(art.artifact_type, "value") else str(art.artifact_type),
                    "file_format": art.file_format,
                    "size_bytes": art.size_bytes,
                    "version": art.version,
                    "validation_status": art.validation_status.value if hasattr(art.validation_status, "value") else str(art.validation_status),
                    "content_hash": art.content_hash,
                    "created_at": art.created_at.isoformat() if art.created_at else None,
                })
            except EntityNotFoundError:
                return ToolResult.fail(f"Artifact '{parsed.artifact_id}' not found")

        elif parsed.action == "list_artifacts":
            project_id = parsed.project_id or (context.project_id if context else None)
            artifacts = self.service.list_artifacts(project_id=project_id, job_id=parsed.job_id)
            summaries = [
                {
                    "id": a.id,
                    "title": a.title,
                    "artifact_type": a.artifact_type.value if hasattr(a.artifact_type, "value") else str(a.artifact_type),
                    "file_format": a.file_format,
                    "size_bytes": a.size_bytes,
                    "version": a.version,
                    "validation_status": a.validation_status.value if hasattr(a.validation_status, "value") else str(a.validation_status),
                }
                for a in artifacts
            ]
            return ToolResult.ok({"artifacts": summaries, "count": len(summaries)})

        elif parsed.action == "record_validation":
            if not parsed.artifact_id:
                return ToolResult.fail("Missing required 'artifact_id' for record_validation")
            if parsed.is_valid is None or parsed.score is None:
                return ToolResult.fail("Missing 'is_valid' or 'score' for record_validation")

            try:
                res = self.service.record_validation_result(
                    artifact_id=parsed.artifact_id,
                    is_valid=parsed.is_valid,
                    score=parsed.score,
                    hallucination_check_passed=parsed.hallucination_check_passed,
                    warnings=parsed.warnings,
                    errors=parsed.errors,
                )
                return ToolResult.ok({
                    "id": res.id,
                    "artifact_id": res.artifact_id,
                    "is_valid": res.is_valid,
                    "score": res.score,
                    "hallucination_check_passed": res.hallucination_check_passed,
                })
            except (EntityNotFoundError, ValueError) as e:
                return ToolResult.fail(str(e))

        else:
            return ToolResult.fail(
                f"Unknown action '{parsed.action}'. Supported: 'get_artifact', 'list_artifacts', 'record_validation'"
            )
