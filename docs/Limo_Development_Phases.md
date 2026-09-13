# Limo Development Phases

## Development Methodology

Limo will follow a **Prototype Development Life Cycle**:

**Planning → Requirements → Development → Testing → Prototype Refinement**

The prototype is developed incrementally with real integrations and real observable outputs.

---

## D1 — Project Foundation

**Goal:** Establish a clean, reproducible development environment.

**Work:**
- Set up Limo repository and project structure.
- Configure frontend/backend environments.
- Install and verify GenOffice, OpenMontage, MoneyPrinterTurbo and required AI infrastructure.
- Configure environment variables and secrets safely.
- Define integration boundaries.
- Create project/repository documentation.

**Done when:** all required components start and can be independently verified.

---

## D2 — Frontend Refinement

**Goal:** Finalize the Limo conversational experience.

**Work:**
- Refine Limo Home, sidebar, navigation and chat.
- Refine composer and feature-selection pills.
- Refine new/active chat and history.
- Refine loading/status states.
- Refine artifact cards, preview, open and export interactions.
- Keep GenOffice Workspace as a separate view.
- Maintain one consistent visual system.

**Rules:**
- No emoji characters as application icons.
- Keep typography, spacing, colors, borders, radius, icons and animations consistent.
- UI must be component-based and state-driven.

**Done when:** frontend interactions work using real application state; no backend implementation is required yet.

---

## D3 — Backend Core

**Goal:** Build the application backend foundation.

**Work:**
- FastAPI structure.
- Pydantic models.
- SQLite/repository layer.
- File/artifact storage.
- Projects.
- Sources.
- Chats/messages.
- Transformation jobs.
- Artifact metadata.
- Logging and error handling.
- API/service boundaries.

**Done when:** core data can be persisted, queried and tested.

---

## D4 — Limo Agent Infrastructure

**Goal:** Build the agent runtime and orchestration layer.

**Use Claude Code as the architectural/reference foundation where appropriate.**

**Work:**
- Agent loop.
- Context/session handling.
- Tool registry and schemas.
- Skills and progressive context loading.
- Hooks/guardrails.
- Subagents.
- Permissions/approvals.
- MCP boundaries.
- Iterative execution/retry.
- CLI diagnostics.

**Architecture:**

```text
Limo Agent
    ↓
Plan / Select / Delegate
    ↓
Tools / Skills / Subagents / MCP
    ↓
LangGraph
    ↓
Transformation workflow
```

**Rules:**
- Do not create competing workflow engines unnecessarily.
- Do not copy proprietary Claude Code source blindly.
- Every tool must execute a real operation.

**Done when:** the agent can receive a real request, select a real tool and return a real result.

---

## D5 — Content Ingestion & Understanding

**Goal:** Convert heterogeneous inputs into reusable structured information.

**Work:**
- Text.
- PDF/DOCX/XLSX.
- Images/OCR.
- Audio/video transcription where required.
- Metadata extraction.
- Source hashing.
- Normalization.
- Context understanding.
- Intent extraction.
- Entities/facts/claims/events/references.
- Canonical Content Model.
- Persistent indexing/retrieval.

**Important:**

```text
Process source when added/changed
→ Extract → Normalize → Index → Cache

New prompt
→ Retrieve relevant information
→ Execute
```

Never analyze all project files on every prompt.

**Done when:** real sources produce validated canonical information and unchanged sources can reuse cached/indexed data.

---

## D6 — Core Transformation & Generation

