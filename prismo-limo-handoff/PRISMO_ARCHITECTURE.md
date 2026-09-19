# Prismo Architecture: Host Application Perspective

> **Purpose**: Describes the structural boundaries, data flow, and subsystems of Prismo for engineers integrating it into host applications.  
> **Key Principle**: Prismo is a standalone design engine. Limo is a client/host. Prismo must not contain Limo-specific UI logic.

---

## 1. System Topology

```
┌────────────────────────────────────────────────────────────────────────┐
│                          HOST APPLICATIONS                             │
│                                                                        │
│   ┌───────────────────────┐   ┌─────────────────┐   ┌──────────────┐   │
│   │       Limo Chat       │   │    Prismo CLI   │   │  Studio UI   │   │
│   │ (External Application)│   │  (app/cli/)     │   │ (app/server/)│   │
│   └───────────┬───────────┘   └────────┬────────┘   └───────┬──────┘   │
└───────────────┼────────────────────────┼────────────────────┼──────────┘
                │                        │                    │
                ▼                        ▼                    ▼
══════════════════════════════════════════════════════════════════════════
  PUBLIC ENGINE BOUNDARY: core/index.ts
  - StandaloneDesignEngine (Facade)
  - Contracts: GenerationInput, RefinementInput, GenerationResult, ExportOptions
  - Geometry: SupportedRatio, CanonicalDimension, RatioState
  - Seams: ModelProvider, AgentToolRegistry
══════════════════════════════════════════════════════════════════════════
                │
                ▼
┌────────────────────────────────────────────────────────────────────────┐
│                           CORE SUBSYSTEMS                              │
│                                                                        │
│  ┌───────────────────────┐   ┌────────────────────────┐                │
│  │     PosterEngine      │──▶│     PromptComposer     │                │
│  │ (Generation Pipeline) │   │ (Hallmark Disciplines) │                │
│  └───────────┬───────────┘   └────────────────────────┘                │
│              │                                                         │
│              ├──▶ ┌─────────────────────────────────────────┐          │
│              │    │ RatioPrecedenceCoordinator & Tools      │          │
│              │    │ (User Explicit > Agent Tool > Default)  │          │
│              │    └─────────────────────────────────────────┘          │
│              │                                                         │
│              ├──▶ ┌─────────────────────────────────────────┐          │
│              │    │ ModelProvider Seam                      │          │
│              │    │ (Gemini Multi-Account Pool OR Host LLM) │          │
│              │    └─────────────────────────────────────────┘          │
│              │                                                         │
│              ├──▶ ┌─────────────────────────────────────────┐          │
│              │    │ AssetProviderManager                    │          │
│              │    │ (Unsplash / Pexels / Pixabay / Local)   │          │
│              │    └─────────────────────────────────────────┘          │
│              │                                                         │
│              ├──▶ ┌─────────────────────────────────────────┐          │
│              │    │ ArtifactValidator (Quality Gate)        │          │
│              │    │ (Anti-Slop, Dark Scrims, Layout Ratios) │          │
│              │    └─────────────────────────────────────────┘          │
│              │                                                         │
│              ├──▶ ┌─────────────────────────────────────────┐          │
│              │    │ WorkspaceManager & VersioningEngine     │          │
│              │    │ (Disk Projects, Diff Snapshots, Rollback│          │
│              │    └─────────────────────────────────────────┘          │
│              │                                                         │
│              └──▶ ┌─────────────────────────────────────────┐          │
│                   │ HeadlessExporter (Non-blocking Chrome)  │          │
│                   │ (Rasterization, Magic Bytes & Headers)  │          │
│                   └─────────────────────────────────────────┘          │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Layer-by-Layer Responsibilities

### Layer 1: Public Facade (`core/engine.ts` & `core/index.ts`)
- **Status**: **PUBLIC / STABLE**
- Exposes `StandaloneDesignEngine` implementing `DesignEngine`.
- Coordinates all internal subsystems and exposes clean, typed async methods (`generate`, `refine`, `export`, `preview`, `inspect`, `rollback`).
- Keeps internal dependencies (`PosterEngine`, `WorkspaceManager`, `GeminiApiClient`) completely private.

### Layer 2: Generation Engine (`core/generation/poster.ts`)
- **Status**: **INTERNAL / PRIVATE**
- Houses the multi-phase poster generation pipeline:
  1. Ratio Precedence Evaluation.
  2. Bounded Agent Tool Loop for Geometry Decision.
  3. Reference Study & Semantic Visual Intent Analysis (`image_required` vs `image_not_wanted`).
  4. Prompt Composition with Hallmark Art Direction Disciplines.
  5. Code Block Parsing (`index.html` and `styles.css`).
  6. Mechanical Linking & Dynamic Asset Resolution.
  7. Quality Validation & Bounded Correction Turn.
  8. Directional Dark Scrim Safety Net.
  9. File Diffing, Turn Logging, and Version Checkpointing.

### Layer 3: Model Provider Seam (`core/contracts/models.ts` & `core/providers/`)
- **Status**: **PUBLIC INTERFACE / PLUGGABLE BACKEND**
- Default implementation: `GeminiProviderManager`, providing round-robin account rotation across a pool of Gemini API keys, circuit breaker failover on HTTP 429, and exponential backoff.
- Extensibility point: Any class implementing `ModelProvider` can be passed to `StandaloneDesignEngine({ modelProvider: customProvider })`.

### Layer 4: Geometry & Ratio Capability (`core/geometry/`)
- **Status**: **PUBLIC CONTRACTS / INTERNAL ENFORCEMENT**
- `CANONICAL_RATIO_REGISTRY` holds immutable metadata for all 5 canonical ratios.
- `ProjectRatioCapability` tracks project-scoped aspect ratio states.
- `RatioPrecedenceCoordinator` enforces:
  $$\text{Explicit User Intent} > \text{Agent Tool Decision} > \text{Default (3:4)}$$
- `AgentToolRegistry` formats function-calling schemas for the model and dispatches typed tool execution without leaking `projectId` to the LLM.

### Layer 5: Design Knowledge & Typography Director (`core/design-system/` & `core/design-knowledge/`)
- **Status**: **INTERNAL / PRIVATE**
- `TypographyDirector`: Programmatically selects font pairings from 19 verified open-source Google fonts based on domain context. Strictly enforces the prohibition of monospace fonts on headlines and numbers.
- `ReferenceStudyEngine`: Categorizes subject prompts into visual design DNA profiles (e.g. brutalist technical, luxury editorial, cinematic photograph).

### Layer 6: Validation & Anti-Slop Gate (`core/validation/validator.ts`)
- **Status**: **INTERNAL / PRIVATE**
- Programmatic quality gate checking:
  - Strict pixel dimensions and canonical aspect ratio matching.
  - Image contract compliance (fails if image was requested but `<img ...>` is absent).
  - Micro-UI / micro-text violations (text < 22px).
  - Repeated card proliferation (enforces &le; 2 cards).
  - Directional dark scrim verification on full-bleed imagery.

### Layer 7: Headless Exporter (`core/export/exporter.ts`)
- **Status**: **INTERNAL / PRIVATE**
- Promise-wrapped, non-blocking asynchronous execution of headless Chrome/Chromium.
- Validates raster image headers (PNG/JPEG magic bytes, width/height chunks) to ensure output files are non-corrupted and dimensionally accurate.
- Supports cooperative cancellation via `AbortSignal`.

### Layer 8: Workspace & Versioning (`core/workspace/`)
- **Status**: **INTERNAL / PRIVATE**
- `WorkspaceManager`: Project directory management under `<dataDir>/projects/<projectId>/`.
- `FilesystemDiffEngine`: Computes created, modified, and deleted files per turn.
- `VersioningEngine`: Checkpoints project files on disk, enabling multi-version inspection and rollbacks.

---

## 3. Public vs Internal Summary Matrix

| Module / Symbol | Classification | Host Application Guidance |
| :--- | :---: | :--- |
| `StandaloneDesignEngine` | **PUBLIC** | **Import directly**. The only engine class Limo needs. |
| `GenerationInput`, `GenerationResult` | **PUBLIC** | **Import directly**. Use for request/response typing. |
| `ExportOptions`, `ExportResult` | **PUBLIC** | **Import directly**. Use for raster export requests. |
| `ModelProvider` | **PUBLIC** | **Implement if needed**. Use if supplying an in-house LLM. |
| `AgentToolRegistry` | **PUBLIC** | **Inspect if needed**. Available if Limo manages tool dispatching. |
| `PosterEngine` | **INTERNAL** | **Do NOT import**. Private implementation detail of the facade. |
| `WorkspaceManager` | **INTERNAL** | **Do NOT import**. Use `engine.getArtifacts()` instead. |
| `GeminiProviderManager` | **INTERNAL** | **Do NOT import**. Handled internally via constructor keys. |
| `PreviewServer` | **INTERNAL** | **Do NOT import**. Disable via `enablePreviewServer: false`. |
| `HeadlessExporter` | **INTERNAL** | **Do NOT import**. Call `engine.export()` instead. |
| `ArtifactValidator` | **INTERNAL** | **Do NOT import**. Automatically runs during `engine.generate()`. |
