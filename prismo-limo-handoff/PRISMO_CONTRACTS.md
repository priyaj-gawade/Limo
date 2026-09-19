# Prismo TypeScript Contracts

> **Authority**: Extracted directly from `core/contracts/engine.ts`, `core/geometry/ratio.ts`, `core/geometry/ratio_tools.ts`, and `core/contracts/models.ts`.

---

## 1. Primary Engine Contracts (`core/contracts/engine.ts`)

```typescript
export type TargetType = 'poster';

export interface ProjectMetadata {
  id: string;
  name: string;
  target: TargetType;
  rootPath: string;
  createdAt: number;
  updatedAt: number;
  designSystemId?: string;
  instructions?: string;
  version: number;
  ratioState?: RatioState;
}

export interface ArtifactFile {
  path: string;
  size: number;
  content?: string;
  mimeType?: string;
}

export interface FileChangeRecord {
  path: string;
  changeType: 'created' | 'modified' | 'deleted';
  previousSize?: number;
  newSize?: number;
}

export interface GenerationInput {
  projectId: string;
  conversationId?: string;
  prompt: string;
  designSystemId?: string;
  skillName?: string;
  attachments?: string[];
  dimensions?: { width: number; height: number };
  ratio?: SupportedRatio;
  ratioState?: RatioState;
  signal?: AbortSignal;
}

export interface RefinementInput {
  projectId: string;
  conversationId?: string;
  instruction: string;
  targetElementId?: string; // Surgical edit targeting data-od-id (e.g. "headline", "hero-image")
  preserveSections?: string[];
  signal?: AbortSignal;
}

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

export interface GenerationResult {
  runId: string;
  projectId: string;
  target: TargetType;
  status: 'succeeded' | 'failed';
  changedFiles: FileChangeRecord[];
  allFiles: string[];
  entryHtmlFile: string;
  previewUrl: string;
  ratioState?: RatioState;
  diagnostics: GenerationDiagnostics;
  error?: string;
}

export interface ExportOptions {
  format: 'png' | 'jpeg';
  width?: number;
  height?: number;
  ratio?: SupportedRatio;
  slideIndex?: number;
  outputPath?: string;
  signal?: AbortSignal;
}

export interface ExportResult {
  filePath: string;
  format: 'png' | 'jpeg';
  width: number;
  height: number;
  fileSize: number;
  durationMs: number;
}

export interface PreviewInfo {
  url: string;
  port: number;
  entryFile: string;
  projectRoot: string;
}
```

---

## 2. Geometry & Aspect Ratio Contracts (`core/geometry/ratio.ts`)

```typescript
export type SupportedRatio = '3:4' | '9:16' | '16:9' | '1:1' | '4:3';

export const SUPPORTED_RATIOS: readonly SupportedRatio[] = [
  '3:4',
  '9:16',
  '16:9',
  '1:1',
  '4:3'
] as const;

export interface CanonicalDimension {
  readonly width: number;
  readonly height: number;
}

export interface RatioMetadata {
  readonly dimensions: CanonicalDimension;
  readonly orientation: 'portrait' | 'landscape' | 'square';
  readonly commonUseCases: readonly string[];
}

export const CANONICAL_RATIO_REGISTRY: Record<SupportedRatio, RatioMetadata> = {
  '3:4': {
    dimensions: { width: 1080, height: 1440 },
    orientation: 'portrait',
    commonUseCases: ['Graphic poster', 'Editorial hero', 'Standard artboard print']
  },
  '9:16': {
    dimensions: { width: 1080, height: 1920 },
    orientation: 'portrait',
    commonUseCases: ['Mobile stories', 'Reels', 'Vertical lockscreen']
  },
  '16:9': {
    dimensions: { width: 1920, height: 1080 },
    orientation: 'landscape',
    commonUseCases: ['Keynote presentation', 'Desktop display', 'Widescreen visual']
  },
  '1:1': {
    dimensions: { width: 1080, height: 1080 },
    orientation: 'square',
    commonUseCases: ['Social feed square', 'Album artwork', 'Focal badge']
  },
  '4:3': {
    dimensions: { width: 1440, height: 1080 },
    orientation: 'landscape',
    commonUseCases: ['Classic screen display', 'Landscape editorial publication']
  }
} as const;

export type RatioOrigin = 'explicit_user' | 'agent_decision' | 'default';

export interface RatioState {
  readonly ratio: SupportedRatio;
  readonly dimensions: CanonicalDimension;
  readonly origin: RatioOrigin;
  readonly locked: boolean;
}
```

