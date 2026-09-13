# Software Requirements Specification (SRS)
## Limo — AI-Powered Content Transformation Workspace

**Document Status:** Baseline SRS  
**Version:** 1.0  
**Application:** Limo  
**Primary Client:** Desktop application  
**Primary Backend:** Python + FastAPI  
**AI Orchestration:** Limo Agent + LangGraph  
**Document Editing:** GenOffice  
**Video Engine:** OpenMontage + MoneyPrinterTurbo  

---

## 1. Introduction

### 1.1 Purpose

This document defines the functional and non-functional requirements for **Limo**, an AI-powered content transformation workspace.

Limo accepts source information in different forms, understands the source context and user intent, and transforms the information into one or more communication artefacts selected by the operator.

The original problem statement describes the need to transform information such as news articles, reports, advisories, threat intelligence, policy documents, research papers, announcements, incident reports, prompts, images and videos into specific communication artefacts through a simple and configurable interface.

### 1.2 Scope

Limo shall provide a common workflow:

```text
Source / Prompt
      ↓
Input Processing
      ↓
Context + Intent Understanding
      ↓
Canonical Content Representation
      ↓
Output Selection + Configuration
      ↓
Transformation
      ↓
Validation
      ↓
Artifact Creation
      ↓
Preview
      ↓
Edit / Export
```

The system shall support generation of multiple output types from the same source content.

### 1.3 Intended Users

The primary user is an **operator/content creator** who needs to transform source information into communication artefacts efficiently.

The design may support future team/project workflows, but authentication and enterprise identity management are outside the current core scope unless separately specified.

### 1.4 Source of Requirements

The core transformation requirements are derived from the supplied SIH problem statement. Project-specific architecture and integration requirements in this document are additional implementation requirements for the Limo solution.

---

# 2. Product Overview

Limo is a conversational AI workspace in which the operator can:

1. Start a conversation.
2. Provide source content or contextual information.
3. Select one or more desired output types.
4. Configure generation parameters.
5. Let the agent execute the required transformation workflow.
6. Receive real generated artefacts inside the conversation.
7. Preview the artefacts.
8. Open editable artefacts in GenOffice.
9. Export/download the final result.

The Limo conversational interface and GenOffice Workspace are separate application views.

### 2.1 Core Product Flow

```text
Limo Chat
   ↓
User Request + Source
   ↓
Limo Agent
   ↓
Content Understanding
   ↓
Canonical Content Model
   ↓
Transformation / Generator
   ↓
Validation
   ↓
Artifact
   ↓
Limo Artifact Card
   ├── Preview
   ├── Open/Edit in GenOffice
   └── Export
```

---

# 3. Functional Requirements

## 3.1 Source Input and Ingestion

### FR-001 — Accept Text Input
The system shall allow the operator to provide high-quality English text directly through the Limo composer.

### FR-002 — Accept File Sources
The system shall accept supported document and media files, including applicable documents, reports, articles, images and videos.

### FR-003 — Accept Multiple Sources
The system shall allow multiple source items to be associated with one transformation request.

### FR-004 — Normalize Sources
The system shall extract and normalize usable information from supported source formats before transformation.

### FR-005 — Preserve Source Identity
The system shall retain source metadata and a source identifier throughout the transformation lifecycle.

### FR-006 — Source Hashing
The system shall be able to calculate a cryptographic hash for a source so that source versions can be distinguished.

---

## 3.2 Content Understanding

### FR-007 — Understand Context
The system shall analyze submitted information and identify relevant context.

### FR-008 — Determine Intent
The system shall infer the intended communication objective from the operator request and selected output configuration.

### FR-009 — Extract Structured Information
The system shall extract relevant entities, facts, claims, events, references and contextual information where applicable.

### FR-010 — Canonical Content Model
The system shall convert normalized source information into a structured canonical representation that can be reused by multiple output generators.

### FR-011 — Multi-Source Synthesis
The system shall combine information from multiple sources into a common canonical representation when a transformation request contains multiple sources.

---

## 3.3 Generation Configuration

