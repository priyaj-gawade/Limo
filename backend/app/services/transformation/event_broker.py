"""Transformation Event Broker with Atomic Sequencing and In-Memory Replay (Phase D6.5).

Features:
- Atomic per-job monotonic sequence counter (1, 2, 3...) protected against concurrent emission.
- Process-lifetime event replay buffer (in-memory ring buffer, max 200 events/job).
  NOTE: Process-lifetime only. Durable restart-safe replay is deferred to Phase D9.
- Strict payload sanitization: strips private CoT, keys, passwords, tracebacks, and system filepaths.
- Pub/sub distribution for sync and async listeners.
- Pure async generator yielding standard SSE-formatted frames without coupling to FastAPI transport.
"""

import asyncio
from datetime import datetime, timezone
import logging
import re
import threading
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set

from ...db.connection import get_connection
from ...db.repositories.job_repo import JobRepository
from ...models.transformation_events import (
    TransformationEventType,
    TransformationLifecycleEvent,
)

logger = logging.getLogger("limo.services.transformation.event_broker")

# Sensitive key names forbidden from public events
FORBIDDEN_PAYLOAD_KEYS = {
    "thought",
    "reasoning",
    "chain_of_thought",
    "private_scratchpad",
    "api_key",
    "token",
    "secret",
    "password",
    "connection_string",
    "auth_header",
    "system_prompt",
    "prompt_template",
    "traceback",
}

# Regex to detect absolute filesystem paths (Windows or Unix)
SYSTEM_PATH_REGEX = re.compile(
    r"(?:[a-zA-Z]:[\\/][^:\s\"\'<>]+)|(?:/(?:home|Users|var|tmp|etc|usr)/[^\s\"\'<>]+)",
    re.IGNORECASE,
)


def sanitize_public_payload(data: Any) -> Any:
    """Recursively scrub sensitive keys, stack traces, and local filesystem paths from public event payloads."""
    if isinstance(data, dict):
        scrubbed = {}
        for k, v in data.items():
            if str(k).lower() in FORBIDDEN_PAYLOAD_KEYS:
                continue
            scrubbed[k] = sanitize_public_payload(v)
        return scrubbed
    elif isinstance(data, list):
        return [sanitize_public_payload(item) for item in data]
    elif isinstance(data, str):
        if "Traceback (most recent call last)" in data:
            return "Execution encountered an internal error"
        if SYSTEM_PATH_REGEX.search(data):
            return SYSTEM_PATH_REGEX.sub("[REDACTED_PATH]", data)
        return data
    return data


