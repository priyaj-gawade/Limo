"""Repository for TransformationJob and lifecycle execution events."""

from datetime import datetime, timezone
import json
from typing import Any, List, Optional
from ...models.job import GenerationConfig, TransformationJob
from ...models.content import CanonicalContent
from ...models.enums import JobState, OutputFormat
from ...models.transformation_events import (
    TransformationEventType,
    TransformationLifecycleEvent,
)
from .common import parse_dt, parse_json


class JobRepository:
    """CRUD repository for TransformationJob and lifecycle execution events."""

    @staticmethod
    def create_job(conn: Any, job: TransformationJob) -> TransformationJob:
        sql = """
            INSERT INTO jobs (
                id, user_id, project_id, session_id, prompt, source_ids_json,
                requested_formats_json, configuration_json, state, progress,
                current_stage, error, artifact_ids_json, execution_id, worker_id,
                attempt_count, claimed_at, cancellation_requested, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        conn.execute(sql, (
            job.id,
            job.user_id,
            job.project_id,
            job.session_id,
            job.prompt,
            json.dumps(job.source_ids),
            json.dumps([f.value for f in job.requested_formats]),
            job.configuration.model_dump_json(),
            job.state.value,
            job.progress,
            job.current_stage,
            job.error,
            json.dumps(job.artifact_ids),
            job.execution_id,
            job.worker_id,
            job.attempt_count,
            job.claimed_at.isoformat() if job.claimed_at else None,
            job.cancellation_requested,
            job.created_at.isoformat(),
            job.updated_at.isoformat(),
        ))
        return job

    @staticmethod
    def _row_to_model(row: Any) -> TransformationJob:
        raw_formats = parse_json(row["requested_formats_json"], default=[])
        formats = [OutputFormat(f) for f in raw_formats]
        config_data = parse_json(row["configuration_json"], default={})
        source_ids = parse_json(row["source_ids_json"], default=[]) if row["source_ids_json"] else []

        claimed_at = None
        if "claimed_at" in row.keys() and row["claimed_at"]:
            claimed_at = parse_dt(row["claimed_at"])

        return TransformationJob(
            id=row["id"],
            user_id=row["user_id"] if "user_id" in row.keys() else None,
            project_id=row["project_id"],
            session_id=row["session_id"],
            prompt=row["prompt"] if "prompt" in row.keys() else None,
            source_ids=source_ids,
            requested_formats=formats,
            configuration=GenerationConfig(**config_data),
            state=JobState(row["state"]),
            progress=row["progress"],
            current_stage=row["current_stage"],
            error=row["error"],
            artifact_ids=parse_json(row["artifact_ids_json"], default=[]),
            execution_id=row["execution_id"] if "execution_id" in row.keys() else None,
            worker_id=row["worker_id"] if "worker_id" in row.keys() else None,
            attempt_count=row["attempt_count"] if "attempt_count" in row.keys() else 0,
            claimed_at=claimed_at,
            cancellation_requested=bool(row["cancellation_requested"]) if "cancellation_requested" in row.keys() else False,
            created_at=parse_dt(row["created_at"]),
            updated_at=parse_dt(row["updated_at"]),
        )

    @staticmethod
    def get_job(conn: Any, job_id: str) -> Optional[TransformationJob]:
        sql = """
            SELECT id, user_id, project_id, session_id, prompt, source_ids_json,
                   requested_formats_json, configuration_json, state, progress,
                   current_stage, error, artifact_ids_json, execution_id, worker_id,
                   attempt_count, claimed_at, cancellation_requested, created_at, updated_at
            FROM jobs
            WHERE id = ?
        """
        row = conn.execute(sql, (job_id,)).fetchone()
        if not row:
            return None
        return JobRepository._row_to_model(row)

    @staticmethod
    def list_jobs(
        conn: Any,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        state: Optional[JobState] = None,
    ) -> List[TransformationJob]:
        query = """
            SELECT id, user_id, project_id, session_id, prompt, source_ids_json,
                   requested_formats_json, configuration_json, state, progress,
                   current_stage, error, artifact_ids_json, execution_id, worker_id,
                   attempt_count, claimed_at, cancellation_requested, created_at, updated_at
            FROM jobs
        """
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
        conn: Any,
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
            WHERE id = ? AND state = ? AND cancellation_requested = ?
        """
        cur = conn.execute(sql, (
            JobState.PROCESSING.value,
            execution_id,
            worker_id,
            now,
            now,
            job_id,
            JobState.QUEUED.value,
            False,
        ))
        return cur.rowcount > 0

    @staticmethod
    def request_cancellation(conn: Any, job_id: str) -> bool:
        """Flag cancellation_requested atomically without prematurely forcing CANCELLED state."""
        now = datetime.now(timezone.utc).isoformat()
        sql = """
            UPDATE jobs
            SET cancellation_requested = ?,
                updated_at = ?
            WHERE id = ? AND state IN (?, ?)
        """
        cur = conn.execute(sql, (True, now, job_id, JobState.QUEUED.value, JobState.PROCESSING.value))
        return cur.rowcount > 0

    @staticmethod
    def get_stale_jobs(conn: Any) -> List[TransformationJob]:
        """Fetch abandoned running jobs or unexecuted queued jobs for startup recovery."""
        sql = """
            SELECT * FROM jobs
            WHERE state = ? OR (state = ? AND cancellation_requested = ?)
            ORDER BY created_at ASC
        """
        rows = conn.execute(sql, (JobState.PROCESSING.value, JobState.QUEUED.value, False)).fetchall()
        return [JobRepository._row_to_model(row) for row in rows]

    @staticmethod
    def update_job_progress(
        conn: Any,
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
            params.append(cancellation_requested)

        params.append(job_id)
        sql = f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?"
        cur = conn.execute(sql, tuple(params))
        return cur.rowcount > 0

    @staticmethod
    def save_job_event(conn: Any, event: TransformationLifecycleEvent) -> None:
        """Persist a lifecycle event for durable SSE replay."""
        sql = """
            INSERT INTO job_events (
                event_id, job_id, sequence, event_type, payload_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT DO NOTHING
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
        conn: Any,
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
                payload=parse_json(row["payload_json"], default={}),
                timestamp=parse_dt(row["created_at"]),
            )
            for row in rows
        ]

    @staticmethod
    def save_canonical_content(conn: Any, canonical: CanonicalContent) -> CanonicalContent:
        sql = """
            INSERT INTO canonical_contents (
                id, source_ids_json, title, context, intent_json,
                entities_json, facts_json, claims_json, events_json,
                data_points_json, recommendations_json, references_json,
                content_hash, created_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                source_ids_json = EXCLUDED.source_ids_json,
                title = EXCLUDED.title,
                context = EXCLUDED.context,
                intent_json = EXCLUDED.intent_json,
                entities_json = EXCLUDED.entities_json,
                facts_json = EXCLUDED.facts_json,
                claims_json = EXCLUDED.claims_json,
                events_json = EXCLUDED.events_json,
                data_points_json = EXCLUDED.data_points_json,
                recommendations_json = EXCLUDED.recommendations_json,
                references_json = EXCLUDED.references_json,
                content_hash = EXCLUDED.content_hash,
                metadata_json = EXCLUDED.metadata_json
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
    def get_canonical_content(conn: Any, canonical_id: str) -> Optional[CanonicalContent]:
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
            source_ids=parse_json(row["source_ids_json"], default=[]),
            title=row["title"],
            context=row["context"],
            intent=CanonicalIntent(**parse_json(row["intent_json"], default={})),
            entities=[CanonicalEntity(**e) for e in parse_json(row["entities_json"], default=[])],
            facts=[CanonicalFact(**f) for f in parse_json(row["facts_json"], default=[])],
            claims=[CanonicalClaim(**c) for c in parse_json(row["claims_json"], default=[])],
            events=[CanonicalEvent(**ev) for ev in parse_json(row["events_json"], default=[])],
            data_points=[CanonicalDataPoint(**dp) for dp in parse_json(row["data_points_json"], default=[])],
            recommendations=parse_json(row["recommendations_json"], default=[]),
            references=[CanonicalReference(**r) for r in parse_json(row["references_json"], default=[])],
            content_hash=row["content_hash"],
            created_at=parse_dt(row["created_at"]),
            metadata=parse_json(row["metadata_json"], default={}),
        )
