# Prismo &rarr; Limo Master Handoff

> **Target Audience**: AI / software engineering agents integrating Prismo as a visual design capability inside the Limo chat platform.  
> **Authority**: Source code in `core/` is the sole source of truth.  
> **Status**: Headless, framework-neutral, fully decoupled from Studio UI and HTTP servers.

---

## 1. What Prismo Is

Prismo (formerly known internally as D8.7) is a **headless, programmatic graphic poster and visual design engine**. It takes natural-language design prompts and produces production-grade social infographic posters across canonical geometric aspect ratios.

Prismo produces real, editable web primitives:
- `index.html`: Fully semantic HTML marked with stable `data-od-id` hooks.
- `styles.css`: CSS containing layout geometry, typographic hierarchy, and directional dark scrims.
- `tokens.css` & `DESIGN.md`: Computed design-system tokens and design rationale.
- `output.png` / `output.jpg`: High-resolution headless browser raster exports.

### Target Role in Limo
```
User in Limo Chat
       ↓
Limo Chat Application (Host)
       ↓ (calls public boundary only)
Prismo Engine Facade (core/index.ts)
       ↓
Prompt Composition → Geometry Tool Gate → ModelProvider → Anti-Slop Validator → Headless Exporter
       ↓
Structured GenerationResult (runId, changedFiles, previewUrl, ratioState, diagnostics)
       ↓
Limo displays poster preview / sends artifacts to user
```

Prismo is **NOT** a full-stack web framework or chat application. Prismo is a **pure design capability**.

---

## 2. Current Supported Targets & Ratios

### Supported Target
- Currently supported target: `'poster'` (type `TargetType = 'poster'`).
- Website and multi-slide deck generation were separated/deprecated; the current engine focuses exclusively on single-artboard editorial posters.

### Supported Aspect Ratios
Prismo enforces **5 canonical aspect ratios** with integer-safe pixel dimensions:

| Aspect Ratio | Width &times; Height | Orientation | Primary Usage Notes |
| :---: | :---: | :---: | :--- |
| `3:4` | `1080px × 1440px` | Portrait | Default editorial hero, social feed, print |
| `9:16` | `1080px × 1920px` | Portrait | Mobile stories, Reels, vertical lockscreens |
| `16:9` | `1920px × 1080px` | Landscape | Keynote presentations, desktop widescreen displays |
| `1:1` | `1080px × 1080px` | Square | Social feed square, album art, focal badge |
| `4:3` | `1440px × 1080px` | Landscape | Classic screen display, landscape publication |

**Invariants**:
- **Default**: If no ratio is specified by the user or agent, Prismo defaults to `3:4` (`1080×1440`).
- **No Arbitrary Ratios**: Arbitrary dimensions (e.g. `2:3`, `21:9`) are rejected with an explicit error. Zero silent coercion.
- **Precedence**: `Explicit User > Agent Tool Decision > Default Fallback`.

---

## 3. Public Entrypoint & Architectural Seams

Limo must interact with Prismo **exclusively through `core/index.ts`**.

```typescript
import {
  StandaloneDesignEngine,
  type DesignEngine,
  type GenerationInput,
  type GenerationResult,
  type RefinementInput,
  type ExportOptions,
  type ExportResult,
  type ModelProvider
} from './core/index.ts';
```

### Decoupled Seams
1. **ModelProvider Seam**: Prismo does not require direct Gemini network calls. Limo can pass its own model provider via `options.modelProvider` (implementing the `ModelProvider` interface in `core/contracts/models.ts`).
2. **Headless Execution**: Setting `enablePreviewServer: false` and `autoExportPng: false` runs Prismo completely in-memory with zero port binding and zero auto-export overhead.
3. **Agent Tool Registry**: Ratio selection is exposed via function declarations (`AgentToolRegistry`), enabling LLMs to reason about geometry during generation turns.

---

## 4. Lifecycles

### A. Initialization Lifecycle
```typescript
const engine = new StandaloneDesignEngine({
  dataDir: '/path/to/limo/storage/prismo-data',
  geminiKeys: process.env.GEMINI_KEY ? [process.env.GEMINI_KEY] : [],
  modelProvider: limoManagedModelProvider, // Optional: bypass Gemini pool
  enablePreviewServer: false,              // Headless: no HTTP port opened
  autoExportPng: false                     // Headless: export on-demand
});
```

### B. Project Creation Lifecycle
```typescript
const project = await engine.createProject(
  'Project Name',
  'poster',
  'Optional initial instructions',
  'modern-dark' // Preset: 'modern-dark', 'amber-minimal', etc.
);
// Returns ProjectMetadata: id ('proj_...'), rootPath, version (1), etc.
```

### C. Generation Lifecycle
1. `engine.generate(input: GenerationInput)`:
   - Evaluates prompt for explicit ratio overrides.
   - If ratio is unconstrained, runs a bounded function-calling loop with `AgentToolRegistry` (`get_supported_ratios`, `set_ratio`).
   - Analyzes semantic visual intent via `ReferenceStudyEngine` (`image_required`, `image_helpful`, `image_not_wanted`).
   - Composes structured Hallmark art-direction prompt via `PromptComposer`.
   - Calls `ModelProvider` to emit `index.html` and `styles.css`.
   - Runs mechanical syntax and CSS coverage checks (with a bounded 1-turn correction if CSS is incomplete).
   - Resolves stock imagery (Unsplash/Pexels/Pixabay) if photography is required.
   - Programmatically gates output through `ArtifactValidator.validateAntiSlop()`.
   - Injects directional dark scrim (`.scrim-bottom`, `.scrim-top`, `.scrim-dual`) matching text coordinates.
   - Snapshots workspace filesystem and bumps version in `VersioningEngine`.
   - Returns structured `GenerationResult`.

