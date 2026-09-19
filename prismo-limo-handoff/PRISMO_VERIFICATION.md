# Prismo Verification & Test Suite Audit

> **Authority**: Verified by running `npm test` (`tests/run-all.ts`), `npm run test:deterministic` (`tests/deterministic/run.ts`), and `npm run test:smoke` (`tests/smoke/run.ts`).

---

## 1. Test Suite Summary

Prismo is verified by a two-tier test suite:
1. **23 Deterministic Test Suites** (`tests/deterministic/`): 100% offline, zero network access, fast execution (~3.5 seconds).
2. **5 Real API Smoke Suites** (`tests/smoke/`): Tests live external endpoints and headless browser rasterization.

Current Pass Rate: **28 / 28 Suites Passing (100%)**.

---

## 2. Deterministic Test Suites (23 Suites)

The deterministic suite in `tests/deterministic/` verifies all core invariants and contracts:

### A. Core Architecture & Environment (8 Suites)
1. **`env.test.ts`**: Verifies configuration discovery, `.env` parsing, and key isolation.
2. **`pool.test.ts`**: Verifies Gemini key rotation, exponential backoff, and circuit breaker trip on HTTP 429.
3. **`workspace.test.ts`**: Verifies project folder creation, metadata persistence, and file write/read isolation.
4. **`assets.test.ts`**: Verifies stock asset provider query normalization and fallback order.
5. **`memory.test.ts`**: Verifies persistent markdown memory storage and atomic write safety.
6. **`retrieval.test.ts`**: Verifies memory retrieval and query relevance filtering.
7. **`prompt.test.ts`**: Verifies PromptComposer Hallmark discipline injection and system instruction formatting.
8. **`contracts.test.ts`**: Verifies schema validation and runtime contract conformance.

### B. Visual Quality, Typography & Art Direction (5 Suites)
9. **`anti_slop_micro_ui.test.ts`**: Verifies detection and rejection of micro-labels (< 22px), repeated node cards (&gt; 2), status dots, and dashboard UI slop.
10. **`typography.test.ts`**: Verifies FontRegistry integrity (19 fonts, Orbitron exclusion), anti-monospace rules on headlines, and font recommendation profiles.
11. **`editorial_composition.test.ts`**: Verifies elimination of rigid layout skeletons, support for selective italic accents, and semantic editability via `data-od-id`.
12. **`semantic_intent.test.ts`**: Verifies natural-language visual intent detection (`image_required` vs `image_not_wanted`), query synthesis, and directional dark scrim injection (`.scrim-bottom`, `.scrim-top`, `.scrim-dual`).
13. **`export_validation.test.ts`**: Verifies image validation logic against corrupted binary headers and dimension mismatches.

### C. Geometry & Aspect Ratio Invariants (4 Suites)
14. **`ratio_contracts.test.ts`**: Verifies canonical dimensions for all 5 ratios, integer-safe validation, and immediate rejection of non-canonical ratios (e.g. `2:3`).
15. **`ratio_capability.test.ts`**: Verifies project-scoped ratio isolation, precedence hierarchy (`explicit_user > agent_decision > default`), and multi-turn lock stability.
16. **`no_hidden_classifier.test.ts`**: Verifies that ambiguous platform requests (e.g. "make this for Instagram") trigger the agent tool gate rather than hardcoded heuristics.
17. **`ratio_pipeline.test.ts`**: Verifies propagation of canonical dimensions, orientation, and directional scrims through the full prompt and validation pipeline.

### D. Host Integration & Extensibility (6 Suites)
18. **`public_boundary.test.ts`**: Verifies that `core/index.ts` exports only approved native contracts and keeps internal classes private.
19. **`embedded_engine_mode.test.ts`**: Verifies running the engine headlessly with zero HTTP port binding and zero automatic exports.
20. **`concurrency_async_export.test.ts`**: Verifies that headless Chrome export runs asynchronously without blocking the Node.js event loop during concurrent requests, and verifies immediate cancellation via `AbortSignal`.
21. **`extensibility_mock_provider.test.ts`**: Verifies that an in-memory `ModelProvider` can execute full poster generations with zero Gemini API keys.
22. **`extensibility_custom_tool.test.ts`**: Verifies custom tool registration, schema formatting, and typed execution in `AgentToolRegistry`.
23. **`host_integration_contract.test.ts`**: End-to-end simulation of Limo embedding Prismo: project initialization, generation, artifact inspection, refinement turn, version tracking, file URI preview, and `AbortSignal` cancellation.

---

## 3. Real API Smoke Tests (5 Suites)

Executed via `tests/smoke/run.ts` against real endpoints:

| Suite | Verified External Dependency | Validation Check |
| :--- | :--- | :--- |
| **Pexels Smoke** | `https://api.pexels.com/v1/search` | Performs query, verifies image metadata, downloads and saves image to disk. |
| **Pixabay Smoke** | `https://pixabay.com/api/` | Performs query, verifies response payload, downloads asset locally. |
| **Unsplash Smoke** | `https://api.unsplash.com/search/photos` | Performs search, checks attribution contracts and orientation parameters. |
| **Gemini Smoke** | Google Generative Language API | Generates real text with `gemini-3.5-flash-lite`, rotates keys across account pool. |
| **Export Smoke** | Headless Chrome executable | Renders real 1080&times;1440 PNG and JPEG, verifies PNG/JPEG magic byte headers. |

---

## 4. Known Verification Boundaries & Gaps

To maintain strict engineering honesty, Limo engineers should note:
1. **Linux / Docker Environment**: Tests were validated in a Windows Node.js v22 environment. When deploying into a Linux Docker container, font rendering and Chrome executable paths depend on container-installed packages (`fonts-liberation`, `google-chrome-stable` or `chromium`).
2. **Network Dependency for Real Generations**: When using the default `GeminiProviderManager`, external internet access to Google's API and Google Fonts CDN is required unless a local model and pre-installed fonts are provided.
3. **No Visual Regression Diffing**: Tests verify binary headers, aspect ratio dimensions, CSS coverage, and anti-slop rules programmatically; they do not perform pixel-by-pixel perceptual image diffs.
