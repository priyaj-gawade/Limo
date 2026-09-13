# Walkthrough — Phase D6.4: Transformation Workflow Orchestration

Phase D6.4 completes the transformation workflow orchestration portion of D6, providing a unified, deterministic task scheduling and execution layer that coordinates native deliverable adapters and external engine contracts while strictly guarding future execution engines (GenOffice D7 and Video Engine D8).

> [!IMPORTANT]
> **Roadmap Boundary & D6 Status**:
> Phase D6 is **not** finished. D6.4 coordinates the transformation workflow. The remaining sub-phases are:
> - **D6.5**: Job & Artifact Handoff (broader job ↔ artifact lifecycle orchestration, event streaming, client UI links)
> - **D6.6**: Testing & Real Verification (end-to-end transformation suite across all formats)

---

## 1. Accomplished Work

### Component 1: Single Authoritative Execution Path
- **Unified Pipeline Architecture**:
  - Unified all execution behind one single entry point:
    `Agent / API` → `TransformService.orchestrate_transformation(job_id)` → `TransformationWorkflowOrchestrator.execute_job_workflow(job)` → `EngineRouter.dispatch()`.
  - `execute_deliverable()` now delegates internally to `orchestrator.execute_single_task()`.
  - `execute_native_deliverables()` delegates directly to `orchestrate_transformation()`.
  - Zero duplicate execution pipelines exist in the codebase.

### Component 2: Workflow Domain Models & State Machine
- **`backend/app/models/workflow.py`**:
  - `TaskStatus`: Strongly-typed lifecycle state (`PENDING`, `RUNNING`, `COMPLETED`, `BLOCKED`, `FAILED`, `SKIPPED`).
  - `DeliverableTask`: Individual deliverable work unit tracking execution state, timing, and sanitized error messages.
  - `TransformationWorkflow`: Overall execution state tracking the task queue and workflow lifecycle.
  - `TransformationWorkflowResult`: **Frozen, structured result model** (`ConfigDict(frozen=True)`) encapsulating completed artifacts, blocked contracts, failed tasks, and execution metrics.
- **`backend/app/models/enums.py`**:
  - Added dedicated `WorkflowStatus.WAITING_EXTERNAL` for pure external requests (e.g. `[PRESENTATION, VIDEO]`), ensuring unambiguous state tracking instead of misleading "partial" completion.
  - Added `WorkflowStatus.PARTIALLY_COMPLETED` and `WorkflowStatus.CANCELLED`.

### Component 3: Transformation Workflow Orchestrator
- **`backend/app/services/transformation/workflow_orchestrator.py`**:
  - **Direct CanonicalContent Sibling Execution**: Eliminated artificial inter-deliverable dependencies; all deliverables execute independently as siblings derived directly from `CanonicalContent`.
  - **Retry Idempotency**: Keyed by `(job_id, deliverable_id)`. Before retrying, verifies whether an intact artifact already exists in storage and database, avoiding duplicate files or orphaned records.
  - **Task-Boundary Cancellation**: Active native tasks finish their atomic (<50ms) write to preserve filesystem integrity, while all pending unstarted tasks transition to `SKIPPED`.
  - **Safe Error Reporting**: `task.error` exposes only sanitized, user-friendly error summaries. Full tracebacks and system paths are logged exclusively via `logger.exception()`.
  - **External Engine Guarding**: Builds versioned `GenOfficePayload` and `VideoEnginePayload` contracts via `EngineRouter.build_contract()`, marks tasks as `BLOCKED`, and generates **zero fake files**.

### Component 4: LangGraph Integration
- **`backend/app/agent/orchestration/bridge.py`**:
  - Added `register_default_generation_handler()`, connecting D4's `WorkflowStage.GENERATE` directly to `transform_service.orchestrate_transformation()`.
  - Preserves `LangGraphBridge` as the single macro-level pipeline bridge without creating a competing framework.

---

## 2. Verification Results

### Automated Test Suite
Ran `.venv\Scripts\python.exe -m pytest -q`:
```text
........................................................................ [ 27%]
........................................................................ [ 55%]
........................................................................ [ 83%]
............................................                             [100%]
260 passed in 18.03s
```
**Result**: **260/260 tests passed** (244 existing + 16 new D6.4 tests).