### FR-012 — Select Output Type
The operator shall be able to select one or more desired output types.

### FR-013 — Target Audience
The operator shall be able to specify or use a target audience.

### FR-014 — Tone
The operator shall be able to specify the desired tone.

### FR-015 — Language
The operator shall be able to specify the output language where supported.

### FR-016 — Level of Detail
The operator shall be able to specify the required level of detail.

### FR-017 — Communication Objective
The operator shall be able to specify the communication objective.

### FR-018 — Content Style
The operator shall be able to specify the desired content style.

### FR-019 — Reusable Configuration
The system shall pass the selected configuration to the appropriate transformation workflow.

---

## 3.4 Output Transformation

### FR-020 — Multiple Deliverables
The system shall generate every output selected by the operator from the same source content.

### FR-021 — Advisory
If Advisory is selected, the system shall generate a structured advisory document.

### FR-022 — Executive Summary
If Executive Summary is selected, the system shall generate a concise executive briefing.

### FR-023 — Presentation
If Presentation is selected, the system shall generate presentation slides and speaker notes.

### FR-024 — LinkedIn Post
If LinkedIn Post is selected, the system shall generate a professional LinkedIn-ready post.

### FR-025 — X/Twitter
If X/Twitter is selected, the system shall generate platform-optimized posts or threads.

### FR-026 — Infographic
If Infographic is selected, the system shall generate infographic content, layout recommendations and key messaging.

### FR-027 — Video Package
If Video is selected, the system shall generate a complete video deliverable/package including script, storyboard, scene descriptions, narration, subtitles and visual recommendations, and the implementation shall produce the requested video output using the configured video-production pipeline.

### FR-028 — Output-Specific Parameters
The system shall apply output-specific generation rules in addition to the common generation configuration.

### FR-029 — Artifact Creation
Every successful output transformation shall result in a registered artifact.

---

## 3.5 AI Agent and Orchestration

### FR-030 — Request Planning
The Limo Agent shall interpret the operator request and determine the required actions.

### FR-031 — Tool Selection
The Limo Agent shall select appropriate tools/services for the requested task.

### FR-032 — Skill Selection
The Limo Agent shall load relevant domain-specific skills/instructions when required.

### FR-033 — Workflow Orchestration
The system shall use a structured workflow for multi-step transformations.

### FR-034 — Delegation
The agent shall be able to delegate suitable complex tasks to specialized workers/subagents.

### FR-035 — External Tool Integration
The system shall support external or replaceable capabilities through defined integration boundaries where appropriate.

### FR-036 — Iterative Execution
The agent shall be able to retry or correct a transformation when validation identifies a correctable failure.

---

## 3.6 Transformation Jobs

### FR-037 — Background Execution
Long-running transformations shall execute as background jobs without blocking normal client/API operation.

### FR-038 — Job State
Each transformation job shall maintain a lifecycle state, such as queued, processing, completed, failed or cancelled.

### FR-039 — Job Progress
The system shall provide meaningful progress/status information for long-running transformations.

### FR-040 — Job Cancellation
The operator shall be able to cancel a running job where cancellation is supported.

### FR-041 — Job Recovery
Interrupted jobs shall be detected and handled safely after application/backend restart.

---

## 3.7 Chat and Conversation

### FR-042 — New Chat
The operator shall be able to start a new conversation.

### FR-043 — Persistent Conversations
The system shall persist chat sessions and message history.

### FR-044 — Recent Chats
The system shall display recent conversations.

### FR-045 — Contextual Follow-Up
The operator shall be able to continue a transformation within an existing conversation.

### FR-046 — Streamed Responses
The system shall support streamed response/status events for long-running agent activity.

### FR-047 — Public Execution Status
The chat shall display safe execution summaries such as current stage, tool activity summaries and artifact creation status.

### FR-048 — No Private Reasoning Exposure
The system shall not expose or persist private model chain-of-thought as user-facing reasoning content.

---

## 3.8 Artifact Management

### FR-049 — Artifact Registration
Generated files shall be registered with metadata including identifier, type, format, source relationship and version.

