# Walkthrough — Phase D6.5: Job & Artifact Handoff

Phase D6.5 builds the lifecycle handoff layer that connects D6.4 workflow execution results to persistent `TransformationJob` state, real `Artifact` records, and ordered public lifecycle events, preparing the system for subsequent verification (D6.6) and frontend streaming (D9).

> [!IMPORTANT]
> **Roadmap Boundary & Scope Clarity**:
> - Phase D6 is **not** finished. D6.5 handles job and artifact handoff.
> - The final sub-phase of Phase D6 is:
>   - **D6.6**: Testing & Real Verification (comprehensive test suite across all 12 formats, performance validation, and zero-fake deliverable regression tests).
> - **External Engines Remain Guarded**: D7 (GenOffice) and D8 (Video Engine) remain strictly out of scope. D6.5 passively stages contracts into `configuration.format_overrides["blocked_contracts"]` without auto-dispatch or worker polling.
> - **Event Replay Scope**: D6.5 event replay is **process-lifetime only** (in-memory ring buffer). Durable restart-safe replay across worker processes is explicitly deferred to Phase D9.

---

## 1. Accomplished Work & Review Must-Fix Resolutions

### Resolution 1: Explicit Process-Lifetime Event Replay (MUST-FIX #1)
- **Design Decision**: `TransformationEventBroker` maintains an in-memory ring buffer of up to 200 events per job (`max_buffer_per_job=200`).
- **Explicit Boundary**: Documented and verified that D6.5 replay is strictly process-lifetime. Restart-safe, durable event persistence will be introduced in Phase D9.
- **Replay API**: `broker.replay(job_id, after_sequence=X)` and `broker.get_job_events(job_id, after_sequence=X)` allow clients to replay missed events based on `sequence`.

### Resolution 2: Job Creation Layer Owns `job.created` (MUST-FIX #2)
- **Lifecycle Separation**:
  - `JobService.create_job()` emits the initial `TransformationEventType.JOB_CREATED` event.
  - `JobArtifactHandoffService.on_job_started()` emits `TransformationEventType.JOB_STARTED` onward.
- **Result**: Zero duplicate `job.created` events are emitted during workflow execution.

### Resolution 3: Concurrency Protection for Event Sequencing (MUST-FIX #3)
- **Atomic Sequencing**: Synchronized with per-job locks (`threading.Lock` managed per `job_id` under a meta-lock) to guarantee strictly monotonic sequences (`1, 2, 3...`) even when sibling tasks emit events simultaneously from concurrent coroutines.
- **Verified**: 100 simultaneous async event emissions yielded zero collisions and strictly unique monotonic sequences.

### Resolution 4: Passive Contract Staging Without Auto-Dispatch (MUST-FIX #4)
- **No Background Polling or Queueing**: Blocked contracts (`GenOfficePayload`, `VideoEnginePayload`) are passively staged into `job.configuration.format_overrides["blocked_contracts"]`.
- **Handoff Contract Retrieval**: Added `handoff_svc.get_staged_contracts(job_id)` to inspect staged contracts without triggering any background execution or external API calls.

### Resolution 5: Decoupled Task-Based Progress Semantics (MUST-FIX #5)
- **Formula**: `progress = completed_deliverables / total_deliverables` (real task ratio).
- **Independent State**: Lifecycle status (`state`: `COMPLETED`, `WAITING_EXTERNAL`, `PARTIALLY_COMPLETED`, `FAILED`, `CANCELLED`) is independent of progress.
- **Rule**: A job with 1 completed and 1 failed deliverable has `progress = 0.5` and `state = PARTIALLY_COMPLETED` (or `FAILED`), never interpreting progress as a "success score".

### Architectural Recommendation: Lightweight SSE Generation
- **Separation from Transport**: SSE formatting is implemented via `TransformationLifecycleEvent.to_sse_frame()` and `broker.stream_job_events(job_id, after_sequence, poll_timeout)`.
- **Pure Async Generator**: Exposes standard wire frames (`id: <event_id>\nevent: <type>\ndata: <json>\n\n`) without coupling to FastAPI endpoints or WebSocket transports (which remain thin concerns for Phase D9).

---

## 2. Core Components Implemented

### Component 1: Transformation Lifecycle Event Models
- **`backend/app/models/transformation_events.py`**:
  - `TransformationEventType`: Strongly-typed enum (`job.created`, `job.started`, `task.started`, `task.completed`, `task.failed`, `artifact.created`, `job.completed`, `job.waiting_external`, `job.partially_completed`, `job.failed`, `job.cancelled`).
  - `TransformationLifecycleEvent`: Validated Pydantic model with `event_id` (`evt_` prefix), `sequence`, `job_id`, UTC `timestamp`, and sanitized `payload`.
  - `to_sse_frame()`: Formats standard Server-Sent Events frames.
- **`backend/app/core/ids.py`**:
  - Added `generate_event_id()` producing stable IDs with `evt_` prefix.
- **`backend/app/models/enums.py`**:
  - Extended `JobState` with `WAITING_EXTERNAL` and `PARTIALLY_COMPLETED`.

### Component 2: Transformation Event Broker
- **`backend/app/services/transformation/event_broker.py`**:
  - `TransformationEventBroker`: Thread-safe, atomic per-job sequence allocation.
  - In-memory ring buffer (up to 200 events/job) with automatic oldest-event trimming.
  - Pub/sub distribution for sync and async listeners.
  - `sanitize_public_payload`: Strict zero-leakage scrubber stripping API keys, tokens, system prompts, chains of thought, tracebacks, passwords, and local file paths.
  - `stream_job_events`: Async generator yielding SSE frames with catch-up replay and live queue listening.

