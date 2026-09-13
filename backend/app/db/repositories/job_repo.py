"""Repository for TransformationJob and CanonicalContent entities."""

from datetime import datetime
import json
import sqlite3
from typing import List, Optional
from ...models.job import GenerationConfig, TransformationJob
from ...models.content import CanonicalContent
from ...models.enums import JobState, OutputFormat


class JobRepository:
    """CRUD repository for Transformation Jobs and Canonical Content intermediates."""

    @staticmethod
    def create_job(conn: sqlite3.Connection, job: TransformationJob) -> TransformationJob:
        sql = """
            INSERT INTO jobs (
                id, project_id, session_id, prompt, source_ids_json, requested_formats_json, configuration_json,
                state, progress, current_stage, error, artifact_ids_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        formats_data = [fmt.value for fmt in job.requested_formats]
        conn.execute(sql, (
            job.id,
            job.project_id,
            job.session_id,
            job.prompt,
            json.dumps(job.source_ids),
            json.dumps(formats_data),
            json.dumps(job.configuration.model_dump(mode="json")),
            job.state.value,
            job.progress,
            job.current_stage,
            job.error,
            json.dumps(job.artifact_ids),
            job.created_at.isoformat(),
            job.updated_at.isoformat(),
        ))
        return job

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> TransformationJob:
        raw_formats = json.loads(row["requested_formats_json"])
        formats = [OutputFormat(f) for f in raw_formats]
        config_data = json.loads(row["configuration_json"])
        source_ids = json.loads(row["source_ids_json"]) if row["source_ids_json"] else []

        return TransformationJob(
            id=row["id"],
            project_id=row["project_id"],
            session_id=row["session_id"],
            prompt=row["prompt"],
            source_ids=source_ids,
            requested_formats=formats,
            configuration=GenerationConfig(**config_data),
            state=JobState(row["state"]),
            progress=row["progress"],
            current_stage=row["current_stage"],
            error=row["error"],
            artifact_ids=json.loads(row["artifact_ids_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def get_job(conn: sqlite3.Connection, job_id: str) -> Optional[TransformationJob]:
        sql = """
            SELECT id, project_id, session_id, prompt, source_ids_json, requested_formats_json, configuration_json,
                   state, progress, current_stage, error, artifact_ids_json, created_at, updated_at
            FROM jobs
            WHERE id = ?
        """
        row = conn.execute(sql, (job_id,)).fetchone()
        if not row:
            return None
        return JobRepository._row_to_model(row)

    @staticmethod
    def list_jobs(
        conn: sqlite3.Connection,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        state: Optional[JobState] = None,
    ) -> List[TransformationJob]:
        query = """
            SELECT id, project_id, session_id, prompt, source_ids_json, requested_formats_json, configuration_json,
                   state, progress, current_stage, error, artifact_ids_json, created_at, updated_at
            FROM jobs
        """
        clauses = []
        params = []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if state:
            clauses.append("state = ?")
            params.append(state.value if hasattr(state, "value") else str(state))

        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, tuple(params)).fetchall()
        return [JobRepository._row_to_model(row) for row in rows]



    @staticmethod
    def update_job_progress(
        conn: sqlite3.Connection,
        job_id: str,
        state: JobState,
        progress: float,
        current_stage: Optional[str] = None,
        error: Optional[str] = None,
        artifact_ids: Optional[List[str]] = None,
        configuration: Optional[GenerationConfig] = None,
    ) -> bool:
        now = datetime.now()
        fields = ["state = ?", "progress = ?", "current_stage = ?", "error = ?", "updated_at = ?"]
        params = [state.value, progress, current_stage, error, now.isoformat()]

        if artifact_ids is not None:
            fields.append("artifact_ids_json = ?")
            params.append(json.dumps(artifact_ids))

        if configuration is not None:
            fields.append("configuration_json = ?")
            params.append(json.dumps(configuration.model_dump(mode="json")))

        params.append(job_id)
        sql = f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?"
        cur = conn.execute(sql, tuple(params))
        return cur.rowcount > 0

    @staticmethod
    def save_canonical_content(conn: sqlite3.Connection, canonical: CanonicalContent) -> CanonicalContent:
        sql = """
            INSERT OR REPLACE INTO canonical_contents (
                id, source_ids_json, title, context, intent_json,
                entities_json, facts_json, claims_json, events_json,
                data_points_json, recommendations_json, references_json,
                content_hash, created_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        conn.execute(sql, (
            canonical.id,
            json.dumps(canonical.source_ids),
            canonical.title,
            canonical.context,
            json.dumps(canonical.intent.model_dump()),
            json.dumps([e.model_dump() for e in canonical.entities]),
            json.dumps([f.model_dump() for f in canonical.facts]),
            json.dumps([c.model_dump() for c in canonical.claims]),
            json.dumps([ev.model_dump() for ev in canonical.events]),
            json.dumps([dp.model_dump() for dp in canonical.data_points]),
            json.dumps(canonical.recommendations),
            json.dumps([r.model_dump() for r in canonical.references]),
            canonical.content_hash,
            canonical.created_at.isoformat(),
            json.dumps(canonical.metadata),
        ))
        return canonical

    @staticmethod
    def get_canonical_content(conn: sqlite3.Connection, canonical_id: str) -> Optional[CanonicalContent]:
        sql = """
            SELECT id, source_ids_json, title, context, intent_json,
                   entities_json, facts_json, claims_json, events_json,
                   data_points_json, recommendations_json, references_json,
                   content_hash, created_at, metadata_json
            FROM canonical_contents
            WHERE id = ?
        """
        row = conn.execute(sql, (canonical_id,)).fetchone()
        if not row:
            return None

        from ...models.content import (
            CanonicalEntity,
            CanonicalFact,
            CanonicalClaim,
            CanonicalEvent,
            CanonicalDataPoint,
            CanonicalReference,
            CanonicalIntent,
        )

        return CanonicalContent(
            id=row["id"],
            source_ids=json.loads(row["source_ids_json"]),
            title=row["title"],
            context=row["context"],
            intent=CanonicalIntent(**json.loads(row["intent_json"])),
            entities=[CanonicalEntity(**e) for e in json.loads(row["entities_json"])],
            facts=[CanonicalFact(**f) for f in json.loads(row["facts_json"])],
            claims=[CanonicalClaim(**c) for c in json.loads(row["claims_json"])],
            events=[CanonicalEvent(**ev) for ev in json.loads(row["events_json"])],
            data_points=[CanonicalDataPoint(**dp) for dp in json.loads(row["data_points_json"])],
            recommendations=json.loads(row["recommendations_json"]),
            references=[CanonicalReference(**r) for r in json.loads(row["references_json"])],
            content_hash=row["content_hash"],
            created_at=datetime.fromisoformat(row["created_at"]),
            metadata=json.loads(row["metadata_json"]),
        )
