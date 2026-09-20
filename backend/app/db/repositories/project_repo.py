"""Repository for Project entity."""

from datetime import datetime, timezone
import json
import sqlite3
from typing import List, Optional
from ...models.project import Project


class ProjectRepository:
    """CRUD repository for Projects."""

    @staticmethod
    def create_project(conn: sqlite3.Connection, project: Project) -> Project:
        sql = """
            INSERT INTO projects (id, user_id, name, description, created_at, updated_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        conn.execute(sql, (
            project.id,
            project.user_id,
            project.name,
            project.description,
            project.created_at.isoformat(),
            project.updated_at.isoformat(),
            json.dumps(project.metadata),
        ))
        return project

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> Project:
        user_id = row["user_id"] if "user_id" in row.keys() else None
        return Project(
            id=row["id"],
            user_id=user_id,
            name=row["name"],
            description=row["description"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata=json.loads(row["metadata_json"]),
        )

    @staticmethod
    def get_project(conn: sqlite3.Connection, project_id: str) -> Optional[Project]:
        sql = "SELECT * FROM projects WHERE id = ?"
        row = conn.execute(sql, (project_id,)).fetchone()
        if not row:
            return None
        return ProjectRepository._row_to_model(row)

    @staticmethod
    def list_projects(conn: sqlite3.Connection, user_id: Optional[str] = None) -> List[Project]:
        if user_id:
            sql = "SELECT * FROM projects WHERE user_id = ? ORDER BY updated_at DESC"
            rows = conn.execute(sql, (user_id,)).fetchall()
        else:
            sql = "SELECT * FROM projects ORDER BY updated_at DESC"
            rows = conn.execute(sql).fetchall()
        return [ProjectRepository._row_to_model(row) for row in rows]

    @staticmethod
    def update_project(conn: sqlite3.Connection, project: Project) -> Optional[Project]:
        sql = """
            UPDATE projects
            SET user_id = ?, name = ?, description = ?, updated_at = ?, metadata_json = ?
            WHERE id = ?
        """
        cur = conn.execute(sql, (
            project.user_id,
            project.name,
            project.description,
            datetime.now(timezone.utc).isoformat(),
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
