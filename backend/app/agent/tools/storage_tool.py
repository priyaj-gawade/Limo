"""Storage and artifact reading tool for Limo Agent Infrastructure.

Strictly enforces authorization boundaries: an agent can only read artifacts
that belong to its current active project/session context (MUST-FIX #2).
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from ..contracts import BaseTool, ToolResult, PermissionType
from ..context import AgentContext
from ...services.artifact_service import ArtifactService, artifact_service
from ...exceptions import EntityNotFoundError, StorageError


class StorageReadArgs(BaseModel):
    artifact_id: str = Field(description="ID of the deliverable artifact to inspect")
    max_bytes: Optional[int] = Field(default=8192, description="Maximum bytes of content to read into context (budget protection)")


class StorageTool(BaseTool):
    """Safely reads artifact content within active project authorization boundaries."""

    name: str = "storage_tool"
    description: str = (
        "Read verified artifact deliverable content from storage. "
        "Strictly restricted to artifacts within the active project context."
    )
    permission_type: PermissionType = PermissionType.READ

    def __init__(self, artifact_svc: Optional[ArtifactService] = None) -> None:
        self.artifact_svc = artifact_svc or artifact_service

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return StorageReadArgs.model_json_schema()

    async def execute(self, args: Dict[str, Any], context: Optional[AgentContext] = None) -> ToolResult:
        try:
            parsed = StorageReadArgs(**args)
        except Exception as e:
            return ToolResult.fail(f"Invalid arguments for storage_tool: {str(e)}")

        if not parsed.artifact_id:
            return ToolResult.fail("Missing required 'artifact_id'")

        try:
            artifact = self.artifact_svc.get_artifact(parsed.artifact_id)
        except EntityNotFoundError:
            return ToolResult.fail(f"Artifact '{parsed.artifact_id}' not found")

        # MUST-FIX #2: Strict Context Authorization Guard
        if context and context.project_id:
            if artifact.project_id and artifact.project_id != context.project_id:
                return ToolResult.fail(
                    f"Access denied: Artifact '{artifact.id}' belongs to project '{artifact.project_id}', "
                    f"not the active project context '{context.project_id}'"
                )

        try:
            raw_bytes = self.artifact_svc.read_artifact_content(artifact.id)
            total_size = len(raw_bytes)

            # Attempt text decoding for preview
            try:
                decoded_text = raw_bytes[: parsed.max_bytes].decode("utf-8")
                is_text = True
            except UnicodeDecodeError:
                decoded_text = None
                is_text = False

            return ToolResult.ok({
                "artifact_id": artifact.id,
                "title": artifact.title,
                "file_format": artifact.file_format,
                "size_bytes": total_size,
                "content_hash": artifact.content_hash,
                "is_text": is_text,
                "content_preview": decoded_text if is_text else f"[Binary data: {total_size} bytes]",
                "truncated": total_size > parsed.max_bytes,
            })
        except StorageError as e:
            return ToolResult.fail(f"Storage error reading artifact: {str(e)}")
        except Exception as e:
            return ToolResult.fail(f"Unexpected error reading artifact: {str(e)}")