**Status:** `COMPLETED & FROZEN` (288/288 tests passing)  
**Detailed Specification:** [`Limo_D6_Complete_Specification_and_Master_Walkthrough.md`](file:///c:/Users/Admin/Downloads/LIMO/docs/Limo_D6_Complete_Specification_and_Master_Walkthrough.md)

**Goal:** Make required outputs generate real deliverables.

**Required outputs:**
- Advisory
- Executive Summary
- Presentation
- LinkedIn
- X/Twitter
- Infographic
- Video

**Work Accomplished:**
- D6.1: Deterministic Transformation Configuration Reconciliation (`TransformationConfigResolver`).
- D6.2: Output Planning Manifest & Route Assignment (`OutputPlanner`).
- D6.3: In-process Native Adapters (Markdown, HTML, LinkedIn, Twitter, SVG Infographics) & Staged Contracts (GenOffice, Video Engine).
- D6.4: Workflow Orchestration with sibling execution, retry idempotency, and cooperative task cancellation (`WorkflowOrchestrator`).
- D6.5: Job & Artifact Handoff with real task ratio progress, referential integrity verification, and SSE event streaming (`JobArtifactHandoffService`, `TransformationEventBroker`).
- D6.6: Comprehensive end-to-end verification and Ponytail audit cleanup (Zero fake artifacts on disk).

**Done when:** each supported output produces a real observable result from a real input, and external engines are guarded by versioned contracts. (Verified)

---

## D7 — GenOffice Integration

**Status:** `D7.1 COMPLETED & VERIFIED` | `D7.2 FROZEN & LOCKED` | `D7.3–D7.5 PLANNED`  
**D7.1 Specification & Walkthrough:** [`Limo_D7_1_Automation_Interface_Walkthrough.md`](file:///c:/Users/Admin/Downloads/LIMO/docs/Limo_D7_1_Automation_Interface_Walkthrough.md)  
**D7.2 Implementation Plan:** [`D7.2_Implementation_Plan.md`](file:///c:/Users/Admin/Downloads/LIMO/docs/D7.2_Implementation_Plan.md)  
**Goal:** Connect Limo to the actual GenOffice system without recreating its capabilities.

**Flow:**

```text
Limo Chat
→ Feature selection
→ AI request
→ Real GenOffice generation workflow
→ Real file
→ Artifact registration
→ Preview
→ Open/Edit in GenOffice
→ Save/update
```

**Work:**
- Define Limo ↔ GenOffice contract.
- Trace actual GenOffice agent/tool/IPC entry points.
- Build a real bridge/adapter.
- Route DOCX → Docs.
- Route PPTX → Slides.
- Route XLSX → Sheets.
- Route PDF/Markdown to supported GenOffice views.
- Handle save/update/version events.
- Connect edits to provenance.

**Strict rule:** never create a fake Python/TypeScript implementation that imitates GenOffice.

**Done when:** a real Limo request produces a real GenOffice-generated artifact and opens that exact artifact in the correct editor.

---

## D8 — Video Engine Integration

**Goal:** Integrate the already-tested OpenMontage + MoneyPrinterTurbo pipeline.

**Work:**
- Connect Limo video requests.
- Use OpenMontage for production.
- Use MoneyPrinterTurbo for configured narration/TTS.
- Generate subtitles and media.
- Register final MP4 as a Limo artifact.
- Return real progress and results.

**Done when:** a real Limo request produces a playable, validated video artifact.

---

## D9 — Jobs & Streaming

**Goal:** Support long-running transformations reliably.

**Work:**
- Durable background jobs.
- Persistent job states.
- Progress reporting.
- Cancellation.
- Crash recovery.
- Persistent event history.
- SSE streaming.
- Last-Event-ID replay.
- Agent/tool/generator events.
- Safe public execution summaries.

**Done when:** users can start, monitor, reconnect to and complete real long-running jobs.

---

## D10 — Artifact, Preview & Versioning

**Goal:** Make artifacts first-class objects.

**Work:**
- Artifact registration.
- Real previews/thumbnails.
- Artifact cards.
- Download/export.
- Versioning.
- Source/job relationships.
- GenOffice editing relationships.
- Save/update handling.

**Flow:**

```text
Generate
→ Artifact v1
→ Preview
→ Edit
→ Save
→ Artifact v2
```

**Done when:** the complete lifecycle works using real data.

---

## D11 — Validation, Security & Provenance

**Goal:** Ensure outputs are valid, secure and traceable.

**Work:**
- Structural validation.
- Content/fact validation.
- Safe tool execution.
- File/path isolation.
- Secret protection.
- External API protection.
- SHA-256 hashing.
- Source-to-output traceability.
- Version provenance.
- Audit trail.
- Blockchain-backed provenance where required.

**Done when:** artifacts have verifiable integrity/provenance and unsafe operations are rejected.

---

## D12 — Full REST/API & Client Integration

**Goal:** Connect all real backend functionality to the Limo desktop application.

**APIs:**
```text
/projects
/sources
/chats
/transform
/artifacts
/provenance
/health
```

**Work:**
- Chat messages.
- Transformation submission.
- Job status.
- SSE.
- Artifact retrieval.
- Preview.
- Export.
- GenOffice actions.

**Done when:** Limo UI operates using real backend data with no production mocks.

---

## D13 — Full Testing & Verification

**Goal:** Verify complete functionality through real execution.

```text
Unit
→ Integration
→ Runtime
→ End-to-End
```

**Test:**
- Frontend typecheck/build.
- Backend/API.
- Agent/tools/skills.
- Generators.
- GenOffice integration.
- OpenMontage/MPT.
- Jobs/SSE.
- Validation/provenance.
- Complete user journeys.

**Critical flows:**

```text
Prompt → Agent → DOCX → Artifact → GenOffice

Prompt → Agent → PPTX → Artifact → GenOffice Slides

Prompt → OpenMontage + MPT → MP4 → Artifact
```

**Done when:** real flows pass repeatedly without mock success.

---

## D14 — Prototype Refinement

**Goal:** Improve the working prototype using real test results.

**Work:**
- Fix integration failures.
- Remove remaining mocks.
- Improve error handling.
- Improve latency and context usage.
- Improve generation quality.
- Improve UI consistency.
- Improve agent reliability.
- Improve previews.
- Improve recovery.

**Done when:** the prototype is stable enough for repeated demonstration.

---

## D15 — Final Prototype & Demonstration

**Goal:** Prepare the complete prototype for evaluation.

**Work:**
- Final integration test.
- Final build/package.
- Demo scenarios.
- Setup instructions.
- Architecture documentation.
- Testing documentation.
- Known limitations.
- Technical presentation.
- Demo video.

**Final product flow:**

```text
Source / Prompt
→ Limo Chat
→ Agent
→ Understand
→ Transform
→ Generate
→ Validate
→ Artifact
→ Preview
→ Edit in GenOffice / Preview Video
→ Export
→ Provenance
```

---

# Development Rules

1. **No fake pipelines.**
2. **No simulated GenOffice or OpenMontage behavior.**
3. **No hardcoded production data.**
4. **No fake progress or fake artifacts.**
5. **Never claim completion without a real observable result.**
6. **Inspect existing implementations before creating integrations.**
7. **Reuse working GenOffice and OpenMontage capabilities.**
8. **Keep frontend dynamic and API/state driven.**
9. **Never expose private model chain-of-thought.**
10. **Keep development CLI-testable.**
11. **Keep Limo Chat and GenOffice Workspace separate.**
12. **Never use emoji characters as application icons.**
13. **Keep the entire UI visually and interactively consistent.**
14. **Implement one real vertical slice before expanding the same architecture.**

---

# Priority Vertical Slice

The first complete product path should be:

```text
Prompt
→ Limo Agent
→ Real transformation
→ Real DOCX
→ Real artifact
→ Preview
→ Open in GenOffice
```

After this works reliably:

```text
DOCX
→ PPTX
→ XLSX
→ PDF / Markdown
→ Video
→ Multi-output workflows
```
