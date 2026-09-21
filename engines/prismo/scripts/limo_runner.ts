/**
 * Isolated Subprocess Runner for Prismo -> Limo Integration (Phase D8.8).
 * 
 * Architectural Rules:
 * 1. MUST import Prismo strictly and exclusively through `../core/index.ts`.
 * 2. NEVER import internal Prismo modules (PosterEngine, WorkspaceManager, gemini.ts, exporter.ts, etc.).
 * 3. ZERO imports of Limo internals.
 * 4. Implements LimoModelProvider using Prismo's public `ModelProvider` seam (zero Gemini keys managed by Prismo).
 * 5. Enforces canonical aspect ratios (3:4, 9:16, 16:9, 1:1, 4:3) and rejects unsupported ratios without silent coercion.
 * 6. Headless execution: enablePreviewServer = false, autoExportPng = false.
 * 7. Binds SIGTERM/SIGINT to an internal AbortController to support clean cancellation without file corruption.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import {
  StandaloneDesignEngine,
  SUPPORTED_RATIOS,
  isSupportedRatio,
  type SupportedRatio,
  type ModelProvider,
  type ModelMessage,
  type ModelGenerateOptions,
  type ModelGenerateResult,
  type ProviderExecutionDiagnostics,
  type GenerationInput,
  type RefinementInput,
  type ExportOptions,
  type GenerationResult,
  type ExportResult
} from '../core/index.ts';

// --------------------------------------------------------------------------
// 1. Limo Model Provider Bridge Adapter (Public ModelProvider Seam)
// --------------------------------------------------------------------------

interface BridgeConfig {
  endpoint: string;
  token?: string;
}

class LimoModelProvider implements ModelProvider {
  private config: BridgeConfig;

  constructor(config: BridgeConfig) {
    this.config = config;
  }

  async generate(
    messages: ModelMessage[],
    options?: ModelGenerateOptions
  ): Promise<{ result: ModelGenerateResult; diagnostics: ProviderExecutionDiagnostics }> {
    const url = `${this.config.endpoint}/generate`;
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.config.token) {
      headers['X-Limo-Bridge-Token'] = this.config.token;
    }

    const payload = {
      messages,
      options: {
        model: options?.model,
        temperature: options?.temperature,
        maxOutputTokens: options?.maxOutputTokens,
        systemInstruction: options?.systemInstruction,
        tools: options?.tools
      }
    };

    const res = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      signal: options?.signal
    });

    if (!res.ok) {
      const errBody = await res.text().catch(() => '');
      throw new Error(`Limo LLM bridge failed (${res.status} ${res.statusText}): ${errBody}`);
    }

    return (await res.json()) as { result: ModelGenerateResult; diagnostics: ProviderExecutionDiagnostics };
  }

  async generateText(options: {
    model?: string;
    systemInstruction?: string;
    prompt: string;
    signal?: AbortSignal;
  }): Promise<{ text: string; model: string; accountId: string }> {
    const url = `${this.config.endpoint}/generate-text`;
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.config.token) {
      headers['X-Limo-Bridge-Token'] = this.config.token;
    }

    const res = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(options),
      signal: options?.signal
    });

    if (!res.ok) {
      const errBody = await res.text().catch(() => '');
      throw new Error(`Limo LLM bridge text failed (${res.status} ${res.statusText}): ${errBody}`);
    }

    return (await res.json()) as { text: string; model: string; accountId: string };
  }
}

// Deterministic mock provider for isolated verification tests
class DeterministicMockModelProvider implements ModelProvider {
  async generate(messages: ModelMessage[], options?: ModelGenerateOptions) {
    return {
      result: {
        text: 'I choose canonical 3:4 ratio',
        model: 'gemini-3.5-flash-lite' as const,
        accountId: 'deterministic-test-account',
        finishReason: 'STOP'
      },
      diagnostics: {
        provider: 'deterministic-mock',
        model: 'gemini-3.5-flash-lite',
        accountId: 'deterministic-test-account',
        durationMs: 10,
        fallbackOccurred: false,
        attemptsCount: 1,
        attemptedAccounts: ['deterministic-test-account']
      }
    };
  }

  async generateText(options: { model?: string; systemInstruction?: string; prompt: string; signal?: AbortSignal }) {
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <link rel="stylesheet" href="styles.css">
  <link rel="stylesheet" href="tokens.css">
</head>
<body>
  <div class="poster-artboard" data-od-id="poster-root">
    <header class="poster-header" data-od-id="header">
      <span class="category-label" data-od-id="category">RESEARCH BRIEF</span>
    </header>
    <main class="poster-body" data-od-id="body">
      <h1 class="poster-headline" data-od-id="headline">ARTIFICIAL INTELLIGENCE</h1>
      <p class="poster-subheading" data-od-id="subheading">High-density visual synthesis of real-time multi-agent execution graphs and neural reasoning.</p>
    </main>
  </div>
</body>
</html>`;

    const css = `
* { margin: 0; padding: 0; box-sizing: border-box; }
.poster-artboard {
  width: 1080px;
  height: 1440px;
  background-color: #0A0A0C;
  color: #FFFFFF;
  padding: 80px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  font-family: 'Inter', system-ui, sans-serif;
  position: relative;
}
.category-label {
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: #38BDF8;
}
.poster-headline {
  font-size: 80px;
  font-weight: 900;
  line-height: 1.05;
  letter-spacing: -0.03em;
  margin-bottom: 24px;
}
.poster-subheading {
  font-size: 26px;
  line-height: 1.5;
  color: #94A3B8;
  max-width: 820px;
}
`;

    return {
      text: `\`\`\`html:index.html\n${html}\n\`\`\`\n\`\`\`css:styles.css\n${css}\n\`\`\``,
      model: 'deterministic-mock-v1',
      accountId: 'deterministic-test-account'
    };
  }
}

// --------------------------------------------------------------------------
// 2. Runner Contract Definition
// --------------------------------------------------------------------------

interface RunnerContract {
  action: 'generate_and_export' | 'generate' | 'refine' | 'export';
  projectId?: string;
  projectName?: string;
  prompt?: string;
  instruction?: string;
  targetElementId?: string;
  ratio?: string;
  attachments?: string[];
  dataDir: string;
  outputPath?: string;
  bridge?: BridgeConfig;
  mockProvider?: boolean;
  pexelsKeys?: string[];
  pixabayKeys?: string[];
  unsplashKeys?: string[];
}

interface RunnerExecutionResult {
  success: boolean;
  action: string;
  projectId: string;
  runId?: string;
  ratio?: string;
  dimensions?: { width: number; height: number };
  changedFiles?: Array<{ path: string; changeType: string }>;
  allFiles?: string[];
  export?: {
    filePath: string;
    format: string;
    width: number;
    height: number;
    fileSize: number;
    durationMs: number;
  };
  diagnostics?: any;
  error?: {
    code: string;
    message: string;
  };
}

// --------------------------------------------------------------------------
// 3. Execution Lifecycle with AbortSignal
// --------------------------------------------------------------------------

const abortController = new AbortController();

process.on('SIGTERM', () => {
  console.error('[limo_runner] Received SIGTERM, aborting operation...');
  abortController.abort();
});

process.on('SIGINT', () => {
  console.error('[limo_runner] Received SIGINT, aborting operation...');
  abortController.abort();
});

async function run() {
  const args = process.argv.slice(2);
  let contractPath = '';
  let outputJsonPath = '';

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--contract' && args[i + 1]) {
      contractPath = args[i + 1];
      i++;
    } else if (args[i] === '--output-json' && args[i + 1]) {
      outputJsonPath = args[i + 1];
      i++;
    }
  }

  if (!contractPath) {
    console.error('[limo_runner] Missing required argument: --contract <path>');
    process.exit(1);
  }

  const contractContent = fs.readFileSync(contractPath, 'utf-8');
  const contract: RunnerContract = JSON.parse(contractContent);

  // Validate or set aspect ratio
  let targetRatio: SupportedRatio = '3:4';
  if (contract.ratio) {
    const rawRatio = contract.ratio.trim();
    if (!isSupportedRatio(rawRatio)) {
      const errResult: RunnerExecutionResult = {
        success: false,
        action: contract.action,
        projectId: contract.projectId || 'unknown',
        error: {
          code: 'UNSUPPORTED_ASPECT_RATIO',
          message: `Unsupported aspect ratio '${rawRatio}'. Prismo supports: ${SUPPORTED_RATIOS.join(', ')}.`
        }
      };
      if (outputJsonPath) {
        fs.writeFileSync(outputJsonPath, JSON.stringify(errResult, null, 2), 'utf-8');
      }
      console.error(errResult.error?.message);
      process.exit(2);
    }
    targetRatio = rawRatio;
  }

  // ModelProvider Selection
  let modelProvider: ModelProvider;
  if (contract.mockProvider) {
    modelProvider = new DeterministicMockModelProvider();
  } else if (contract.bridge?.endpoint) {
    modelProvider = new LimoModelProvider(contract.bridge);
  } else {
    // Fail if neither bridge nor mock provider is specified (zero raw keys allowed)
    const errResult: RunnerExecutionResult = {
      success: false,
      action: contract.action,
      projectId: contract.projectId || 'unknown',
      error: {
        code: 'MISSING_MODEL_PROVIDER',
        message: 'No LLM bridge endpoint or mock provider configured for Prismo execution.'
      }
    };
    if (outputJsonPath) {
      fs.writeFileSync(outputJsonPath, JSON.stringify(errResult, null, 2), 'utf-8');
    }
    process.exit(3);
  }

  // Load stock API key arrays from contract or process.env fallback
  const pexelsKeys: string[] = (contract.pexelsKeys && contract.pexelsKeys.length > 0)
    ? contract.pexelsKeys
    : [
        process.env.PEXELS_KEY_1,
        process.env.PEXELS_KEY_2,
        process.env.PEXELS_KEY_3,
        process.env.PEXELS_API_KEY
      ].filter((k): k is string => Boolean(k && k.trim()));

  const pixabayKeys: string[] = (contract.pixabayKeys && contract.pixabayKeys.length > 0)
    ? contract.pixabayKeys
    : [
        process.env.PIXABAY_KEY_1,
        process.env.PIXABAY_KEY_2,
        process.env.PIXABAY_KEY_3,
        process.env.PIXABAY_API_KEY
      ].filter((k): k is string => Boolean(k && k.trim()));

  const unsplashKeys: string[] = (contract.unsplashKeys && contract.unsplashKeys.length > 0)
    ? contract.unsplashKeys
    : [
        process.env.UNSPLASH_ACCESS_KEY,
        process.env.UNSPLASH_KEY_1,
        process.env.UNSPLASH_KEY_2
      ].filter((k): k is string => Boolean(k && k.trim()));

  // Headless Engine Initialization
  const engine = new StandaloneDesignEngine({
    dataDir: path.resolve(contract.dataDir),
    geminiKeys: [], // Zero Gemini keys managed by Prismo
    modelProvider,
    pexelsKeys,
    pixabayKeys,
    unsplashKeys,
    enablePreviewServer: false,
    autoExportPng: false
  });

  let resultData: RunnerExecutionResult;

  try {
    let activeProjectId = contract.projectId;

    if (!activeProjectId) {
      const proj = await engine.createProject(
        contract.projectName || 'Poster Deliverable',
        'poster',
        contract.prompt || 'Editorial poster'
      );
      activeProjectId = proj.id;
    }

    if (contract.action === 'generate_and_export') {
      const genInput: GenerationInput = {
        projectId: activeProjectId,
        prompt: contract.prompt || '',
        ratio: targetRatio,
        attachments: contract.attachments || [],
        signal: abortController.signal
      };

      const genResult = await engine.generate(genInput);

      if (genResult.status !== 'succeeded') {
        throw new Error(genResult.error || 'Prismo generation failed with non-succeeded status');
      }

      const activeRatio = genResult.ratioState?.ratio || targetRatio;
      const exportOptions: ExportOptions = {
        format: 'png',
        ratio: activeRatio,
        outputPath: contract.outputPath,
        signal: abortController.signal
      };

      const exportResult = await engine.export(activeProjectId, exportOptions);

      resultData = {
        success: true,
        action: contract.action,
        projectId: activeProjectId,
        runId: genResult.runId,
        ratio: activeRatio,
        dimensions: genResult.ratioState?.dimensions || { width: exportResult.width, height: exportResult.height },
        changedFiles: genResult.changedFiles,
        allFiles: genResult.allFiles,
        export: {
          filePath: exportResult.filePath,
          format: exportResult.format,
          width: exportResult.width,
          height: exportResult.height,
          fileSize: exportResult.fileSize,
          durationMs: exportResult.durationMs
        },
        diagnostics: genResult.diagnostics
      };
    } else if (contract.action === 'refine') {
      const refineInput: RefinementInput = {
        projectId: activeProjectId,
        instruction: contract.instruction || '',
        targetElementId: contract.targetElementId,
        signal: abortController.signal
      };

      const refineResult = await engine.refine(refineInput);

      resultData = {
        success: refineResult.status === 'succeeded',
        action: contract.action,
        projectId: activeProjectId,
        runId: refineResult.runId,
        ratio: refineResult.ratioState?.ratio,
        dimensions: refineResult.ratioState?.dimensions,
        changedFiles: refineResult.changedFiles,
        allFiles: refineResult.allFiles,
        diagnostics: refineResult.diagnostics
      };
    } else if (contract.action === 'export') {
      const exportResult = await engine.export(activeProjectId, {
        format: 'png',
        ratio: targetRatio,
        outputPath: contract.outputPath,
        signal: abortController.signal
      });

      resultData = {
        success: true,
        action: contract.action,
        projectId: activeProjectId,
        export: {
          filePath: exportResult.filePath,
          format: exportResult.format,
          width: exportResult.width,
          height: exportResult.height,
          fileSize: exportResult.fileSize,
          durationMs: exportResult.durationMs
        }
      };
    } else {
      throw new Error(`Unsupported action: ${contract.action}`);
    }

    await engine.shutdown?.();

    if (outputJsonPath) {
      fs.writeFileSync(outputJsonPath, JSON.stringify(resultData, null, 2), 'utf-8');
    }
    console.log(JSON.stringify(resultData));
    process.exit(0);

  } catch (err: any) {
    const isAborted = err.name === 'AbortError' || err.message?.includes('aborted');
    const errResult: RunnerExecutionResult = {
      success: false,
      action: contract.action,
      projectId: contract.projectId || 'unknown',
      error: {
        code: isAborted ? 'OPERATION_ABORTED' : 'EXECUTION_FAILED',
        message: err.message || 'Prismo runner encountered an error'
      }
    };

    try {
      await engine.shutdown?.();
    } catch {}

    if (outputJsonPath) {
      fs.writeFileSync(outputJsonPath, JSON.stringify(errResult, null, 2), 'utf-8');
    }
    console.error(err.message || err);
    process.exit(isAborted ? 130 : 1);
  }
}

run().catch((err) => {
  console.error('[limo_runner] Fatal top-level error:', err);
  process.exit(1);
});
