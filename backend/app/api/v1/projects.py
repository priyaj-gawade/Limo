"""Projects REST API router with resource authorization."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from ...auth.config import auth_config
from ...auth.dependencies import authorize_resource, get_current_user
from ...models.project import Project
from ...models.user import User
from ...services.project_service import project_service

router = APIRouter(prefix="/projects", tags=["Projects"])


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255, description="Project title")
    description: Optional[str] = Field(default=None, max_length=2000, description="Project description")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extension metadata")


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    metadata: Optional[Dict[str, Any]] = None


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    req: CreateProjectRequest,
    current_user: User = Depends(get_current_user),
) -> Project:
    """Create a new project container bound to the current user."""
    return project_service.create_project(
        name=req.name,
        description=req.description,
        metadata=req.metadata,
        user_id=current_user.id if current_user else None,
    )


@router.get("", response_model=List[Project])
async def list_projects(
    current_user: User = Depends(get_current_user),
) -> List[Project]:
    """List all projects ordered by update recency, scoped to user on web surface."""
    user_scope = current_user.id if auth_config.is_web_surface else None
    return project_service.list_projects(user_id=user_scope)


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> Project:
    """Get project details by ID with resource authorization."""
    project = project_service.get_project(project_id)
    authorize_resource(project.user_id, current_user)
    return project


@router.patch("/{project_id}", response_model=Project)
async def update_project(
    project_id: str,
    req: UpdateProjectRequest,
    current_user: User = Depends(get_current_user),
) -> Project:
    """Update project details."""
    project = project_service.get_project(project_id)
    authorize_resource(project.user_id, current_user)
    return project_service.update_project(
        project_id=project_id,
        name=req.name,
        description=req.description,
        metadata=req.metadata,
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a project and disassociate its assets."""
    project = project_service.get_project(project_id)
    authorize_resource(project.user_id, current_user)
    project_service.delete_project(project_id)
