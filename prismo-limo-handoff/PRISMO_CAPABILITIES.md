# Prismo Capabilities: Supported vs Planned

> **Authority**: Verified against active implementation code and test suites in `core/` and `tests/`.

---

## 1. Supported Now (Production Capable)

### A. Poster & Visual Design Generation
- **Single-Artboard Posters**: Generates complete, self-contained `index.html`, `styles.css`, `tokens.css`, and `DESIGN.md` artifacts.
- **Stable DOM Hooks**: Every editable element is tagged with a semantic `data-od-id` attribute (e.g., `poster-root`, `headline`, `supporting-copy`, `hero-image`, `spec-strip`).
- **Archetype Grounding**: Automatically detects prompt domains and matches against 5 battle-tested template archetypes:
  - `bento-execution-pipeline` (Architecture, telemetry, execution steps)
  - `kraft-architecture` (Warm tactile paper, brutalist headlines, tape badges)
  - `motorsport-supercars` (Cinematic hero photography, directional dark scrims, spec strips)
  - `swiss-international` (Mathematical 12-col asymmetric grid, neo-grotesque type, focal photo)
  - `ui-telemetry-inverted` (Top-heavy media waveform/terminal UI, lower typography)

### B. Geometry & Canonical Aspect Ratios
- **5 Canonical Geometries**: Strictly enforces integer-safe pixel dimensions:
  - `3:4` (1080 &times; 1440) — Default
  - `9:16` (1080 &times; 1920)
  - `16:9` (1920 &times; 1080)
  - `1:1` (1080 &times; 1080)
  - `4:3` (1440 &times; 1080)
- **Zero Silent Coercion**: Unsupported ratios (e.g. `2:3`, `21:9`) fail immediately with structured errors.
- **Precedence Hierarchy**:
  1. `explicit_user`: Natural-language user commands ("make it 16:9", "vertical stories", "square") lock the ratio.
  2. `agent_decision`: If the user did not specify, an LLM agent uses function-calling tools to select the best geometry based on content semantics.
  3. `default`: Unset fresh projects default to `3:4`.
- **Multi-Turn Stability**: Once a ratio is locked or selected, subsequent content refinement turns do NOT unexpectedly mutate the aspect ratio unless explicitly commanded.

### C. Visual Discipline & Anti-Slop Safeguards
- **Programmatic Quality Validator**: Programmatically checks each generation before acceptance:
  - Rejects micro-text labels (< 22px).
  - Flags card proliferation (caps repeated cards at &le; 2).
  - Prevents dashboard status dots and pill chip explosion.
  - Bounded 1-turn agent correction loop if CSS is incomplete or slop is detected.
- **Directional Dark Scrim System**: Automatically detects whether text overlays a full-bleed photo and injects matching directional CSS gradients (`.scrim-bottom`, `.scrim-top`, `.scrim-dual`) so text remains readable.
- **Typography Director**:
  - Curated registry of 19 high-craft fonts (`Plus Jakarta Sans`, `Poppins`, `Syne`, `Instrument Serif`, `Inter`).
  - Strict anti-monospace rule: Prevents the model from using monospace fonts (`JetBrains Mono`, `Courier`) for display headlines or body numbers.
  - Selective accent typography: Supports pairing Roman display headings with selective italic serif accent words.

### D. Stock Photography & Local Caching
- **Multi-Provider Search**: Queries Unsplash, Pexels, and Pixabay with automatic failover.
- **Local Asset Caching**: Downloads photos to `<dataDir>/projects/<projectId>/assets/` so generated posters remain fully self-contained offline.

### E. Headless Operation & Host Integration
- **Zero Server Overhead**: Can run completely headless with `enablePreviewServer: false` and `autoExportPng: false`.
- **Model Provider Seam**: Accepts any custom model provider conforming to `ModelProvider` (e.g., custom host LLM proxy, Ollama, Claude, or mock backends for testing).
- **Asynchronous Non-Blocking Headless Export**: Uses Chromium/Chrome to render PNG/JPEG without blocking the Node.js event loop. Validates magic bytes and dimensions before resolving.
- **AbortSignal Support**: Immediate cooperative cancellation across generation, refinement, and export.
- **Filesystem Versioning & Rollback**: Snapshots every turn; allows programmatic rollback to previous version numbers.

---

## 2. Planned / Future / Not Implemented

The following features were discussed in earlier conceptual roadmaps or prototype sketches, but are **NOT** part of the active implementation:

| Capability | Current Status | Details |
| :--- | :--- | :--- |
| **Multi-Slide Keynote Decks** | **Not Implemented** | Removed from active engine to focus purely on single-artboard poster craft. |
| **Multi-Page Websites** | **Not Implemented** | Website generation code was deprecated. Target is strictly `'poster'`. |
| **Token Streaming (`onToken`)** | **Not Implemented** | Generation waits for full model response before parsing HTML/CSS code blocks. |
| **In-Browser DOM Canvas (No Chrome)**| **Not Implemented** | Raster export (`output.png`) strictly requires headless Chromium/Chrome. |
| **Arbitrary / Dynamic Aspect Ratios**| **Not Implemented** | Arbitrary ratios like `2:3` or `21:9` are actively blocked by validator. |
| **Generative SVG Synthesis** | **Not Implemented** | SVGs are embedded from templates or handcrafted CSS/HTML; no separate SVG diffusion model. |
| **Interactive Video / Animation** | **Not Implemented** | Posters are static artboards with zero keyframe video/animation rendering. |
