"""Repository for Source entity."""

from datetime import datetime
import json
from typing import Any, List, Optional
from ...models.project import Source
from ...models.enums import SourceType
from .common import parse_dt, parse_json


class SourceRepository:
    """CRUD repository for Ingested Source assets."""

    @staticmethod
    def create_source(conn: Any, source: Source) -> Source:
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
    def _row_to_model(row: Any) -> Source:
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
            created_at=parse_dt(row["created_at"]),
            metadata=parse_json(row["metadata_json"], default={}),
        )

    @staticmethod
    def get_source(conn: Any, source_id: str) -> Optional[Source]:
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
    def list_sources_by_project(conn: Any, project_id: str) -> List[Source]:
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
        conn: Any,
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
        conn: Any,
        cache_key: str,
        project_id: Optional[str] = None,
    ) -> Optional[Source]:
        """Lookup an existing source by its composite extraction cache key in metadata_json."""
        is_pg = getattr(conn, "is_postgres", False)
        json_filter = (
            "metadata_json::jsonb ->> 'composite_cache_key' = ?"
            if is_pg
            else "json_extract(metadata_json, '$.composite_cache_key') = ?"
        )

        if project_id:
            sql = f"""
                SELECT id, project_id, name, source_type, mime_type, storage_ref,
                       size_bytes, content_hash, extracted_text, created_at, metadata_json
                FROM sources
                WHERE {json_filter} AND project_id = ?
                LIMIT 1
            """
            row = conn.execute(sql, (cache_key, project_id)).fetchone()
        else:
            sql = f"""
                SELECT id, project_id, name, source_type, mime_type, storage_ref,
                       size_bytes, content_hash, extracted_text, created_at, metadata_json
                FROM sources
                WHERE {json_filter}
                LIMIT 1
            """
            row = conn.execute(sql, (cache_key,)).fetchone()

        if not row:
            return None
        return SourceRepository._row_to_model(row)

    @staticmethod
    def update_source_metadata(
        conn: Any,
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
    def delete_source(conn: Any, source_id: str) -> bool:
        sql = "DELETE FROM sources WHERE id = ?"
        cur = conn.execute(sql, (source_id,))
        return cur.rowcount > 0