---

## 3. Agent Tool & Function Calling Contracts (`core/geometry/ratio_tools.ts`)

```typescript
export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
}

export interface ToolExecutionResult {
  success: boolean;
  data?: unknown;
  error?: string;
}

export interface AgentTool {
  readonly declaration: FunctionDeclaration;
  execute(projectId: string, args: Record<string, unknown>): ToolExecutionResult | Promise<ToolExecutionResult>;
}

export class AgentToolRegistry {
  registerTool(tool: AgentTool): void;
  getDeclarations(): FunctionDeclaration[];
  hasTool(name: string): boolean;
  executeTool(projectId: string, toolCall: ToolCall): Promise<ToolExecutionResult>;
}
```

### Registered Tool Declarations
Prismo ships with 3 runtime-bound function declarations exposed to Gemini:
1. `get_supported_ratios`: Retrieves available ratios, dimensions, and usage notes.
2. `get_current_ratio`: Returns the active project ratio state and lock status.
3. `set_ratio`: Sets project ratio (validated against `SUPPORTED_RATIOS`, rejected if locked by explicit user instruction).

*Note: `projectId` is strictly injected by the runtime environment and is never exposed as an LLM parameter.*

---

## 4. Model Provider Seam Contracts (`core/contracts/models.ts`)

Limo can supply an in-house model provider implementing `ModelProvider` to bypass external Gemini calls.

```typescript
export interface ModelMessagePart {
  text?: string;
  functionCall?: FunctionCallPart;
  functionResponse?: FunctionResponsePart;
  [key: string]: unknown;
}

export interface ModelMessage {
  role: 'user' | 'assistant' | 'system' | 'function';
  content?: string;
  parts?: ModelMessagePart[];
}

export interface ModelGenerateOptions {
  model?: string;
  temperature?: number;
  maxOutputTokens?: number;
  systemInstruction?: string;
  responseSchema?: Record<string, unknown>;
  responseMimeType?: string;
  tools?: ToolDefinition[];
  signal?: AbortSignal;
}

export interface ModelGenerateResult {
  text: string;
  model: string;
  accountId: string;
  functionCalls?: FunctionCallPart[];
  finishReason?: string;
}

export interface ProviderExecutionDiagnostics {
  model: string;
  accountId: string;
  durationMs: number;
  fallbackOccurred: boolean;
  attemptsCount: number;
  attemptedAccounts: string[];
}

export interface ModelProvider {
  generate(
    messages: ModelMessage[],
    options?: ModelGenerateOptions
  ): Promise<{ result: ModelGenerateResult; diagnostics: ProviderExecutionDiagnostics }>;

  generateText?(options: {
    model?: string;
    systemInstruction?: string;
    prompt: string;
    signal?: AbortSignal;
  }): Promise<{ text: string; model: string; accountId: string; provider?: string }>;
}
```

---

## 5. Architectural Note on `core/contracts/limo.ts`

The repository contains a file named `core/contracts/limo.ts`.  
- **Inspection Finding**: It was written as an early prototype sketch defining `LimoDesignEngineRequest`, `LimoDesignEngineResponse`, and `LimoDesignEngineAdapter`.
- **Architectural Decision**: It is **NOT exported** from `core/index.ts`. Prismo's public boundary is kept host-neutral.
- **Guidance for Limo**: Do not import `core/contracts/limo.ts`. Depend directly on the native contracts above (`GenerationInput`, `GenerationResult`, `ExportOptions`, etc.) exported via `core/index.ts`.
