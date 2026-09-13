"""Repository for Project entity."""

from datetime import datetime
import json
import sqlite3
from typing import List, Optional
from ...models.project import Project


class ProjectRepository:
    """CRUD repository for Projects."""

    @staticmethod
    def create_project(conn: sqlite3.Connection, project: Project) -> Project:
        sql = """
            INSERT INTO projects (id, name, description, created_at, updated_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        conn.execute(sql, (
            project.id,
            project.name,
            project.description,
            project.created_at.isoformat(),
            project.updated_at.isoformat(),
            json.dumps(project.metadata),
        ))
        return project

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata=json.loads(row["metadata_json"]),
        )

    @staticmethod
    def get_project(conn: sqlite3.Connection, project_id: str) -> Optional[Project]:
        sql = "SELECT id, name, description, created_at, updated_at, metadata_json FROM projects WHERE id = ?"
        row = conn.execute(sql, (project_id,)).fetchone()
        if not row:
            return None
        return ProjectRepository._row_to_model(row)

    @staticmethod
    def list_projects(conn: sqlite3.Connection) -> List[Project]:
        sql = "SELECT id, name, description, created_at, updated_at, metadata_json FROM projects ORDER BY updated_at DESC"
        rows = conn.execute(sql).fetchall()
        return [ProjectRepository._row_to_model(row) for row in rows]

    @staticmethod
    def update_project(conn: sqlite3.Connection, project: Project) -> Optional[Project]:
        sql = """
            UPDATE projects
            SET name = ?, description = ?, updated_at = ?, metadata_json = ?
            WHERE id = ?
        """
        cur = conn.execute(sql, (
            project.name,
            project.description,
            project.updated_at.isoformat(),
            json.dumps(project.metadata),
            project.id,
        ))
        if cur.rowcount == 0:
            return None
        return project

    @staticmethod
    def delete_project(conn: sqlite3.Connection, project_id: str) -> bool:
        sql = "DELETE FROM projects WHERE id = ?"
        cur = conn.execute(sql, (project_id,))
        return cur.rowcount > 0