### Specific Test Coverage for D6.4:
1. **Workflow Models (`tests/test_d6_workflow_models.py`)**:
   - `test_deliverable_task_lifecycle_and_validation`: Validates task fields, lifecycle states, and `task_` ID prefix.
   - `test_deliverable_task_id_validation`: Enforces validation errors on malformed IDs.
   - `test_transformation_workflow_construction`: Tests workflow state tracking.
   - `test_transformation_workflow_result_frozen_immutability`: Confirms that mutating fields on `TransformationWorkflowResult` raises `ValidationError`.
   - `test_workflow_status_includes_waiting_external`: Verifies `WAITING_EXTERNAL`, `PARTIALLY_COMPLETED`, and `CANCELLED`.
2. **Workflow Orchestration (`tests/test_d6_workflow_orchestrator.py`)**:
   - `test_independent_task_execution_no_artificial_dag`: Confirms tasks execute independently from `CanonicalContent`.
   - `test_pure_native_workflow_completes`: Pure native workflow produces 5 verified files and status `COMPLETED`.
   - `test_pure_external_workflow_waiting_external`: Pure external workflow produces status `WAITING_EXTERNAL` and zero fake files.
   - `test_mixed_workflow_partially_completes`: Mixed native + external produces real `.md` file, blocked presentation contract, and status `PARTIALLY_COMPLETED`.
   - `test_retry_idempotency_prevents_duplicate_artifacts`: Proves re-running a job deliverable reuses the existing artifact identity without duplicate accumulation.
   - `test_task_error_is_safe_user_message`: Confirms `task.error` contains user-friendly text without leaking stack traces or internal paths.
   - `test_task_boundary_cancellation`: Proves cancellation transitions pending tasks to `SKIPPED` and workflow to `CANCELLED`.
   - `test_task_boundary_cancellation_prevents_newly_starting_tasks`: Verifies that mid-run cancellation allows the in-flight active task to finish and register its artifact, while explicitly preventing newly starting tasks from beginning (status `SKIPPED`, dispatch count = 1).
   - `test_cancelled_job_state_prevents_task_execution`: Proves that attempting to invoke `execute_job_workflow` or `execute_single_task` on an already cancelled job safely refuses execution without starting any tasks.
   - `test_snapshot_zero_fake_office_and_video_artifacts_during_orchestration`: Pre/post filesystem snapshot verifies **zero `.docx`, `.pptx`, `.xlsx`, or `.mp4` fake files exist**.
3. **LangGraph Bridge Integration (`tests/test_d6_workflow_bridge_integration.py`)**:
   - `test_langgraph_bridge_dispatches_generate_stage`: Dispatches `WorkflowStage.GENERATE` via `LangGraphBridge` and verifies `WorkflowState.stage_data["generate"]` contains the `TransformationWorkflowResult`.

---

## 3. Provenance & Workflow Outcome Matrix

| Deliverable Selection | Implemented Engine | Workflow Outcome Status | Physical Artifacts Generated | External Contracts Staged |
|---|---|---|---|---|
| Native Only (e.g. `MARKDOWN`, `HTML`, `LINKEDIN`) | Yes (D6.3 Adapters) | `COMPLETED` | Real `.md`, `.html` files with verified SHA-256 | None |
| External Only (e.g. `PRESENTATION`, `VIDEO`) | No (Guarded for D7/D8) | `WAITING_EXTERNAL` | **Zero fake files** | Typed `GenOfficePayload`, `VideoEnginePayload` |
| Mixed (e.g. `MARKDOWN` + `PRESENTATION`) | Native Yes, External No | `PARTIALLY_COMPLETED` | Real `.md` file created | Typed `GenOfficePayload` held |
| Cancelled mid-run | Yes/No | `CANCELLED` | Active task finishes atomically; pending `SKIPPED` | None for skipped tasks |
| System / synthesis error | N/A | `FAILED` | None | Sanitized error on `task.error` |