### FR-050 — Artifact Preview
The system shall provide an in-application preview where a preview representation is available.

### FR-051 — Artifact Card
Generated artefacts shall appear as interactive cards in the Limo conversation.

### FR-052 — Download/Export
The operator shall be able to export or download generated artefacts.

### FR-053 — Artifact Versioning
The system shall support version tracking for modified artefacts.

### FR-054 — Source-to-Artifact Traceability
The system shall maintain the relationship between source content, transformation job and generated artifact.

### FR-055 — Artifact Validation
The system shall validate the generated artifact before finalization.

### FR-056 — Artifact Integrity
The system shall be able to verify that the stored artifact has not been altered unexpectedly.

---

## 3.9 GenOffice Workspace and Editing

### FR-057 — Separate Workspace
GenOffice Workspace shall remain a separate application view from the Limo conversational home.

### FR-058 — AI-First GenOffice Feature Flow
Selecting an editor capability such as Docs or Slides from the Limo workflow shall first provide an AI/plugin creation experience rather than immediately opening the editor.

### FR-059 — Real Artifact Generation
The requested document must be created by the real generation workflow; the system shall not simulate document creation with mock data.

### FR-060 — Preview Before Editing
The operator shall be able to preview a generated artifact in Limo before choosing to edit it.

### FR-061 — Open in GenOffice
The operator shall be able to open the generated file in the appropriate GenOffice editor.

### FR-062 — Format-Based Routing
The system shall route supported file formats to the corresponding editor, such as DOCX to Docs, PPTX to Slides and XLSX to Sheets.

### FR-063 — Save and Update
When supported by the editor integration, user modifications shall update the associated artifact/version state.

---

## 3.10 Video Production

### FR-064 — Video Engine
Video production shall use the integrated OpenMontage + MoneyPrinterTurbo pipeline rather than a second custom video-production engine.

### FR-065 — Narration
The video workflow shall support narration through the configured MoneyPrinterTurbo TTS integration.

### FR-066 — Video Assets
The video workflow shall support configured stock/visual asset sources.

### FR-067 — Subtitles
The video workflow shall produce synchronized subtitles.

### FR-068 — Final Video Artifact
The completed video shall be registered as a Limo artifact and made available in the Limo conversation.

---

## 3.11 Validation

### FR-069 — Structural Validation
The system shall verify that generated files are structurally valid for their expected format.

### FR-070 — Content Validation
The system shall validate generated content against required structural/content rules.

### FR-071 — Fact Grounding
Where applicable, the system shall identify unsupported or insufficiently grounded claims.

### FR-072 — Validation Result
The system shall store and expose validation status and relevant warnings/errors.

---

## 3.12 Provenance and Auditability

### FR-073 — Provenance Record
The system shall associate generated artifacts with their source, transformation and generation metadata.

### FR-074 — Content Hash
The system shall calculate a cryptographic hash for artifact content.

### FR-075 — Version Relationship
The system shall preserve parent/previous-version relationships when an artifact is modified.

### FR-076 — Audit Trail
The system shall maintain an auditable record of important artifact lifecycle events.

### FR-077 — Tamper Detection
The system shall be able to detect unexpected changes to content covered by its integrity mechanism.

### FR-078 — Blockchain Extension
The architecture shall support a future blockchain-backed tamper-evident provenance layer without requiring changes to the core transformation model.

---

## 3.13 Projects and Organization

### FR-079 — Projects
The system shall allow artefacts, conversations and source materials to be associated with a project.

### FR-080 — Project Filtering
The system shall support filtering project-associated conversations, sources and artefacts.

### FR-081 — Project Continuity
The system shall allow the operator to continue work on a project using previously stored context and artefacts.

---

# 4. Non-Functional Requirements

## 4.1 Security

### NFR-001 — Secret Protection
API keys, credentials and secrets shall not be hardcoded into application source or exposed to the frontend.

### NFR-002 — File Boundary Protection
File-processing operations shall restrict access to approved workspace/storage locations.

