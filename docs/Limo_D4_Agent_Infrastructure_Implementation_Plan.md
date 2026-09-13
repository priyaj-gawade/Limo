# Limo D4 — Agent Infrastructure Implementation Plan

## Goal

Build the real **Limo Agent Runtime** using Claude Code-style architectural patterns, while keeping Limo's own backend/services as the source of truth.

Core flow:

```text
User Request
→ Limo Agent
→ Understand / Plan
→ Select Skill / Tool
→ Execute
→ Observe Result
→ Continue / Retry
→ Final Result
```

D4 builds the agent brain/runtime. It does **not** build the actual document/video generators.

---

## D4.1 — Claude Code Audit & Architecture

### Goal
Study the available Claude Code infrastructure and define what Limo will reuse/adapt.

Cover:
- Agent loop
- Tools
- Tool schemas
- Skills
- Progressive disclosure
- Hooks
- Permissions
- Subagents
- MCP
- Context/session handling
- CLI diagnostics

Create a mapping:

```text
Claude-style capability
→ Limo equivalent
→ integration point
```

No generator or frontend work.

---

## D4.2 — Agent Core & Context

### Goal
Implement the main agent execution loop and context manager.

Flow:

```text
Request
→ Load session/context
→ Understand
→ Plan
→ Select action
→ Execute
→ Observe
→ Continue / retry / complete
```

Context must support:
- chat history
- current request
- active feature mode
- relevant project/source context
- tool results
- artifact references
- token/context limits
- truncation/summarization
- session continuation

**Never reload the entire project for every prompt.**

---

## D4.3 — Tools & Skills

### Goal
Create the real execution interface for Limo capabilities.

### Tools
Implement:
- `BaseTool`
- structured `ToolResult`
- schemas
- registry
- discovery
- validation
- execution
- error handling

Tools wrap existing Limo services instead of recreating them.

Initial tools may cover:
- projects
- sources
- chats
- transformations
- jobs
- artifacts
- storage

### Skills
Implement:
- skill registry
- discovery
- trigger matching
- activation
- progressive loading

Example skill areas:

```text
document
presentation
spreadsheet
video
research
validation
```

---

## D4.4 — Hooks, Permissions & Subagents

### Hooks
Implement lifecycle hooks such as:

```text
Before Tool
After Tool
Before Artifact Creation
After Artifact Creation
Agent Error
Agent Stop
```

Use them for validation, safety, diagnostics and policy checks.

### Permissions
Define permissions for:

```text
Read
Write
Execute
External Request
Artifact Creation
```

Support approval for operations that require user authorization.

### Subagents
Create bounded specialist agents:

```text
Research Agent
Content Analysis Agent
Validation Agent
```

Each must have:
- dedicated role
- restricted tools
- clear input/output contract
- bounded execution

---

## D4.5 — MCP & Backend Integration

### Goal
Connect the agent runtime to real Limo services and external boundaries.

Internal services:

```text
ProjectService
SourceService
ChatService
JobService
ArtifactService
StorageService
TransformService
```

External boundaries:

```text
GenOffice
OpenMontage
MoneyPrinterTurbo
Web/research providers
```

Do not use undocumented shortcuts.

The agent should request capabilities through defined tools/interfaces, for example:

```text
generate_document
generate_presentation
generate_video
open_artifact
```

The actual GenOffice and video execution is implemented in their dedicated later phases.

---

## D4.6 — LangGraph, Retrieval & Events

### LangGraph

Keep the architectural separation:

```text
Limo Agent
→ plans/configures
→ LangGraph
→ executes deterministic workflow
```

Do not create a competing workflow engine.

### Retrieval

Implement a retrieval abstraction so the agent can:
- find relevant sources
- retrieve relevant chunks/metadata
- reuse cached information
- avoid unnecessary full-document loading

Do not force a specific vector database in D4 unless required.

### Events

Emit structured public execution events such as:

```text
agent.started
agent.thinking
tool.started
tool.completed
subagent.started
subagent.completed
workflow.started
workflow.completed
artifact.created
agent.failed
agent.completed
```

Expose only safe execution summaries. Never expose or persist private chain-of-thought.

---

## D4.7 — Testing & Real Verification

### Test

#### Agent
- loop execution
- context handling
- turn limits
- failures
- retry

#### Tools
- registration
- schemas
- discovery
- execution
- invalid input
- failure handling

#### Skills
- discovery
- matching
- progressive loading

#### Hooks
- execution
- rejection
- validation

#### Subagents
- delegation
- scoped tools
- result handling

#### Retrieval
- relevant retrieval
- caching
- unchanged-source reuse

#### LangGraph
- agent-to-graph invocation
- state passing

#### Events
- ordering
- schema
- public/private separation

### Real verification

Example:

```text
User
→ Limo Agent
→ Project Tool
→ real ProjectService
→ real SQLite record
→ real result
```

Then:

```text
User
→ Limo Agent
→ Source Tool
→ real SourceService
→ real stored source
→ real result
```

Then verify a multi-step request using multiple real tools.

No fake generators or simulated integrations.

---

# D4 Completion Criteria

D4 is complete only when:

- Agent loop works on real requests.
- Tools execute real Limo services.
- Skills are dynamically selected.
- Context is managed efficiently.
- Hooks and permissions work.
- Subagents execute bounded tasks.
- LangGraph can be invoked by the agent.
- Retrieval prevents unnecessary full-project loading.
- Events are observable and safe.
- Errors are explicit and diagnosable.
- Automated tests pass.
- Real CLI verification passes.

---

# D4 Boundaries

## Do NOT implement yet

- New frontend UI
- Canvas
- New document generators
- New spreadsheet/presentation generators
- New video engine
- Fake GenOffice pipeline
- Fake OpenMontage pipeline
- Final artifact preview UI
- Production blockchain integration

These belong to later phases.

---

# D4 Non-Negotiable Rules

1. No fake tools or fake pipelines.
2. No success without a real result.
3. Do not read the whole project on every prompt.
4. Never expose or persist private chain-of-thought.
5. Reuse D3 services instead of duplicating them.
6. Keep tools strongly typed.
7. Keep subagents scoped.
8. Keep LangGraph as the deterministic workflow engine.
9. Verify real execution before claiming completion.
10. Do not move to the next major capability until the current one is proven.

---

# Final Architecture

```text
Limo Chat
   ↓
Limo Agent
   ├── Context
   ├── Skills
   ├── Tools
   ├── Hooks
   ├── Permissions
   ├── Subagents
   └── MCP
         ↓
      LangGraph
         ↓
  Limo Services / Generators / GenOffice / Video Engine
```
