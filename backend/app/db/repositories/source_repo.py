"""Repository for Source entity."""

from datetime import datetime
import json
import sqlite3
from typing import List, Optional
from ...models.project import Source
from ...models.enums import SourceType


class SourceRepository:
    """CRUD repository for Ingested Source assets."""

    @staticmethod
    def create_source(conn: sqlite3.Connection, source: Source) -> Source:
        sql = """
            INSERT INTO sources (
                id, project_id, name, source_type, mime_type, storage_ref,
                size_bytes, content_hash, extracted_text, created_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        conn.execute(sql, (
            source.id,
            source.project_id,
            source.name,
            source.source_type.value,
            source.mime_type,
            source.storage_ref,
            source.size_bytes,
            source.content_hash,
            source.extracted_text,
            source.created_at.isoformat(),
            json.dumps(source.metadata),
        ))
        return source

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> Source:
        return Source(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            source_type=SourceType(row["source_type"]),
            mime_type=row["mime_type"],
            storage_ref=row["storage_ref"],
            size_bytes=row["size_bytes"],
            content_hash=row["content_hash"],
            extracted_text=row["extracted_text"],
            created_at=datetime.fromisoformat(row["created_at"]),
            metadata=json.loads(row["metadata_json"]),
        )

    @staticmethod
    def get_source(conn: sqlite3.Connection, source_id: str) -> Optional[Source]:
        sql = """
            SELECT id, project_id, name, source_type, mime_type, storage_ref,
                   size_bytes, content_hash, extracted_text, created_at, metadata_json
            FROM sources
            WHERE id = ?
        """
        row = conn.execute(sql, (source_id,)).fetchone()
        if not row:
            return None
        return SourceRepository._row_to_model(row)

    @staticmethod
    def list_sources_by_project(conn: sqlite3.Connection, project_id: str) -> List[Source]:
        sql = """
            SELECT id, project_id, name, source_type, mime_type, storage_ref,
                   size_bytes, content_hash, extracted_text, created_at, metadata_json
            FROM sources
            WHERE project_id = ?
            ORDER BY created_at DESC
        """
        rows = conn.execute(sql, (project_id,)).fetchall()
        return [SourceRepository._row_to_model(row) for row in rows]

    @staticmethod
    def get_source_by_hash(
        conn: sqlite3.Connection,
        content_hash: str,
        project_id: Optional[str] = None,
    ) -> Optional[Source]:
        if project_id:
            sql = """
                SELECT id, project_id, name, source_type, mime_type, storage_ref,
                       size_bytes, content_hash, extracted_text, created_at, metadata_json
                FROM sources
                WHERE content_hash = ? AND project_id = ?
                LIMIT 1
            """
            row = conn.execute(sql, (content_hash, project_id)).fetchone()
        else:
            sql = """
                SELECT id, project_id, name, source_type, mime_type, storage_ref,
                       size_bytes, content_hash, extracted_text, created_at, metadata_json
                FROM sources
                WHERE content_hash = ?
                LIMIT 1
            """
            row = conn.execute(sql, (content_hash,)).fetchone()

        if not row:
            return None
        return SourceRepository._row_to_model(row)

    @staticmethod
    def get_source_by_cache_key(
        conn: sqlite3.Connection,
        cache_key: str,
        project_id: Optional[str] = None,
    ) -> Optional[Source]:
        """Lookup an existing source by its composite extraction cache key in metadata_json."""
        if project_id:
            sql = """
                SELECT id, project_id, name, source_type, mime_type, storage_ref,
                       size_bytes, content_hash, extracted_text, created_at, metadata_json
                FROM sources
                WHERE json_extract(metadata_json, '$.composite_cache_key') = ? AND project_id = ?
                LIMIT 1
            """
            row = conn.execute(sql, (cache_key, project_id)).fetchone()
        else:
            sql = """
                SELECT id, project_id, name, source_type, mime_type, storage_ref,
                       size_bytes, content_hash, extracted_text, created_at, metadata_json
                FROM sources
                WHERE json_extract(metadata_json, '$.composite_cache_key') = ?
                LIMIT 1
            """
            row = conn.execute(sql, (cache_key,)).fetchone()

        if not row:
            return None
        return SourceRepository._row_to_model(row)

    @staticmethod
    def update_source_metadata(
        conn: sqlite3.Connection,
        source_id: str,
        metadata: dict,
        extracted_text: Optional[str] = None,
    ) -> bool:
        if extracted_text is not None:
            sql = """
                UPDATE sources
                SET metadata_json = ?, extracted_text = ?
                WHERE id = ?
            """
            cur = conn.execute(sql, (json.dumps(metadata), extracted_text, source_id))
        else:
            sql = """
                UPDATE sources
                SET metadata_json = ?
                WHERE id = ?
            """
            cur = conn.execute(sql, (json.dumps(metadata), source_id))
        return cur.rowcount > 0

    @staticmethod
    def delete_source(conn: sqlite3.Connection, source_id: str) -> bool:
        sql = "DELETE FROM sources WHERE id = ?"
        cur = conn.execute(sql, (source_id,))
        return cur.rowcount > 0