### NFR-003 — Input Safety
Uploaded or externally retrieved content shall be treated as untrusted input.

### NFR-004 — Tool Safety
Agent tools shall execute through controlled interfaces with validation and appropriate permission/guard checks.

### NFR-005 — Path Traversal Protection
File operations shall prevent path traversal outside approved directories.

### NFR-006 — External Request Safety
External API calls shall use controlled providers/configuration and shall not expose private credentials to client code.

### NFR-007 — Auditability
Security-sensitive actions shall be logged sufficiently to support investigation without exposing secrets.

---

## 4.2 Performance

### NFR-008 — Non-Blocking Interaction
Long-running generation tasks shall not block normal UI/API responsiveness.

### NFR-009 — Background Processing
CPU-intensive or external-process work shall execute outside the primary asynchronous request path where necessary.

### NFR-010 — Incremental Streaming
Long-running operations shall provide incremental status/events rather than requiring the client to wait for one final response.

### NFR-011 — Context Efficiency
The agent shall avoid unnecessarily loading all project files or all source content into every model request.

### NFR-012 — Reuse/Caching
The system should reuse previously extracted/indexed information when source content has not changed.

---

## 4.3 Reliability and Recovery

### NFR-013 — Persistent Job State
Transformation job state shall survive normal process restarts through persistence.

### NFR-014 — SSE Replay
Disconnected clients shall be able to reconnect and replay missed persisted events.

### NFR-015 — Graceful Failure
A failed generator or external integration shall produce a clear failure state without corrupting unrelated jobs or artefacts.

### NFR-016 — Cancellation Integrity
Cancelled jobs shall be distinguishable from failed jobs.

### NFR-017 — Atomic Artifact Writes
Generated files shall be written safely so partially written files are not registered as completed artefacts.

### NFR-018 — Data Consistency
Database metadata and artifact filesystem state shall remain consistent or provide recoverable reconciliation.

---

## 4.4 Usability

### NFR-019 — Conversational Workflow
The primary creation experience shall be understandable without requiring the operator to manually configure complex pipelines.

### NFR-020 — Clear State
The UI shall clearly distinguish idle, processing, completed, failed and cancelled states.

### NFR-021 — Predictable Navigation
Limo Chat and GenOffice Workspace shall remain visually and functionally distinct while providing clear transitions between them.

### NFR-022 — Accessible Feedback
Actions such as generation, preview, edit and export shall provide clear feedback.

### NFR-023 — Consistent Design
The Limo interface shall use a consistent component, typography, icon and interaction system.

---

## 4.5 Maintainability

### NFR-024 — Modular Architecture
Generators, ingestion handlers, agent tools, skills, validation and external integrations shall remain modular.

### NFR-025 — Separation of Concerns
API routes shall remain thin and business logic shall reside in service/domain layers.

### NFR-026 — Provider Replaceability
AI providers, research providers, TTS providers and external engines should be replaceable without rewriting unrelated components.

### NFR-027 — GenOffice Isolation
The Limo platform shall integrate with GenOffice through defined interfaces rather than duplicating its editors.

### NFR-028 — Video Engine Isolation
OpenMontage + MoneyPrinterTurbo shall remain replaceable behind a defined video integration boundary.

---

## 4.6 Scalability

### NFR-029 — Multiple Jobs
The backend shall support multiple transformation jobs without one long-running task preventing other requests from being served.

### NFR-030 — Multiple Outputs
The architecture shall support a transformation request producing multiple artefacts from one canonical source representation.

### NFR-031 — Extensible Generators
Additional output types shall be addable without redesigning the entire pipeline.

### NFR-032 — Extensible Tools
Additional agent tools and integrations shall be addable through defined tool contracts.

---

## 4.7 Data Integrity and Provenance

### NFR-033 — Deterministic Metadata
Artifact metadata required for provenance shall be stored consistently.

### NFR-034 — Cryptographic Integrity
Integrity checks shall use cryptographic hashes over the relevant source/artifact data.

### NFR-035 — Version Traceability
Every user-modified artifact version shall remain traceable to its prior version where supported.

