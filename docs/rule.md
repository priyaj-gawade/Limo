Limo Development Rules
1. Core Rule

Build only real, working functionality. Never create a fake implementation to make a feature appear complete.

A feature is considered complete only when the actual execution path works and produces a real observable result.

2. No Fake Pipelines
Do not create Python/TypeScript scripts that imitate GenOffice, OpenMontage, or another existing system.
Do not return deterministic placeholder results as production results.
Do not simulate successful generation.
Do not create fake artifacts, fake progress, fake file paths, or fake API responses.
Never claim an integration works without testing the real integration.
3. Integration First, UI Second

Before implementing an integration:

Find real implementation
→ Identify real entry point
→ Trace execution
→ Define interface
→ Test independently
→ Integrate
→ Test end-to-end

Never invent an integration path when the existing repository already provides one.

4. GenOffice Rule

GenOffice is the real document editing/generation system.

Reuse its existing agent, tools, editors, IPC and file handling where appropriate.
Do not recreate GenOffice functionality in Limo.
Do not replace GenOffice with a custom fake generator.
A successful document operation must produce a real file through the actual GenOffice workflow.
DOCX, PPTX, XLSX, PDF, Markdown and other supported formats must route to the appropriate real GenOffice functionality.
5. OpenMontage + MoneyPrinterTurbo Rule
Use the existing OpenMontage + MoneyPrinterTurbo video pipeline.
Do not build another video-production pipeline that duplicates it.
Keep the integration behind a clean adapter/service boundary.
Validate that the final MP4 is actually produced.
6. Agent Rule

The Limo Agent should:

Understand
→ Plan
→ Select skill
→ Select tool
→ Execute
→ Validate
→ Retry if necessary
→ Produce artifact

Tools must execute real operations and return structured results.

7. Claude Code Rule

Claude Code may be used as the architectural/implementation foundation for agent capabilities where appropriate.

Useful concepts include:

Agent loop
Tools
Skills
Hooks
Subagents
Permissions
MCP
Context management
CLI verification

Do not introduce unnecessary duplication between the Claude-style agent layer and LangGraph.

8. LangGraph Rule

LangGraph is responsible for structured, multi-step transformation workflows.

Do not create multiple competing workflow/state machines that can disagree with each other.

9. Dynamic Data Rule

Never hardcode production data.

Do not hardcode:

Chats
Messages
Projects
Artifacts
File paths
Generation results
Progress
Status
User data

Use real API responses, repositories, services and application state.

10. Error Handling Rule

No silent failures.

Every important operation must provide:

request_id
job_id
component
status
error
logs
output/result

Failures must be visible to both the developer and the application where appropriate.

11. Verification Rule

Every feature must be tested at the correct level:

Unit Test
→ Integration Test
→ Real Runtime Test
→ End-to-End Test

A passing mock test is not proof that the real feature works.

12. CLI-First Rule

The project must remain easy for an AI coding agent to diagnose.

Maintain commands for:

Typecheck
Lint
Tests
Build
Health Check
Integration Check
End-to-End Verification

Prefer one master verification command where practical.

13. Repository Search Rule

Do not repeatedly scan the entire repository.

Before searching:

Read the project context/documentation.
Check the repository map.
Locate the relevant module.
Search only the required area.

Do not waste context on unrelated files.

14. Change Rule

Before changing existing code:

Understand existing behavior
→ Identify dependency
→ Make smallest required change
→ Test

Do not rewrite working systems without a clear reason.

Frontend Rules
Main Frontend Rule

Never use emoji characters as icons in the application UI.

Use proper icon components, SVGs, or the project's approved icon system.

UI Consistency Rule

Keep the entire Limo UI consistent.

Maintain consistent:

Typography
Font sizes
Spacing
Colors
Borders
Radius
Icons
Button styles
Hover states
Focus states
Loading states
Animations
Transitions

Do not introduce a new visual language for individual screens.

UI Fidelity Rule

When a UI reference has been approved:

Follow the approved structure.
Do not invent unrelated layouts.
Do not add unnecessary cards, buttons or panels.
Preserve established interaction patterns.
Dynamic UI Rule

The UI must be state-driven.

Backend State
→ Application State
→ UI

Not:

Hardcoded Data
→ UI
Real Artifact Rule

Artifact cards, thumbnails, previews, status and metadata must represent the actual generated artifact.

Frontend Completion Rule

A frontend feature is not complete just because it looks correct.

It must also:

Render correctly
→ use real state
→ call the correct API/IPC
→ handle loading
→ handle errors
→ handle empty state
→ handle success
Development Discipline
Never Do
Fake pipeline
Fake success
Fake GenOffice integration
Fake artifact
Fake progress
Silent fallback
Unverified assumption
Unnecessary rewrite
Repeated full-repository search
Always Do
Inspect
→ Understand
→ Implement smallest real path
→ Run
→ Observe actual result
→ Test
→ Fix
→ Verify
Definition of Done

A feature is DONE only when:

Real implementation
+ Real data
+ Real integration
+ Error handling
+ Automated verification
+ Real end-to-end result

No visual simulation counts as completion.