### D. Refinement Lifecycle
1. `engine.refine(input: RefinementInput)`:
   - Accepts `instruction` and optional `targetElementId` (matching `data-od-id`).
   - Preserves active project ratio and existing design tokens.
   - Applies targeted edits to HTML/CSS.
   - Re-runs validation and snapshots a new version.
   - Returns updated `GenerationResult`.

### E. Export Lifecycle
1. `engine.export(projectId: string, options: ExportOptions)`:
   - Asynchronously launches headless Chromium/Chrome to capture high-res PNG or JPEG.
   - Validates output file binary headers (magic bytes) and dimensions.
   - Copies output to `<projectRoot>/output.png` and returns `ExportResult`.

### F. Cancellation Lifecycle
Every async operation (`generate`, `refine`, `export`) accepts an `AbortSignal`:
```typescript
const controller = new AbortController();
const promise = engine.generate({ projectId, prompt, signal: controller.signal });
controller.abort(); // Immediately rejects with AbortError without corrupting state
```

---

## 5. Artifact Flow

Outputs are saved in the project's workspace directory: `<dataDir>/projects/<projectId>/`.

| File | Purpose |
| :--- | :--- |
| `index.html` | Generated poster DOM with `data-od-id` tags for every editable element |
| `styles.css` | Complete stylesheet with layout, typography, scrims, and token bindings |
| `tokens.css` | CSS Custom Properties defining the active color palette and typography |
| `DESIGN.md` | Human-readable design system summary and archetype rationale |
| `metadata.json` | Project state: id, name, target, version, ratioState, timestamps |
| `output.png` | Canonical raster export (available when exported) |
| `.versions/` | Internal rollback checkpoints managed by `VersioningEngine` |

---

## 6. What Limo Owns vs What Prismo Owns

| Area | Limo (Host Application) Owns | Prismo (Engine) Owns |
| :--- | :--- | :--- |
| **User Interaction** | Chat UI, user message streaming, typing indicators | Nothing (pure headless) |
| **Message History** | Conversation database, user auth, session management | Project-scoped turn history in `SessionTracker` |
| **Rendering** | Embedding `output.png` or `file://` / iframe into chat | Headless Chrome raster export and DOM generation |
| **Model Credentials** | User API keys or host LLM proxy routing | Optional internal Gemini key pool rotation |
| **Design Rules** | Nothing (does not write CSS/HTML prompts) | Typography director, anti-slop rules, dark scrims |
| **Geometry** | Displays aspect ratio selector if desired | Enforces canonical dimensions, ratio state & locks |

---

## 7. What Limo Must NOT Import

To maintain clean architectural seams and prevent breakage during updates, Limo **MUST NOT** import:
- `core/generation/poster.ts` (`PosterEngine` internals)
- `core/workspace/workspace.ts` (`WorkspaceManager` internals)
- `core/providers/gemini.ts` or `core/providers/manager.ts` (`GeminiApiClient` internals)
- `core/preview/server.ts` (`PreviewServer` HTTP daemon)
- `core/export/exporter.ts` (`HeadlessExporter` process internals)
- `app/server/*` (Studio UI web endpoints)
- `app/cli/*` (CLI entrypoints)

**Rule**: If it is not in `core/index.ts`, Limo must not import it.

---

## 8. Current Limitations & Known Gaps

1. **Target Type**: Only `'poster'` is active. Slides, websites, and multi-page documents are not supported by the current engine.
2. **Model Dependency for Function Calling**: The agent ratio tool loop requires a model that understands tool declarations (`gemini-3.5-flash-lite` format). If a host model provider lacks tool support, explicit user ratios or default `3:4` must be passed via `GenerationInput.ratio`.
3. **Headless Chrome Dependency**: Raster export (`output.png`) requires a local installation of Google Chrome, Chromium, or Microsoft Edge. If no browser is installed, HTML/CSS generation succeeds, but `engine.export()` throws an error.
4. **Offline Fonts**: Posters link to Google Fonts (`Plus Jakarta Sans`, `Poppins`, `Inter`, `Syne`, `Instrument Serif`). Offline environments without internet access require fonts to be pre-installed in the OS font directory.

---

## 9. Integration Checklist for Limo Engineers

- [ ] Import only from `core/index.ts`.
- [ ] Initialize `StandaloneDesignEngine` with `enablePreviewServer: false` and `autoExportPng: false` for pure headless mode.
- [ ] Supply either `geminiKeys` or a custom `modelProvider`.
- [ ] Pass `signal: AbortSignal` on all user-cancelable operations.
- [ ] Read `GenerationResult.changedFiles` and `previewUrl` or `output.png` to display results in chat.
- [ ] Use `engine.refine()` with `targetElementId` when the user requests changes to a specific section.
