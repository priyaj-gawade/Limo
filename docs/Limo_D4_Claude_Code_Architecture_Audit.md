# Limo Phase D4.1 — Claude Code Audit & Agent Architecture Specification

## 1. Executive Summary & Objective

The objective of **Phase D4** is to construct the real **Limo Agent Runtime** utilizing proven architectural design patterns from Anthropic's **Claude Code**, while maintaining Limo's FastAPI backend, SQLite database, and sandboxed storage as the authoritative sources of truth.

Phase **D4.1** establishes the comprehensive audit of the Claude Code architecture located in `external/claude-code/`, mapping its core abstractions into Limo equivalents and defining exact integration points into Limo's Phase D3 services.

```text
User Request
     ↓
FastAPI Router / Chat Service
     ↓
Limo Agent Runtime (D4)
  ├── Agent Loop & Context Manager (D4.2)
  ├── Typed Tools & Discoverable Skills (D4.3)
  ├── Lifecycle Hooks, Permissions & Subagents (D4.4)
  ├── MCP & Backend Adapters (D4.5)
  └── LangGraph Deterministic Execution Engine (D4.6)
     ↓
Limo Core Services (Phase D3)
  [ProjectService, SourceService, ChatService, JobService, ArtifactService, StorageService, TransformService]
     ↓
SQLite Database (data/limo.db) & Storage Sandbox (data/)
```

---

## 2. Claude Code Architecture Audit

An in-depth study of `external/claude-code` reveals 11 foundational capabilities that make Claude Code reliable, token-efficient, and maintainable:

| # | Claude Code Capability | Mechanism in Claude Code | Architectural Significance |
|---|---|---|---|
| 1 | **Agent Loop** | Asynchronous turn-based loop: `Reason → Select Tool → Execute → Observe → Iterate` with max-turn guard. | Prevents runaway recursion, allows iterative self-correction, stops when task is complete. |
| 2 | **Tools** | Strongly typed, single-purpose actions with execution timeout and structured result objects. | Decouples reasoning from side effects; provides deterministic boundaries. |
| 3 | **Tool Schemas** | JSONSchema definitions specifying properties, types, requirements, and field descriptions. | Ensures LLMs receive strict JSON contracts for function calling without hallucinating parameter names. |
| 4 | **Skills** | Modular directories with `SKILL.md` frontmatter, markdown instructions, and bundled resources (`scripts/`, `references/`). | Enables specialized domain expertise without hardcoding custom logic in the core prompt. |
| 5 | **Progressive Disclosure** | 3-tier loading: Metadata in prompt → Full `SKILL.md` on trigger → Deep references loaded on-demand. | Protects context window; prevents loading unnecessary documentation into every request. |
| 6 | **Hooks** | Event interceptors (`PreToolUse`, `PostToolUse`, `SessionStart`, `Stop`, `SubagentStop`). | Enforces safety, audit logging, redaction, and compliance policies before/after actions. |
| 7 | **Permissions** | Granular permission model (`Read`, `Write`, `Execute`, `External Request`, `Artifact Creation`). | Restricts high-risk actions, prevents unauthorized access, and scopes subagents. |
| 8 | **Subagents** | Isolated child loops with dedicated role, scoped tools, and isolated context window. | Keeps complex sub-tasks (research, fact-checking, validation) from polluting main context. |
| 9 | **MCP Integration** | Model Context Protocol (`.mcp.json`) exposing external tools over stdio/HTTP. | Standardizes integration with external processes and tools without custom adapters. |
| 10 | **Context Management** | Rolling session window, token budget tracking, clean turn state separation. | Prevents context overflow; preserves critical system rules across long conversational threads. |
| 11 | **CLI Diagnostics** | Diagnostic subcommands to inspect tools, validate skills, test hooks, and run probe loops. | Provides immediate, verifiable feedback for developers without needing frontend UI. |

---

## 3. Detailed Capability Mapping: Claude Code → Limo Equivalent → Integration Point

Below is the definitive capability mapping required by Phase D4.1:

### 3.1 Agent Loop
- **Claude Code**: Multi-turn async loop that alternates between reasoning and executing tool calls until a terminal response or turn limit is reached.
- **Limo Equivalent**: `LimoAgentRuntime` & `AgentLoop` in `backend/app/agent/runtime.py`.
- **Integration Point**:
  - Invoked by `ChatService.send_message()` when conversational AI processing is active.
  - Invoked asynchronously by `TransformService` / `JobService` when processing transformation jobs.
  - Interacts directly with `ChatRepository` to store user and assistant messages, setting `execution_summary` on completion.
  - Strictly follows Limo Non-Negotiable Rule 4: Never exposes or persists private chain-of-thought.

