"""Repository for TransformationJob, CanonicalContent, and JobEvent entities."""

from datetime import datetime, timezone
import json
import sqlite3
from typing import List, Optional
from ...models.job import GenerationConfig, TransformationJob
from ...models.content import CanonicalContent
from ...models.enums import JobState, OutputFormat
from ...models.transformation_events import (
    TransformationEventType,
    TransformationLifecycleEvent,
)


class JobRepository:
    """CRUD repository for Transformation Jobs, Canonical Content, and persistent Job Events."""

    @staticmethod
    def create_job(conn: sqlite3.Connection, job: TransformationJob) -> TransformationJob:
        sql = """
            INSERT INTO jobs (
                id, user_id, project_id, session_id, prompt, source_ids_json, requested_formats_json, configuration_json,
                state, progress, current_stage, error, artifact_ids_json, execution_id, worker_id, attempt_count,
                claimed_at, cancellation_requested, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        formats_data = [fmt.value for fmt in job.requested_formats]
        conn.execute(sql, (
            job.id,
            job.user_id,
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
            job.execution_id,
            job.worker_id,
            job.attempt_count,
            job.claimed_at.isoformat() if job.claimed_at else None,
            1 if job.cancellation_requested else 0,
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

        claimed_at = None
        if "claimed_at" in row.keys() and row["claimed_at"]:
            claimed_at = datetime.fromisoformat(row["claimed_at"])

        return TransformationJob(
            id=row["id"],
            user_id=row["user_id"] if "user_id" in row.keys() else None,
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
            execution_id=row["execution_id"] if "execution_id" in row.keys() else None,
            worker_id=row["worker_id"] if "worker_id" in row.keys() else None,
            attempt_count=row["attempt_count"] if "attempt_count" in row.keys() else 0,
            claimed_at=claimed_at,
            cancellation_requested=bool(row["cancellation_requested"]) if "cancellation_requested" in row.keys() else False,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def get_job(conn: sqlite3.Connection, job_id: str) -> Optional[TransformationJob]:
        sql = "SELECT * FROM jobs WHERE id = ?"
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
        user_id: Optional[str] = None,
    ) -> List[TransformationJob]:
        query = "SELECT * FROM jobs"
        clauses = []
        params = []
        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
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
    def claim_job_execution(
        conn: sqlite3.Connection,
        job_id: str,
        worker_id: str,
        execution_id: str,
    ) -> bool:
        """Atomic DB conditional update to acquire single-worker execution ownership."""
        now = datetime.now(timezone.utc).isoformat()
        sql = """
            UPDATE jobs
            SET state = ?,
                execution_id = ?,
                worker_id = ?,
                attempt_count = attempt_count + 1,
                claimed_at = ?,
                updated_at = ?
            WHERE id = ? AND state = ? AND cancellation_requested = 0
        """
        cur = conn.execute(sql, (
            JobState.PROCESSING.value,
            execution_id,
            worker_id,
            now,
            now,
            job_id,
            JobState.QUEUED.value,
        ))
        return cur.rowcount > 0

    @staticmethod
    def request_cancellation(conn: sqlite3.Connection, job_id: str) -> bool:
        """Flag cancellation_requested atomically without prematurely forcing CANCELLED state."""
        now = datetime.now(timezone.utc).isoformat()
        sql = """
            UPDATE jobs
            SET cancellation_requested = 1,
                updated_at = ?
            WHERE id = ? AND state IN (?, ?)
        """
        cur = conn.execute(sql, (now, job_id, JobState.QUEUED.value, JobState.PROCESSING.value))
        return cur.rowcount > 0

    @staticmethod
    def get_stale_jobs(conn: sqlite3.Connection) -> List[TransformationJob]:
        """Fetch abandoned running jobs or unexecuted queued jobs for startup recovery."""
        sql = """
            SELECT * FROM jobs
            WHERE state = ? OR (state = ? AND cancellation_requested = 0)
            ORDER BY created_at ASC
        """
        rows = conn.execute(sql, (JobState.PROCESSING.value, JobState.QUEUED.value)).fetchall()
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
        cancellation_requested: Optional[bool] = None,
    ) -> bool:
        now = datetime.now(timezone.utc)
        fields = ["state = ?", "progress = ?", "current_stage = ?", "error = ?", "updated_at = ?"]
        params = [state.value, progress, current_stage, error, now.isoformat()]

        if artifact_ids is not None:
            fields.append("artifact_ids_json = ?")
            params.append(json.dumps(artifact_ids))

        if configuration is not None:
            fields.append("configuration_json = ?")
            params.append(json.dumps(configuration.model_dump(mode="json")))

        if cancellation_requested is not None:
            fields.append("cancellation_requested = ?")
            params.append(1 if cancellation_requested else 0)

        params.append(job_id)
        sql = f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?"
        cur = conn.execute(sql, tuple(params))
        return cur.rowcount > 0

    @staticmethod
    def save_job_event(conn: sqlite3.Connection, event: TransformationLifecycleEvent) -> None:
        """Persist a lifecycle event to SQLite for durable SSE replay."""
        sql = """
            INSERT OR IGNORE INTO job_events (
                event_id, job_id, sequence, event_type, payload_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """
        conn.execute(sql, (
            event.event_id,
            event.job_id,
            event.sequence,
            event.event_type.value,
            json.dumps(event.payload),
            event.timestamp.isoformat(),
        ))

    @staticmethod
    def get_job_events(
        conn: sqlite3.Connection,
        job_id: str,
        after_sequence: int = 0,
    ) -> List[TransformationLifecycleEvent]:
        """Fetch persisted events for a job strictly where sequence > after_sequence."""
        sql = """
            SELECT event_id, job_id, sequence, event_type, payload_json, created_at
            FROM job_events
            WHERE job_id = ? AND sequence > ?
            ORDER BY sequence ASC
        """
        rows = conn.execute(sql, (job_id, after_sequence)).fetchall()
        return [
            TransformationLifecycleEvent(
                event_id=row["event_id"],
                job_id=row["job_id"],
                sequence=row["sequence"],
                event_type=TransformationEventType(row["event_type"]),
                payload=json.loads(row["payload_json"]),
                timestamp=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

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
