# Prismo Public API Reference

> **Authority**: Verified against `core/index.ts`, `core/engine.ts`, and `core/contracts/engine.ts`.  
> **Rule**: All imports for external hosts must come directly from `core/index.ts`.

---

## 1. Engine Class & Constructor

### `StandaloneDesignEngine`
The primary engine facade implementing the `DesignEngine` contract.

```typescript
import { StandaloneDesignEngine, type DesignEngineOptions } from './core/index.ts';

const engine = new StandaloneDesignEngine(options: DesignEngineOptions);
```

#### `DesignEngineOptions`
```typescript
export interface DesignEngineOptions {
  /** Root directory for projects, exports, and session data (defaults to './d8.7-data') */
  dataDir?: string;

  /** Optional preview HTTP server port (defaults to 5180) */
  previewPort?: number;

  /** Array of Google Gemini API keys for account rotation pool (required if modelProvider is omitted) */
  geminiKeys: string[];

  /** Stock photography API keys */
  pexelsKeys?: string[];
  pixabayKeys?: string[];
  unsplashKeys?: string[];

  /** If false, disables the HTTP preview server completely (recommended for headless Limo integration) */
  enablePreviewServer?: boolean;

  /** If false, disables automatic headless Chrome PNG export on every generation turn */
  autoExportPng?: boolean;

  /** Custom ModelProvider implementation (bypasses internal Gemini pool) */
  modelProvider?: ModelProvider;
}
```

---

## 2. Core Engine Methods

### `createProject(name, target, instructions?, presetName?)`
Initializes a new design project workspace on disk.

```typescript
createProject(
  nameOrOptions: string | { name?: string; title?: string; target?: TargetType; instructions?: string; preset?: string },
  target: TargetType = 'poster',
  instructions?: string,
  presetName: string = 'modern-dark'
): Promise<ProjectMetadata>
```

- **Parameters**:
  - `nameOrOptions`: Project title string or options object.
  - `target`: Currently must be `'poster'`.
  - `instructions`: Optional background directives for all future turns.
  - `presetName`: Initial design tokens preset (`'modern-dark'`, `'amber-minimal'`, etc.).
- **Returns**: `Promise<ProjectMetadata>`

---

### `generate(input: GenerationInput)`
Executes the full generative poster pipeline.

```typescript
generate(input: GenerationInput): Promise<GenerationResult>
```

#### `GenerationInput` Structure
```typescript
export interface GenerationInput {
  /** Target project identifier (e.g. 'proj_85df5201') - REQUIRED */
  projectId: string;

  /** User prompt or design request - REQUIRED */
  prompt: string;

  /** Limo conversation thread ID (used for anti-repetition session tracking) */
  conversationId?: string;

  /** Design system preset identifier */
  designSystemId?: string;

  /** Explicit aspect ratio ('3:4' | '9:16' | '16:9' | '1:1' | '4:3'). If omitted, agent decides or defaults to '3:4'. */
  ratio?: SupportedRatio;

  /** Explicit pixel dimensions override (must strictly match the ratio) */
  dimensions?: { width: number; height: number };

  /** Attached image paths or URIs */
  attachments?: string[];

  /** AbortSignal for user cancellation */
  signal?: AbortSignal;
}
```

- **Returns**: `Promise<GenerationResult>`
- **Errors**:
  - `Error: Project <id> not found`
  - `Error: Unsupported ratio: "<ratio>"` (when user requests invalid geometry like `2:3`)
  - `DOMException('Operation aborted', 'AbortError')` (when canceled via signal)

---

### `refine(input: RefinementInput)`
Surgically edits an existing poster while preserving layout geometry and design tokens.

```typescript
refine(input: RefinementInput): Promise<GenerationResult>
```

#### `RefinementInput` Structure
```typescript
export interface RefinementInput {
  /** Target project identifier - REQUIRED */
  projectId: string;

  /** Refinement instruction (e.g. "Make the headline bolder and change accent to coral") - REQUIRED */
  instruction: string;

  /** Conversation ID for turn tracking */
  conversationId?: string;

  /** Specific element to target (matching `data-od-id` in index.html, e.g. "headline", "hero-image") */
  targetElementId?: string;

  /** List of section IDs to strictly protect from modifications */
  preserveSections?: string[];

  /** AbortSignal for user cancellation */
  signal?: AbortSignal;
}
```