### 3.2 Tools & Execution
- **Claude Code**: `BaseTool` classes exposing `name`, `description`, `execute(args) -> ToolResult`.
- **Limo Equivalent**: `BaseTool` and `ToolResult` in `backend/app/agent/tools/base.py`.
- **Integration Point**:
  - Tools wrap real Phase D3 business services:
    - `ProjectTool`: Wraps `ProjectService` (`create_project`, `get_project`, `list_projects`).
    - `SourceTool`: Wraps `SourceService` (`register_file_source`, `register_text_source`, `get_source`).
    - `ChatTool`: Wraps `ChatService` (`create_session`, `get_history`).
    - `TransformTool`: Wraps `TransformService` & `JobService` (`create_transform_contract`, `get_job`, `update_progress`).
    - `ArtifactTool`: Wraps `ArtifactService` (`register_artifact`, `get_artifact`, `list_artifacts`).
  - Follows Rule 1 & Rule 5: Zero fake tools, zero simulated pipeline logic.

### 3.3 Tool Schemas
- **Claude Code**: Standard JSON Schema objects passed to Anthropic/OpenAI tool call parameters.
- **Limo Equivalent**: Pydantic v2 `BaseModel` classes with automatic `model_json_schema()` generation.
- **Integration Point**:
  - Each tool defines an explicit Pydantic `args_schema`.
  - Inbound parameters from LLM function calls are validated through Pydantic before service execution, raising structured `BadRequestError` on validation failure.

### 3.4 Skills
- **Claude Code**: Directory containing `SKILL.md` with YAML frontmatter (`name`, `description`) and procedural instructions.
- **Limo Equivalent**: `SkillRegistry` and file-backed skill system in `backend/app/agent/skills/`.
- **Integration Point**:
  - Pre-packaged skills aligned with Limo's Feature Modes and SIH transformation formats:
    - `document_skill`: Rules for drafting, summarizing, and structuring professional documents.
    - `presentation_skill`: Guidelines for slide breakdown, speaker notes, and presentation themes.
    - `spreadsheet_skill`: Schema structuring, tabular data modeling, and calculations.
    - `video_skill`: Scripting, storyboard creation, and scene pacing.
    - `research_skill`: Deep query synthesis, evidence gathering, and claim extraction.
    - `validation_skill`: Fact-checking, hallucination detection, and source citation matching.
  - Discovered and registered dynamically on backend startup.

### 3.5 Progressive Disclosure
- **Claude Code**: Prompt injects only brief skill/tool manifests. On trigger, agent fetches the full `SKILL.md` or executes isolated helper scripts.
- **Limo Equivalent**: `AgentContextManager` 3-tier selective context loader in `backend/app/agent/context.py`.
- **Integration Point**:
  - Tier 1: Manifest with skill names and one-line triggers included in system prompt (~150 tokens).
  - Tier 2: Active skill instructions injected only when relevant mode is active (e.g. `docs`, `slides`, `video`).
  - Tier 3: Source excerpts and canonical intermediates loaded on-demand via `SourceService` queries rather than stuffing complete source files into context.
  - Strictly adheres to Non-Negotiable Rule 3: **Never read the whole project on every prompt.**

### 3.6 Lifecycle Hooks
- **Claude Code**: Event hooks (`PreToolUse`, `PostToolUse`, `SessionStart`, `Stop`, `SubagentStop`).
- **Limo Equivalent**: `HookRegistry` and async hook interfaces in `backend/app/agent/hooks/`.
- **Integration Point**:
  - `PreToolUseHook`: Validates parameters, checks security boundaries (path traversal, parameter sanitization).
  - `PostToolUseHook`: Masks sensitive data, records metrics, formats tool observation.
  - `PreArtifactCreationHook`: Verifies that content is non-empty and generated file format matches `OutputFormat`.
  - `PostArtifactCreationHook`: Triggers automatic provenance registration via `ArtifactService.record_provenance()` and citation validation via `ArtifactService.record_validation()`.
  - `StopHook`: Verifies that deliverables were actually produced before terminating.

### 3.7 Permissions
- **Claude Code**: Capability permissions (`Read`, `Write`, `Execute`, `External Request`).
- **Limo Equivalent**: `PermissionManager` and `PermissionPolicy` in `backend/app/agent/permissions/`.
- **Integration Point**:
  - Tools declare their `PermissionType`:
    - `READ`: Allowed automatically (querying SQLite, reading source metadata).
    - `WRITE`: Scoped strictly to the active project boundary and sandbox directory.
    - `TRANSFORM`: Validates user inputs against allowed `OutputFormat` values.
    - `EXTERNAL_DISPATCH`: Restricted to approved external adapter contracts (GenOffice IPC, OpenMontage worker).
  - Enforced in `Hook.PRE_TOOL_USE` before any underlying service method is invoked.

