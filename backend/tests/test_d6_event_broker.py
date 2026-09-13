"""Unit and concurrency tests for Phase D6.5 TransformationEventBroker."""

import asyncio
import pytest
from app.models.enums import OutputFormat
from app.models.transformation_events import TransformationEventType
from app.services.job_service import JobService
from app.services.transformation.event_broker import TransformationEventBroker
from app.services.transformation.handoff import JobArtifactHandoffService


@pytest.fixture
def broker():
    """Create a fresh isolated EventBroker for testing."""
    return TransformationEventBroker(max_events_per_job=50)


def test_monotonic_sequence_allocation(broker):
    """Verify sequence numbers are strictly incremented per job starting at 1."""
    job_id = "job_test_monotonic_1"
    evt1 = broker.emit(job_id, TransformationEventType.JOB_STARTED, {"stage": "1"})
    evt2 = broker.emit(job_id, TransformationEventType.TASK_STARTED, {"stage": "2"})
    evt3 = broker.emit(job_id, TransformationEventType.TASK_COMPLETED, {"stage": "3"})

    assert evt1.sequence == 1
    assert evt2.sequence == 2
    assert evt3.sequence == 3


@pytest.mark.asyncio
async def test_concurrent_emission_atomic_sequences_no_collision(broker):
    """Verify explicit synchronization mechanism (MUST-FIX #3) prevents sequence collisions under concurrency."""
    job_id = "job_test_concurrency_1"
    total_concurrent_emissions = 100

    async def emit_worker(i: int):
        # Small jitter to interleave coroutines
        await asyncio.sleep(0.001 * (i % 5))
        return broker.emit(
            job_id=job_id,
            event_type=TransformationEventType.TASK_STARTED,
            payload={"worker_id": i},
        )

    # Launch 100 simultaneous emissions
    events = await asyncio.gather(*(emit_worker(i) for i in range(total_concurrent_emissions)))

    assert len(events) == total_concurrent_emissions
    sequences = [e.sequence for e in events]

    # Sequences must be strictly unique, strictly positive, with zero collisions
    assert len(set(sequences)) == total_concurrent_emissions
    assert min(sequences) == 1
    assert max(sequences) == total_concurrent_emissions


def test_in_memory_ring_buffer_process_lifetime_limits(broker):
    """Verify ring buffer caps storage per job at max_events_per_job, trimming oldest (MUST-FIX #1)."""
    job_id = "job_test_buffer_cap"
    # Broker fixture has max_events_per_job=50
    for i in range(75):
        broker.emit(job_id, TransformationEventType.TASK_STARTED, {"index": i})

    events = broker.replay(job_id)
    assert len(events) == 50
    # Oldest 25 were discarded, remaining should have indices 25 to 74
    assert events[0].payload["index"] == 25
    assert events[-1].payload["index"] == 74
    # But sequence numbers reflect true monotonically allocated count
    assert events[-1].sequence == 75


def test_event_replay_with_after_sequence(broker):
    """Verify event replay filters strictly by after_sequence parameter."""
    job_id = "job_test_replay"
    for i in range(10):
        broker.emit(job_id, TransformationEventType.TASK_STARTED, {"step": i})

    # Replay after sequence 7
    replayed = broker.replay(job_id, after_sequence=7)
    assert len(replayed) == 3
    assert [e.sequence for e in replayed] == [8, 9, 10]


@pytest.mark.asyncio
async def test_stream_job_events_yields_events_and_terminates(broker):
    """Verify async generator stream_job_events yields live SSE strings and completes on terminal events."""
    job_id = "job_test_stream_1"

    async def consumer():
        collected_events = []
        async for sse_text in broker.stream_job_events(job_id, poll_timeout=0.2):
            collected_events.append(sse_text)
            if "job.completed" in sse_text:
                break
        return collected_events

    async def producer():
        await asyncio.sleep(0.01)
        broker.emit(job_id, TransformationEventType.JOB_STARTED, {"start": True})
        await asyncio.sleep(0.01)
        broker.emit(job_id, TransformationEventType.TASK_COMPLETED, {"task": 1})
        await asyncio.sleep(0.01)
        broker.emit(job_id, TransformationEventType.JOB_COMPLETED, {"done": True})

    consumer_task = asyncio.create_task(consumer())
    await producer()
    results = await asyncio.wait_for(consumer_task, timeout=2.0)

    assert len(results) == 3
    assert "event: job.started" in results[0]
    assert "event: task.completed" in results[1]
    assert "event: job.completed" in results[2]


from app.db.init import init_db


def test_job_created_emitted_by_job_service_not_d6_5(tmp_path):
    """Verify job.created is emitted by JobService.create_job, and D6.5 does not duplicate it (MUST-FIX #2)."""
    db_path = str(tmp_path / "test_events.db")
    init_db(db_path)
    test_broker = TransformationEventBroker()
    job_svc = JobService(db_path=db_path)
    # Patch event_broker used in job_service and handoff
    job_svc.event_broker = test_broker
    handoff_svc = JobArtifactHandoffService(job_svc=job_svc, broker=test_broker)

    # 1. Create job via JobService
    job = job_svc.create_job(
        requested_formats=[OutputFormat.MARKDOWN],
        prompt="Test event emission separation",
    )

    events_after_creation = test_broker.replay(job.id)
    assert len(events_after_creation) == 1
    assert events_after_creation[0].event_type == TransformationEventType.JOB_CREATED
    assert events_after_creation[0].sequence == 1

    # 2. D6.5 marks job started
    handoff_svc.on_job_started(job.id)

    events_after_started = test_broker.replay(job.id)
    assert len(events_after_started) == 2
    # Ensure NO duplicate job.created was emitted!
    assert events_after_started[0].event_type == TransformationEventType.JOB_CREATED
    assert events_after_started[1].event_type == TransformationEventType.JOB_STARTED
    assert events_after_started[1].sequence == 2
