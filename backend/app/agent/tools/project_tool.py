"""Project workspace management tool for Limo Agent Infrastructure."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from ..contracts import BaseTool, ToolResult, PermissionType
from ..context import AgentContext
from ...services.project_service import ProjectService, project_service
from ...exceptions import EntityNotFoundError


class ProjectArgs(BaseModel):
    action: str = Field(description="Action to perform: 'get_project', 'list_projects', or 'create_project'")
    project_id: Optional[str] = Field(default=None, description="Project ID (required for 'get_project' if not in context)")
    name: Optional[str] = Field(default=None, description="Project name (required for 'create_project')")
    description: Optional[str] = Field(default=None, description="Project description (optional for 'create_project')")


class ProjectTool(BaseTool):
    """Inspect and manage project workspaces."""

    name: str = "project_tool"
    description: str = "Query project workspace details or list available projects."
    permission_type: PermissionType = PermissionType.READ

    def __init__(self, service: Optional[ProjectService] = None) -> None:
        self.service = service or project_service

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return ProjectArgs.model_json_schema()

    async def execute(self, args: Dict[str, Any], context: Optional[AgentContext] = None) -> ToolResult:
        try:
            parsed = ProjectArgs(**args)
        except Exception as e:
            return ToolResult.fail(f"Invalid arguments for project_tool: {str(e)}")

        if parsed.action == "list_projects":
            projects = self.service.list_projects()
            summaries = [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in projects
            ]
            return ToolResult.ok({"projects": summaries, "count": len(summaries)})

        elif parsed.action == "get_project":
            project_id = parsed.project_id or (context.project_id if context else None)
            if not project_id:
                return ToolResult.fail("Missing required 'project_id'")
            try:
                project = self.service.get_project(project_id)
                return ToolResult.ok({
                    "id": project.id,
                    "name": project.name,
                    "description": project.description,
                    "created_at": project.created_at.isoformat() if project.created_at else None,
                    "updated_at": project.updated_at.isoformat() if project.updated_at else None,
                })
            except EntityNotFoundError:
                return ToolResult.fail(f"Project '{project_id}' not found")

        elif parsed.action == "create_project":
            if not parsed.name or not parsed.name.strip():
                return ToolResult.fail("Missing required 'name' for create_project")
            try:
                project = self.service.create_project(
                    name=parsed.name.strip(),
                    description=parsed.description,
                )
                return ToolResult.ok({
                    "id": project.id,
                    "name": project.name,
                    "created": True,
                })
            except Exception as e:
                return ToolResult.fail(f"Failed to create project: {str(e)}")

        else:
            return ToolResult.fail(
                f"Unknown action '{parsed.action}'. Supported: 'get_project', 'list_projects', 'create_project'"
            )
