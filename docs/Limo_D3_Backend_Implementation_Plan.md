# Limo D3 — Backend Core Implementation Plan

## Phase Goal

Build the **real backend foundation** for Limo.

D3 provides the data, storage, services, and API contracts required by later Agent, Generation, GenOffice, OpenMontage, and frontend integration phases.

**D3 does not implement the Claude Code-style agent infrastructure. That belongs to D4.**

**Do not redesign or modify the completed Limo frontend.**

---

## Reference Documentation

Read these documents before implementation:

- `docs/raw_context.md` — original SIH problem statement and core functional requirements.
- `docs/Limo_SRS.md` — functional and non-functional requirements.
- `docs/Limo_Development_Phases.md` — development lifecycle and D3 scope.
- `docs/MASTER_PLAN.md` — overall architecture and project direction.
- `docs/rule.md` — mandatory development and anti-fake/anti-AI-slop rules.

Treat these documents as the project context. If documentation conflicts with the actual repository, inspect the code and document the discrepancy before making changes.

---

# D3.1 — Backend Foundation

### Goal
Establish a clean FastAPI backend structure.

### Work
- FastAPI application structure.
- Configuration/environment management.
- Development logging.
- Global error handling.
- CORS for the approved desktop development environment.
- Dependency management.
- Basic health endpoint.

### Done when
The backend starts cleanly and health checks succeed.

---

# D3.2 — Shared Data Models

### Goal
Define stable domain models used throughout Limo.

Create/verify Pydantic models for:

```text
Project
Source
ChatSession
Message
TransformationJob
GenerationConfig
CanonicalContent
Artifact
ArtifactVersion
ValidationResult
ProvenanceRecord
```

Requirements:
- Stable IDs.
- Explicit types/enums.
- Timestamps where required.
- Serialization/deserialization support.
- No duplicate definitions for the same domain entity.

---

# D3.3 — SQLite Storage Layer

### Goal
Provide persistent application storage.

Core entities:

```text
projects
sources
chats
messages
jobs
artifacts
artifact_versions
provenance
```

Requirements:
- Transactions.
- Foreign-key relationships.
- CRUD operations.
- Parameterized/safe queries.
- Reproducible database initialization/migration.
- No secrets stored in the database.

---

# D3.4 — File & Artifact Storage

### Goal
Provide reliable filesystem storage.

Use clear storage boundaries:

```text
data/
├── sources/
├── artifacts/
└── temp/
```

The storage layer must:
- Create directories safely.
- Prevent path traversal.
- Provide stable artifact references.
- Calculate SHA-256 when registering artifacts.
- Store size/format/location metadata.
- Restrict access to approved directories.

Do not allow arbitrary filesystem paths from untrusted API input.

---

# D3.5 — Project & Source Services

### Goal
Create reusable services for project and source management.

### Project Service
Support:
- Create.
- List.
- Get.
- Update where required.
- Delete.

### Source Service
Support:
- Register source.
- Store metadata.
- Associate with project.
- Store content/file reference.
- Calculate source hash.
- Retrieve.
- Delete safely.

Prepare sources for ingestion/indexing in D5.

---

# D3.6 — Chat & Message Services

### Goal
Persist ChatGPT-style Limo conversations.

Support:

```text
Create Chat
List Chats
Get Chat
Rename Chat
Delete Chat
Add Message
Retrieve History
```

Message data may include:
- role
- content
- attachments
- artifact references
- safe public execution summaries
- timestamps

**Never persist private model chain-of-thought.**

Do not implement the full agent conversation engine in D3.

---

# D3.7 — Transformation Job Model

### Goal
Create the persistent contract required by later background execution.

Store:

```text
job_id
project_id
session_id
requested_formats
configuration
state
progress
current_stage
error
artifact_ids
timestamps
```

Suggested states:

```text
queued
processing
completed
failed
cancelled
```

D3 only establishes the model and persistence.

Actual job execution and SSE belong to later phases.

---

# D3.8 — Artifact Service

### Goal
Make artifacts first-class backend entities.