### 3.8 Subagents
- **Claude Code**: Bounded subagents configured with specialized system prompt, scoped tool whitelist, and isolated context window.
- **Limo Equivalent**: `SubagentCoordinator` and specialist agents in `backend/app/agent/subagents/`.
- **Integration Point**:
  - `ResearchAgent`: Restricted to reading ingested sources, querying canonical data points, and synthesizing background notes.
  - `ContentAnalysisAgent`: Performs extraction of entities, claims, facts, and timeline events to construct `CanonicalContent`.
  - `ValidationAgent`: Cross-references final deliverable claims against source hash digests and computes `hallucination_check_passed` and `score`.
  - Each subagent has its own turn limit (default 5) and cannot invoke destructive tools.

### 3.9 MCP (Model Context Protocol) Integration
- **Claude Code**: Bundles `.mcp.json` to spawn external tool servers over stdio or HTTP/SSE.
- **Limo Equivalent**: `MCPClientAdapter` in `backend/app/agent/mcp/`.
- **Integration Point**:
  - Standardizes external tool adapters for later phases:
    - Phase D5: GenOffice integration (document/presentation/spreadsheet generation).
    - Phase D7: OpenMontage + MoneyPrinterTurbo integration (video pipeline).
  - Normalizes MCP tool schemas into Limo's `BaseTool` registry so the agent uses a single uniform tool calling convention.

### 3.10 Context & Session Management
- **Claude Code**: Sliding message history window, token budgeting, smart truncation, turn tracking.
- **Limo Equivalent**: `AgentContextManager` in `backend/app/agent/context.py`.
- **Integration Point**:
  - Hydrated directly from `ChatRepository.get_messages(session_id)`.
  - Maintains total token budget (e.g. 8k-32k depending on model), compressing older turns while preserving:
    1. System prompt & foundational rules.
    2. Active Project metadata and deliverable requirements.
    3. Active Feature Mode instructions.
    4. Recent user requests, tool calls, and observations.
  - Appends assistant response turn upon agent loop completion.

### 3.11 CLI Diagnostics
- **Claude Code**: Direct terminal CLI commands for inspecting plugins, tools, and execution flows.
- **Limo Equivalent**: Extended `backend/app/cli.py` with `app.cli agent` subcommands.
- **Integration Point**:
  - `python -m app.cli agent inspect-tools`: Lists all registered tools, their schemas, permissions, and backing services.
  - `python -m app.cli agent inspect-skills`: Lists all discovered skills, triggers, and progressive disclosure tiers.
  - `python -m app.cli agent test-loop`: Runs a synthetic multi-step agent execution against real SQLite and storage, reporting turn-by-turn trace.

---

## 4. Architectural Boundaries & Non-Negotiable Rules

In accordance with `docs/rule.md` and `docs/Limo_D4_Agent_Infrastructure_Implementation_Plan.md`:

1. **No Fake Generators**: D4 implements the agent infrastructure and runtime reasoning engine. Actual document generation (GenOffice) and video synthesis (OpenMontage) belong strictly to Phase D5 and Phase D7.
2. **No Competitor to LangGraph**: LangGraph executes deterministic multi-step state machines. The Limo Agent plans, configures, and monitors the workflow, but does not replicate or compete with LangGraph.
3. **Strict Privacy**: Under no circumstance is private chain-of-thought reasoning exposed to the client or persisted to SQLite. Only user-facing `execution_summary` is recorded.
4. **Service-Layer Dominance**: Tools never access SQLite directly or bypass the service layer. Every tool calls a service in `backend/app/services/`.
5. **Progressive Disclosure**: Full documents or entire project directories must never be loaded into context on every user turn.

---

## 5. D4 Phase Breakdown & Sequence

The implementation of Phase D4 proceeds in the following sequential order:

- [x] **D4.1**: Claude Code Audit & Architecture Specification (This document).
- [ ] **D4.2**: Agent Core, Loop & Context Management (`runtime.py`, `context.py`, `loop.py`).
- [ ] **D4.3**: Tools Framework & Skill Registry (`BaseTool`, `ToolResult`, `SkillRegistry`, default tools wrapping D3 services).
- [ ] **D4.4**: Lifecycle Hooks, Granular Permissions & Specialist Subagents (`hooks/`, `permissions/`, `subagents/`).
- [ ] **D4.5**: MCP & External Boundary Adapters (`mcp/client.py`).
- [ ] **D4.6**: LangGraph Orchestration Bridge, Retrieval Abstraction & Public Execution Events (`retrieval/`, `events/`).
- [ ] **D4.7**: Automated Unit/Integration Tests & Real CLI Verification Probe (`tests/test_agent_*.py`, `verify_d4_master.py`).
