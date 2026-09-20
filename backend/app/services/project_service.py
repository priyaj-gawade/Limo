"""Project management business service."""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from ..db.connection import get_connection
from ..db.repositories.project_repo import ProjectRepository
from ..exceptions import EntityNotFoundError
from ..models.project import Project

logger = logging.getLogger("limo.services.project")


class ProjectService:
    """Business service for project workspaces."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def create_project(
        self,
        name: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Project:
        """Create and persist a new project container."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Project name cannot be empty")

        project = Project(
            user_id=user_id,
            name=clean_name,
            description=description.strip() if description else None,
            metadata=metadata or {},
        )

        with get_connection(self.db_path) as conn:
            created = ProjectRepository.create_project(conn, project)
            logger.info("Created project '%s' (id: %s)", created.name, created.id)
            return created

    def get_project(self, project_id: str) -> Project:
        """Retrieve a project by ID or raise EntityNotFoundError."""
        with get_connection(self.db_path) as conn:
            project = ProjectRepository.get_project(conn, project_id)
            if not project:
                raise EntityNotFoundError("Project", project_id)
            return project

    def list_projects(self, user_id: Optional[str] = None) -> List[Project]:
        """List all projects ordered by last modification timestamp."""
        with get_connection(self.db_path) as conn:
            return ProjectRepository.list_projects(conn, user_id=user_id)

    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Project:
        """Update existing project details."""
        with get_connection(self.db_path) as conn:
            project = ProjectRepository.get_project(conn, project_id)
            if not project:
                raise EntityNotFoundError("Project", project_id)

            if name is not None:
                clean_name = name.strip()
                if not clean_name:
                    raise ValueError("Project name cannot be empty")
                project.name = clean_name

            if description is not None:
                project.description = description.strip() if description else None

            if metadata is not None:
                project.metadata = metadata

            project.updated_at = datetime.now(timezone.utc)
            updated = ProjectRepository.update_project(conn, project)
            if not updated:
                raise EntityNotFoundError("Project", project_id)

            logger.info("Updated project (id: %s)", project_id)
            return updated

    def delete_project(self, project_id: str) -> bool:
        """Delete a project by ID or raise EntityNotFoundError."""
        with get_connection(self.db_path) as conn:
            project = ProjectRepository.get_project(conn, project_id)
            if not project:
                raise EntityNotFoundError("Project", project_id)

            deleted = ProjectRepository.delete_project(conn, project_id)
            logger.info("Deleted project (id: %s)", project_id)
            return deleted


project_service = ProjectService()