### NFR-036 — Immutable Audit Evidence
Audit records intended as provenance evidence shall not be silently overwritten.

---

## 4.8 Testability

### NFR-037 — Unit Testing
Core models, generators, services and utilities shall be unit-testable independently.

### NFR-038 — Integration Testing
API, agent, job, storage, artifact and editor-integration boundaries shall support integration tests.

### NFR-039 — End-to-End Testing
Major user journeys shall be testable from request through real artifact creation.

### NFR-040 — CLI Verification
The project shall provide CLI-based verification for type/lint checks, tests, health checks and important integration diagnostics.

### NFR-041 — No Mock Completion
A feature shall not be considered complete only because a mocked response or simulated UI flow works.

---

# 5. System Interfaces

## 5.1 Limo UI ↔ Electron

The React renderer shall communicate with Electron-native functionality through the approved preload/IPC boundary where native operations are required.

## 5.2 Limo UI ↔ Backend

The desktop client shall communicate with FastAPI through defined API contracts for chat, projects, sources, transformations, jobs, artefacts and provenance.

## 5.3 Agent ↔ Tools

The Limo Agent shall invoke typed tools with validated parameters and structured results.

## 5.4 Agent ↔ LangGraph

The agent shall use LangGraph for structured, multi-step transformation workflows.

## 5.5 Backend ↔ GenOffice

The backend/client integration shall use artefact/file-based contracts so that the actual GenOffice editor can open the real generated file.

## 5.6 Backend ↔ OpenMontage/MoneyPrinterTurbo

Video generation shall use the verified OpenMontage + MoneyPrinterTurbo integration through an isolated service/adapter boundary.

---

# 6. Core Data Requirements

## 6.1 Project

```text
Project
- id
- name
- metadata
- created_at
- updated_at
```

## 6.2 Source

```text
Source
- id
- project_id
- name
- type
- location
- extracted_content/reference
- source_hash
- created_at
```

## 6.3 Chat Session

```text
Chat
- id
- project_id
- title
- metadata
- created_at
- updated_at
```

## 6.4 Message

```text
Message
- id
- chat_id
- role
- content
- attachments
- artifact_ids
- public execution summaries
- created_at
```

Private model chain-of-thought shall not be persisted as user-facing message content.

## 6.5 Transformation Job

```text
TransformationJob
- id
- project_id
- session_id
- requested_formats
- configuration
- state
- progress
- current_stage
- error
- artifact_ids
- timestamps
```

## 6.6 Canonical Content

The canonical content representation may contain:

```text
- source references
- context
- intent
- entities
- facts
- claims
- events
- references
- recommendations
```

## 6.7 Artifact

```text
Artifact
- id
- project_id
- job_id
- type
- format
- title
- storage reference/path
- source relationship
- content hash
- version
- validation result
- provenance metadata
- created_at
```

## 6.8 Provenance Record

```text
Provenance
- artifact_id
- source hash
- canonical/content hash
- artifact hash
- model/provider information
- configuration hash
- parent version
- timestamp
- lifecycle event
```

---

# 7. Business Rules

### BR-001
A transformation request shall generate only the output types selected or clearly requested by the operator.

### BR-002
When multiple outputs are selected, they shall derive from the same source/canonical representation unless an explicit transformation step requires otherwise.

### BR-003
Generated artefacts shall not be represented as successfully completed until the actual physical output exists and validation has completed.

### BR-004
The UI shall never use fabricated content, fake artefact paths or simulated generation results as a substitute for real backend output.

### BR-005
Preview content shall represent the actual generated artifact or an approved representation of that artifact.

### BR-006
Opening an artifact for editing shall use the actual generated file.

### BR-007
Changing a source shall not silently reuse stale derived content when the source hash indicates that the source has changed.

### BR-008
User cancellation shall be represented separately from execution failure.

### BR-009
Validation failures shall be visible to the transformation workflow and may trigger retry/correction where supported.

### BR-010
Provenance shall be updated when a tracked artifact version changes.

---

# 8. Main User Acceptance Flows