### Component 3: Job & Artifact Handoff Service
- **`backend/app/services/transformation/handoff.py`**:
  - `JobArtifactHandoffService`:
    - `on_job_started(job_id)`: Marks job `PROCESSING` and emits `job.started`. Idempotent for already terminal jobs.
    - `on_task_started(job_id, ...)`: Emits `task.started`.
    - `on_task_completed(job_id, ...)`: Emits `task.completed` and `artifact.created`.
    - `on_task_failed(job_id, ...)`: Emits `task.failed` with safe error text.
    - `handoff_workflow_result(job_id, result)`: Persists final job state, links artifacts, stages contracts, calculates exact progress, and emits terminal event (`job.completed`, `job.waiting_external`, etc.).
    - `get_staged_contracts(job_id)`: Reads staged contracts.
    - `verify_job_artifact_linkage(job_id)`: Bidirectional referential integrity check comparing SQLite job artifact IDs, `Artifact` records, physical storage file existence, and cryptographic SHA-256 hashes.

### Component 4: Orchestrator & Transform Service Integration
- **`backend/app/services/transformation/workflow_orchestrator.py`**:
  - Integrated `handoff_svc` callbacks at each deliverable task boundary (`on_task_started`, `on_task_completed`, `on_task_failed`).
- **`backend/app/services/transform_service.py`**:
  - `orchestrate_transformation()` delegates directly to `handoff_svc.on_job_started()` and `handoff_svc.handoff_workflow_result()`.
- **`backend/app/services/job_service.py`**:
  - `create_job()` emits `TransformationEventType.JOB_CREATED`.
  - `update_progress()` supports optional `configuration` updating to atomically persist staged contracts in SQLite without schema migration.

---

## 3. Verification Results

### Automated Test Suite
Ran `.venv\Scripts\python.exe -m pytest -q`:
```text
........................................................................ [ 25%]
........................................................................ [ 51%]
........................................................................ [ 77%]
.............................................................            [100%]
277 passed in 19.10s
```

### Dedicated Phase D6.5 Test Coverage (17 new tests)
Ran `.venv\Scripts\python.exe -m pytest -v tests/test_d6_transformation_events.py tests/test_d6_event_broker.py tests/test_d6_job_handoff.py`:
```text
tests/test_d6_transformation_events.py::test_transformation_event_type_enumeration PASSED [  5%]
tests/test_d6_transformation_events.py::test_transformation_lifecycle_event_creation_and_fields PASSED [ 11%]
tests/test_d6_transformation_events.py::test_sanitize_event_payload_scrubs_sensitive_keys PASSED [ 17%]
tests/test_d6_transformation_events.py::test_to_sse_frame_formatting PASSED [ 23%]
tests/test_d6_event_broker.py::test_monotonic_sequence_allocation PASSED [ 29%]
tests/test_d6_event_broker.py::test_concurrent_emission_atomic_sequences_no_collision PASSED [ 35%]
tests/test_d6_event_broker.py::test_in_memory_ring_buffer_process_lifetime_limits PASSED [ 41%]
tests/test_d6_event_broker.py::test_event_replay_with_after_sequence PASSED [ 47%]
tests/test_d6_event_broker.py::test_stream_job_events_yields_events_and_terminates PASSED [ 52%]
tests/test_d6_event_broker.py::test_job_created_emitted_by_job_service_not_d6_5 PASSED [ 58%]
tests/test_d6_job_handoff.py::test_pure_native_handoff_completes_job_and_links_artifacts PASSED [ 64%]
tests/test_d6_job_handoff.py::test_pure_external_handoff_sets_waiting_external_zero_progress PASSED [ 70%]
tests/test_d6_job_handoff.py::test_mixed_workflow_handoff_sets_partially_completed_with_exact_ratio PASSED [ 76%]
tests/test_d6_job_handoff.py::test_progress_semantics_failed_tasks_decoupled_from_status PASSED [ 82%]
tests/test_d6_job_handoff.py::test_referential_integrity_detection_of_corrupted_or_missing_file PASSED [ 88%]
tests/test_d6_job_handoff.py::test_handoff_idempotency_prevents_duplicate_artifact_links PASSED [ 94%]
tests/test_d6_job_handoff.py::test_zero_fake_files_leak_to_disk_during_handoff PASSED [100%]
============================= 17 passed in 1.19s ==============================
```

**Total Test Count**: **277 passed, 0 failed, 0 skipped**.

---

## 4. Key Takeaways & Readiness for Phase D6.6

1. **Clean D6.4 → D6.5 Handoff**: `TransformationWorkflowResult` is cleanly mapped into SQLite `TransformationJob`, linking real physical `Artifact` records and staging blocked contracts.
2. **Deterministic, Concurrency-Safe Events**: Monotonic event sequences are strictly enforced across sibling tasks.
3. **Decoupled Progress**: `progress` measures real deliverable completion ratio (`completed / total`) independent of lifecycle state.
4. **Guarded Engines**: Blocked GenOffice / Video contracts remain cleanly staged for future phases without fake deliverables or premature dispatch.
5. **Phase D6.6 Ready**: The transformation pipeline is now fully prepared for Phase D6.6 (Testing & Real Verification).