- **Returns**: `Promise<GenerationResult>`

---

### `export(projectId: string, options: ExportOptions)`
Renders high-resolution raster images (PNG/JPEG) using headless Chrome.

```typescript
export(projectId: string, options: ExportOptions): Promise<ExportResult>
```

#### `ExportOptions` Structure
```typescript
export interface ExportOptions {
  /** Output image format - REQUIRED */
  format: 'png' | 'jpeg';

  /** Custom output file path (defaults to '<dataDir>/exports/<projectId>/export-<timestamp>.<ext>') */
  outputPath?: string;

  /** Explicit width (must conform to project aspect ratio) */
  width?: number;

  /** Explicit height (must conform to project aspect ratio) */
  height?: number;

  /** Target aspect ratio */
  ratio?: SupportedRatio;

  /** AbortSignal for user cancellation */
  signal?: AbortSignal;
}
```

#### `ExportResult` Structure
```typescript
export interface ExportResult {
  filePath: string;
  format: 'png' | 'jpeg';
  width: number;
  height: number;
  fileSize: number;
  durationMs: number;
}
```

---

### `preview(projectId: string)`
Retrieves preview access information for a project.

```typescript
preview(projectId: string): Promise<PreviewInfo>
```

#### `PreviewInfo` Structure
```typescript
export interface PreviewInfo {
  /** HTTP URL (if enablePreviewServer is true) or file:// URI (if headless) */
  url: string;

  /** Server port (0 if enablePreviewServer is false) */
  port: number;

  /** Relative entry point (always 'index.html') */
  entryFile: string;

  /** Absolute path to the project root directory */
  projectRoot: string;
}
```

---

### `inspect(projectId: string)`
Retrieves metadata, file lists, and version history.

```typescript
inspect(projectId: string): Promise<{
  metadata: ProjectMetadata;
  files: ArtifactFile[];
  versions: number;
}>
```

---

### `getProject(projectId: string)`
Returns project metadata or `null` if not found.

```typescript
getProject(projectId: string): Promise<ProjectMetadata | null>
```

---

### `getArtifacts(projectId: string)`
Lists all files currently generated in the project.

```typescript
getArtifacts(projectId: string): Promise<ArtifactFile[]>
```

---

### `rollback(projectId: string, version: number)`
Rolls back the workspace to a previous checkpoint.

```typescript
rollback(projectId: string, version: number): Promise<ProjectMetadata>
```

---

### `shutdown()`
Cleans up local preview servers and resources.

```typescript
shutdown(): Promise<void>
```

---

## 3. Return Types & Diagnostic Structures

### `GenerationResult`
```typescript
export interface GenerationResult {
  /** Unique execution identifier (e.g. 'run_poster_85df5201') */
  runId: string;

  /** Project identifier */
  projectId: string;

  /** Output target type ('poster') */
  target: TargetType;

  /** Execution status */
  status: 'succeeded' | 'failed';

  /** Diff record of files modified, created, or deleted in this turn */
  changedFiles: FileChangeRecord[];

  /** All filenames currently present in project */
  allFiles: string[];

  /** Primary entry file ('index.html') */
  entryHtmlFile: string;

  /** Relative preview path or file:// URL */
  previewUrl: string;

  /** Active canonical ratio state */
  ratioState?: RatioState;

  /** Operational telemetry */
  diagnostics: GenerationDiagnostics;

  /** Error message if status === 'failed' */
  error?: string;
}
```

### `GenerationDiagnostics`
```typescript
export interface GenerationDiagnostics {
  model: string;
  accountId: string;
  durationMs: number;
  fallbackOccurred: boolean;
  stockProvidersUsed: string[];
  provider?: string;
  toolsInvoked?: string[];
  operation?: 'generate' | 'refine';
}
```
