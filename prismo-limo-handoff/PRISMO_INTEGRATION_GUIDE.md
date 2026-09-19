# Prismo &rarr; Limo Integration Guide

> **Audience**: Engineers embedding Prismo as a capability inside the Limo chat platform.  
> **Source Verification**: All examples use strictly the active public API exposed by `core/index.ts`.

---

## 1. Minimal Headless Setup

To embed Prismo inside Limo with zero HTTP server overhead and zero automatic disk export:

```typescript
import path from 'node:path';
import {
  StandaloneDesignEngine,
  type DesignEngine,
  type GenerationResult,
  type ExportResult
} from './core/index.ts';

// 1. Initialize Engine in Headless Mode
const engine: DesignEngine = new StandaloneDesignEngine({
  dataDir: path.resolve('/var/data/limo/prismo-workspace'),
  geminiKeys: [process.env.GEMINI_API_KEY!],
  enablePreviewServer: false, // Disables HTTP server (no port binding)
  autoExportPng: false        // Disables automatic Chrome screenshots on every turn
});
```

---

## 2. Complete Chat Turn Flow (Generate &rarr; Refine &rarr; Export)

### Step 1: Create a Project Workspace
Every user generation session maps to a project:

```typescript
const project = await engine.createProject(
  'Distributed Consensus Infographic',
  'poster',
  'A high-density technical poster explaining distributed consensus'
);

console.log('Project initialized:', project.id); // e.g. "proj_85df52014d53"
```

---

### Step 2: Generate Poster
Trigger generation with the user's prompt:

```typescript
const genResult: GenerationResult = await engine.generate({
  projectId: project.id,
  conversationId: 'limo-conv-12345',
  prompt: 'A bold, brutalist 3:4 infographic poster on distributed consensus and Raft leader election'
});

if (genResult.status === 'succeeded') {
  console.log('Run ID:', genResult.runId);
  console.log('Active Aspect Ratio:', genResult.ratioState?.ratio); // '3:4'
  console.log('Generated Files:', genResult.allFiles); // ['index.html', 'styles.css', 'tokens.css', 'DESIGN.md']
  console.log('Model Used:', genResult.diagnostics.model);
  console.log('Execution Time:', genResult.diagnostics.durationMs, 'ms');
}
```

---

### Step 3: Refine a Section (Targeted Edit)
When a user asks to modify a specific element in chat, pass `targetElementId` matching the DOM's `data-od-id`:

```typescript
const refineResult: GenerationResult = await engine.refine({
  projectId: project.id,
  conversationId: 'limo-conv-12345',
  instruction: 'Make the headline bolder and change the accent color to electric amber',
  targetElementId: 'headline' // Targets <... data-od-id="headline">
});

console.log('Updated version created. Modified files:', refineResult.changedFiles);
```

---

### Step 4: Export to High-Res PNG (For Chat Display)
Render the raster PNG image to show the user in chat:

```typescript
const exportResult: ExportResult = await engine.export(project.id, {
  format: 'png',
  ratio: genResult.ratioState?.ratio || '3:4',
  outputPath: path.resolve(`/tmp/limo-cache/${project.id}.png`)
});

console.log('Rendered Image Path:', exportResult.filePath);
console.log('Dimensions:', `${exportResult.width}x${exportResult.height}`);
console.log('File Size:', exportResult.fileSize, 'bytes');

// Limo can now stream or attach exportResult.filePath to the user's chat bubble
```

---

## 3. User Cancellation via `AbortSignal`

If a user clicks "Cancel" or sends a new prompt while generation is running:

```typescript
const abortController = new AbortController();

// Pass signal to generate/refine/export
const generationPromise = engine.generate({
  projectId: project.id,
  prompt: 'A poster on quantum computing architecture',
  signal: abortController.signal
});

// User cancels generation:
abortController.abort();

try {
  await generationPromise;
} catch (err: any) {
  if (err.name === 'AbortError' || err.message.includes('aborted')) {
    console.log('Generation cleanly aborted by user; no corrupted files.');
  }
}
```

---

## 4. Supplying a Custom Host Model Provider (Bypassing Gemini)

If Limo has its own AI router (e.g. OpenAI, Anthropic Claude, local Ollama, or an enterprise model gateway), Limo can inject it directly:

```typescript
import {
  StandaloneDesignEngine,
  type ModelProvider,
  type ModelMessage,
  type ModelGenerateOptions
} from './core/index.ts';

class LimoHostModelProvider implements ModelProvider {
  async generate(messages: ModelMessage[], options?: ModelGenerateOptions) {
    // Route messages to Limo's LLM client
    const responseText = await limoInternalLlmClient.complete({ messages, signal: options?.signal });
    return {
      result: { text: responseText, finishReason: 'STOP', model: 'limo-ai-v1', accountId: 'limo-prod-0' },
      diagnostics: {
        provider: 'limo-in-house',
        model: 'limo-ai-v1',
        accountId: 'limo-prod-0',
        durationMs: 450,
        fallbackOccurred: false,
        attemptsCount: 1,
        attemptedAccounts: ['limo-prod-0']
      }
    };
  }

  async generateText(options: { prompt: string; systemInstruction?: string; signal?: AbortSignal }) {
    const text = await limoInternalLlmClient.generateText(options);
    return { text, model: 'limo-ai-v1', accountId: 'limo-prod-0', provider: 'limo-in-house' };
  }
}

// Instantiate Prismo using Limo's provider (zero Gemini keys required)
const engine = new StandaloneDesignEngine({
  dataDir: './limo-prismo-data',
  geminiKeys: [],
  modelProvider: new LimoHostModelProvider(),
  enablePreviewServer: false,
  autoExportPng: false
});
```

---

## 5. Error Handling Pattern

```typescript
try {
  const result = await engine.generate({ projectId, prompt });
} catch (err: any) {
  if (err.message.includes('Unsupported ratio')) {
    // User requested an unsupported aspect ratio (e.g. "make it 2:3")
    // Inform user in chat: "Prismo supports 3:4, 9:16, 16:9, 1:1, and 4:3."
  } else if (err.name === 'AbortError') {
    // Operation was cancelled
  } else {
    // General generation failure
    console.error('Prismo generation error:', err.message);
  }
}
```

---

## 6. Reading Project Files & Artifacts

To inspect or serve HTML/CSS directly to a frontend webview:

```typescript
const artifacts = await engine.getArtifacts(projectId);

for (const artifact of artifacts) {
  console.log(`File: ${artifact.path} (${artifact.size} bytes)`);
}

// Or inspect full project state
const { metadata, files, versions } = await engine.inspect(projectId);
console.log(`Project: ${metadata.name}, Current Version: ${metadata.version}, Total Revisions: ${versions}`);
```