## 8.1 Generate a Document

```text
Open Limo
→ Enter prompt
→ Select Docs
→ Submit
→ Real transformation runs
→ Real DOCX created
→ Artifact card appears
→ Preview
→ Open
→ GenOffice Docs opens the generated file
```

## 8.2 Generate Multiple Outputs

```text
Provide source
→ Select Advisory + Presentation + Social
→ Submit
→ One transformation context
→ Multiple real artefacts
→ Each displayed in chat
→ Preview/Edit/Export independently
```

## 8.3 Generate Video

```text
Provide source
→ Select Video
→ Agent creates video request
→ OpenMontage + MoneyPrinterTurbo runs
→ Real MP4 + narration + subtitles produced
→ Artifact appears in Limo
→ Preview / Export
```

## 8.4 Continue Editing

```text
Generated artifact
→ Open in GenOffice
→ User edits
→ Save
→ New/updated artifact version
→ Provenance updated
```

---

# 9. Out of Scope / Not Mandatory from the Original Problem Statement

The following are implementation/product decisions rather than explicit platform requirements in the original statement:

- Mandatory Android/iOS support
- Mandatory offline deployment
- Mandatory cloud hosting
- A specific cloud provider
- A specific frontend framework
- A specific backend framework
- A specific LLM provider
- A specific blockchain network
- Mandatory authentication/identity provider
- Recreating GenOffice editors from scratch

These may be added as product requirements later if needed.

---

# 10. Technical Constraints and Dependencies

The current target architecture is:

```text
React + TypeScript + Electron
          ↓
       FastAPI
          ↓
      Limo Agent
          ↓
       LangGraph
          ↓
   Tools / Generators
     ↙     ↓      ↘
GenOffice  AI   OpenMontage
                 +
                MPT
          ↓
 Validation
          ↓
 Provenance
          ↓
 SQLite + File Storage
```

Claude Code is used as an architectural reference for agent concepts such as tool systems, skills, hooks, subagents and MCP. Its proprietary source is not part of the Limo application.

---

# 11. Acceptance Criteria Summary

Limo shall be considered functionally ready for the core transformation workflow when:

1. A real source/prompt can be submitted.
2. The system understands the request and determines the requested output.
3. A real transformation workflow executes.
4. A real output artifact is created.
5. The artifact is registered and traceable to its source/job.
6. The real artifact appears in the Limo conversation.
7. The artifact can be previewed where supported.
8. Editable document artefacts open in the correct GenOffice editor.
9. Long-running work reports real progress.
10. Validation and provenance are recorded.
11. No mock/hardcoded production data is required for the flow.
12. The complete flow passes automated and real end-to-end tests.

---

# 12. Requirement Traceability

The most important original problem capabilities map to:

| Problem Capability | Requirement IDs |
|---|---|
| Accept text/documents/images/videos/context | FR-001 to FR-006 |
| Understand context and intent | FR-007 to FR-011 |
| Select one or more outputs | FR-012, FR-020 |
| Audience/tone/language/detail/objective/style | FR-013 to FR-019 |
| Video | FR-027, FR-064 to FR-068 |
| LinkedIn | FR-024 |
| Twitter/X | FR-025 |
| Advisory | FR-021 |
| Infographic | FR-026 |
| Executive Summary | FR-022 |
| Presentation + speaker notes | FR-023 |
| Multiple outputs from one source | FR-020 |
| Preview/edit/export | FR-050 to FR-063 |
| Job execution/streaming | FR-037 to FR-041 |
| Validation | FR-055, FR-069 to FR-072 |
| Provenance/integrity | FR-073 to FR-078 |
| Security/reliability/performance | NFR-001 to NFR-041 |

---

## 13. Final Requirement Statement

Limo shall provide a configurable, AI-powered content transformation workflow that accepts heterogeneous source information, understands the source context and operator intent, generates one or more selected communication artefacts, validates the results, maintains traceability and provenance, and allows the operator to preview, edit and export the resulting artefacts through an integrated conversational workspace and GenOffice editing environment.