class TransformationEventBroker:
    """Manages ordered transformation lifecycle events with SQLite persistence and race-free replay."""

    def __init__(
        self,
        max_buffer_per_job: int = 200,
        max_events_per_job: Optional[int] = None,
        db_path: Optional[str] = None,
    ):
        self._max_buffer = max_events_per_job if max_events_per_job is not None else max_buffer_per_job
        self.db_path = db_path
        self._sequences: Dict[str, int] = {}
        self._history: Dict[str, List[TransformationLifecycleEvent]] = {}
        self._subscribers: Dict[str, List[Callable[[TransformationLifecycleEvent], Any]]] = {}
        self._job_locks: Dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()

    def _get_lock_for_job(self, job_id: str) -> threading.Lock:
        with self._meta_lock:
            if job_id not in self._job_locks:
                self._job_locks[job_id] = threading.Lock()
            return self._job_locks[job_id]

    def emit(
        self,
        job_id: str,
        event_type: TransformationEventType,
        payload: Optional[Dict[str, Any]] = None,
    ) -> TransformationLifecycleEvent:
        """Construct, sequence atomically, persist to SQLite, buffer, and dispatch a safe public event."""
        job_lock = self._get_lock_for_job(job_id)
        with job_lock:
            current_seq = self._sequences.get(job_id, 0) + 1
            self._sequences[job_id] = current_seq

            # Sanitize payload
            safe_payload = sanitize_public_payload(payload or {})

            event = TransformationLifecycleEvent(
                sequence=current_seq,
                job_id=job_id,
                event_type=event_type,
                timestamp=datetime.now(timezone.utc),
                payload=safe_payload,
            )

            # 1. Durable persistence to SQLite job_events table
            try:
                with get_connection(self.db_path) as conn:
                    JobRepository.save_job_event(conn, event)
            except Exception as e:
                logger.warning("Failed to persist event to SQLite for job %s: %s", job_id, str(e))

            # 2. In-memory ring buffer for low-latency live operations
            if job_id not in self._history:
                self._history[job_id] = []
            buf = self._history[job_id]
            buf.append(event)
            if len(buf) > self._max_buffer:
                buf.pop(0)

            # Collect snapshot of listeners under lock
            listeners = list(self._subscribers.get(job_id, []))

        logger.debug(
            "Emitted transformation event: job=%s, seq=%d, type=%s",
            job_id,
            event.sequence,
            event.event_type.value,
        )

        # Notify subscribers outside the lock to avoid deadlocks
        for listener in listeners:
            try:
                import inspect
                if inspect.iscoroutinefunction(listener):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(listener(event))
                    except RuntimeError:
                        asyncio.run(listener(event))
                else:
                    listener(event)
            except Exception as e:
                logger.warning("Listener threw exception on event '%s': %s", event.event_id, str(e))

        return event

    def subscribe(
        self,
        job_id: str,
        listener: Callable[[TransformationLifecycleEvent], Any],
    ) -> None:
        """Register a callback for events on a specific job."""
        with self._meta_lock:
            if job_id not in self._subscribers:
                self._subscribers[job_id] = []
            if listener not in self._subscribers[job_id]:
                self._subscribers[job_id].append(listener)

    def unsubscribe(
        self,
        job_id: str,
        listener: Callable[[TransformationLifecycleEvent], Any],
    ) -> None:
        """Unregister a callback for a specific job."""
        with self._meta_lock:
            if job_id in self._subscribers and listener in self._subscribers[job_id]:
                self._subscribers[job_id].remove(listener)

    def replay(
        self,
        job_id: str,
        after_sequence: int = 0,
    ) -> List[TransformationLifecycleEvent]:
        """Return historical events where sequence > after_sequence from SQLite and memory."""
        db_events: List[TransformationLifecycleEvent] = []
        try:
            with get_connection(self.db_path) as conn:
                db_events = JobRepository.get_job_events(conn, job_id, after_sequence=after_sequence)
        except Exception as e:
            logger.debug("SQLite event replay lookup failed for job %s: %s", job_id, e)

        job_lock = self._get_lock_for_job(job_id)
        with job_lock:
            mem_events = [e for e in self._history.get(job_id, []) if e.sequence > after_sequence]

        # Merge DB and memory events deduplicating by sequence
        merged = {e.sequence: e for e in mem_events}
        for e in db_events:
            merged[e.sequence] = e
        return [merged[s] for s in sorted(merged.keys())]

    async def stream_job_events(
        self,
        job_id: str,
        after_sequence: int = 0,
        poll_timeout: Optional[float] = None,
        heartbeat_interval: float = 15.0,
    ) -> AsyncGenerator[str, None]:
        """Yield Server-Sent Events (SSE) text frames with race-free reconnect and keepalive pings."""
        queue: asyncio.Queue[TransformationLifecycleEvent] = asyncio.Queue()

        def on_event(evt: TransformationLifecycleEvent):
            queue.put_nowait(evt)

        # 1. Subscribe to live queue FIRST before querying DB to eliminate race window
        self.subscribe(job_id, on_event)

        try:
            # 2. Replay missed historical events from authoritative SQLite store
            replayed = self.replay(job_id, after_sequence=after_sequence)
            last_yielded_seq = after_sequence
            for evt in replayed:
                yield evt.to_sse_frame()
                if evt.sequence > last_yielded_seq:
                    last_yielded_seq = evt.sequence

            # 3. Stream live events
            terminal_types = {
                TransformationEventType.JOB_COMPLETED,
                TransformationEventType.JOB_FAILED,
                TransformationEventType.JOB_CANCELLED,
                TransformationEventType.JOB_WAITING_EXTERNAL,
                TransformationEventType.JOB_PARTIALLY_COMPLETED,
            }

            idle_wait = heartbeat_interval if poll_timeout is None else poll_timeout

            while True:
                try:
                    live_evt = await asyncio.wait_for(queue.get(), timeout=idle_wait)
                except asyncio.TimeoutError:
                    if poll_timeout is not None:
                        break
                    # Emit standard SSE keepalive comment frame to prevent proxy drop
                    yield ": keepalive\n\n"
                    continue

                # Deduplicate: Discard any events that were already replayed from DB
                if live_evt.sequence > last_yielded_seq:
                    yield live_evt.to_sse_frame()
                    last_yielded_seq = live_evt.sequence

                if live_evt.event_type in terminal_types:
                    break

        finally:
            self.unsubscribe(job_id, on_event)


event_broker = TransformationEventBroker()