Support:
- Register artifact.
- Get artifact.
- List artifacts.
- Filter by project/job.
- Calculate/store content hash.
- Store source/job relationships.
- Store type/format metadata.
- Store validation state.
- Store version information.

Do not register a successful artifact unless the referenced file actually exists.

---

# D3.9 — Generation Configuration

### Goal
Define the shared configuration contract for later generators.

Support:

```text
Audience
Tone
Language
Detail Level
Communication Objective
Content Style
```

Allow output-specific configuration without duplicating the shared configuration model.

---

# D3.10 — Basic API Contracts

### Goal
Expose core backend resources required by later phases.

Prepare:

```text
/api/v1/health

/api/v1/projects
/api/v1/sources
/api/v1/chats
/api/v1/artifacts
/api/v1/transform
```

D3 should expose data/resource contracts only.

**Do not implement AI generation here.**

**Do not create fake transformation results.**

---

# D3.11 — Service / Repository Separation

Use:

```text
FastAPI Router
      ↓
Service
      ↓
Repository / Storage
```

Rules:
- Routes handle HTTP concerns.
- Services handle business logic.
- Repositories handle persistence.
- File storage handles files.
- Models define contracts.

Do not place database logic directly inside route handlers.

---

# D3.12 — Error Handling & Diagnostics

Every backend operation must fail explicitly.

Use structured errors where appropriate:

```text
error_code
message
request_id
resource_id
```

Never silently swallow exceptions.

Logs should clearly identify:

```text
request
service
operation
status
error
```

Do not log secrets or unnecessary sensitive content.

---

# D3.13 — Automated Tests

Test:

### Models
- Valid input.
- Invalid input.
- Serialization.

### Storage
- Initialization.
- CRUD.
- Transactions.
- Relationships.

### Projects
- CRUD.

### Sources
- CRUD.
- Hashing.
- File references.

### Chats
- Session lifecycle.
- Message persistence.
- Ordering.

### Jobs
- State persistence.
- Artifact relationships.

### Artifacts
- Registration.
- Hashing.
- Metadata.
- Filtering.

### API
- Request validation.
- Response contracts.
- Status codes.
- Error handling.

Run the backend test suite using the repository's configured test command.

---

# D3.14 — Backend Verification

Manually verify:

```text
Start backend
→ Health check
→ Create project
→ Add source
→ Create chat
→ Add/read messages
→ Create job record
→ Register real test artifact
→ Retrieve artifact
→ Verify database persistence
```

No AI generation is required for D3.

---

# D3 Completion Criteria

D3 is complete only when:

- FastAPI starts successfully.
- SQLite persistence works.
- Core models are stable.
- Projects work.
- Sources work.
- Chats/messages work.
- Job records work.
- Artifact registration works.
- File storage is secure.
- Generation configuration exists.
- API contracts are documented/tested.
- Errors are observable.
- Automated tests pass.
- No mock production pipeline has been introduced.

---

# Explicitly NOT in D3

Do not implement:

- Claude Code-style agent runtime.
- Agent loop.
- Tools.
- Skills.
- Subagents.
- LangGraph workflows.
- AI generators.
- GenOffice integration.
- OpenMontage integration.
- MoneyPrinterTurbo integration.
- SSE job execution.
- Canvas.
- New frontend UI.
- Fake generation pipelines.

---

# D3 → D4 Handoff

D3 provides the stable foundation for:

```text
D4  Agent Infrastructure
↓
D5  Content Ingestion & Understanding
↓
D6  Transformation & Generation
↓
D7  GenOffice Integration
↓
D8  Video / OpenMontage + MPT
↓
D9  Jobs & SSE
↓
D10 Artifact / Preview / Versioning
↓
D11 Validation / Security / Provenance
↓
D12 Full API / Client Integration
↓
D13 Testing
↓
D14 Prototype Refinement
↓
D15 Final Prototype
```

The objective of D3 is **not to make the whole application functional**.

The objective is to make the backend foundation **stable, persistent, testable, and ready for the real agent and transformation layers**.
