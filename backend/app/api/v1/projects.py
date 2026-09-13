"""Projects REST API router."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from ...models.project import Project
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
async def create_project(req: CreateProjectRequest) -> Project:
    """Create a new project container."""
    return project_service.create_project(
        name=req.name,
        description=req.description,
        metadata=req.metadata,
    )


@router.get("", response_model=List[Project])
async def list_projects() -> List[Project]:
    """List all projects ordered by update recency."""
    return project_service.list_projects()


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str) -> Project:
    """Get project details by ID."""
    return project_service.get_project(project_id)


@router.patch("/{project_id}", response_model=Project)
async def update_project(project_id: str, req: UpdateProjectRequest) -> Project:
    """Update project details."""
    return project_service.update_project(
        project_id=project_id,
        name=req.name,
        description=req.description,
        metadata=req.metadata,
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str) -> None:
    """Delete a project and disassociate its assets."""
    project_service.delete_project(project_id)
