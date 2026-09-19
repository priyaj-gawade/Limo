# Prismo Source File Map

> **Purpose**: Concise reference mapping paths, responsibilities, and import boundaries for Limo developers.

---

## 1. Public API & External Boundary

| File Path | Responsibility | Limo Direct Import? |
| :--- | :--- | :---: |
| [`core/index.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/index.ts) | The single approved public entrypoint exporting facade, contracts, and seams. | **YES (Primary)** |
| [`core/contracts/engine.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/contracts/engine.ts) | Primary interface definitions: `DesignEngine`, `GenerationInput`, `GenerationResult`, `ExportOptions`. | Re-exported via `core/index.ts` |
| [`core/contracts/models.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/contracts/models.ts) | `ModelProvider` seam, message schemas, and function-calling types. | Re-exported via `core/index.ts` |
| [`core/geometry/ratio.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/geometry/ratio.ts) | Canonical ratio registry, dimensions, orientation, and `RatioState`. | Re-exported via `core/index.ts` |
| [`core/geometry/ratio_tools.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/geometry/ratio_tools.ts) | `AgentToolRegistry`, tool declarations, and tool execution types. | Re-exported via `core/index.ts` |

---

## 2. Core Engine Subsystems (Internal Implementations)

*The files below are managed internally by `StandaloneDesignEngine`. Limo must NOT import them directly.*

### Engine & Generation
| File Path | Responsibility | Access |
| :--- | :--- | :---: |
| [`core/engine.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/engine.ts) | Implements `StandaloneDesignEngine` facade coordinating all subsystems. | Internal (instantiated via `core/index.ts`) |
| [`core/generation/poster.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/generation/poster.ts) | Core multi-step poster generation and refinement pipeline (`PosterEngine`). | Internal Only |
| [`core/prompt/composer.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/prompt/composer.ts) | Composes structured Hallmark art-direction prompts and system instructions. | Internal Only |
| [`core/templates/posters.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/templates/posters.ts) | Discovers, loads, and matches grounded HTML/CSS templates. | Internal Only |

### Design System & Typography
| File Path | Responsibility | Access |
| :--- | :--- | :---: |
| [`core/design-system/typography/director.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/design-system/typography/director.ts) | Contextual font selection and typography hierarchy generator. | Internal Only |
| [`core/design-system/typography/registry.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/design-system/typography/registry.ts) | Curated catalog of 19 verified open-source fonts with weights and fallback chains. | Internal Only |
| [`core/design-system/presets.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/design-system/presets.ts) | Color themes and typographic presets (Amber, Cyan, Emerald, Terracotta, etc.). | Internal Only |
| [`core/design-knowledge/study.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/design-knowledge/study.ts) | Reference study engine analyzing prompt subject for DesignDNA and image intent. | Internal Only |

### Model Providers & Stock Assets
| File Path | Responsibility | Access |
| :--- | :--- | :---: |
| [`core/providers/manager.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/providers/manager.ts) | Multi-account pool manager for Gemini API keys with round-robin rotation. | Internal Only |
| [`core/providers/circuit-breaker.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/providers/circuit-breaker.ts) | Failure tracking, rate-limit classification, and cooldown timers. | Internal Only |
| [`core/providers/gemini.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/providers/gemini.ts) | Low-level HTTP client for Google Generative Language REST endpoints. | Internal Only |
| [`core/assets/manager.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/assets/manager.ts) | Dispatches image search and downloads across Unsplash, Pexels, and Pixabay. | Internal Only |

### Quality Validation & Headless Export
| File Path | Responsibility | Access |
| :--- | :--- | :---: |
| [`core/validation/validator.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/validation/validator.ts) | `ArtifactValidator`: Programmatic anti-slop, ratio integrity, and image contracts. | Internal Only |
| [`core/export/exporter.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/export/exporter.ts) | `HeadlessExporter`: Non-blocking headless Chrome image rasterization. | Internal Only |

### Workspace, Storage & Memory
| File Path | Responsibility | Access |
| :--- | :--- | :---: |
| [`core/workspace/workspace.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/workspace/workspace.ts) | Manages project disk directories, file writes, and metadata reads. | Internal Only |
| [`core/workspace/versioning.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/workspace/versioning.ts) | File checkpointing and version history rollbacks. | Internal Only |
| [`core/workspace/diff.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/workspace/diff.ts) | Filesystem diff engine recording created/modified/deleted files per turn. | Internal Only |
| [`core/memory/store.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/memory/store.ts) | Persistent markdown-backed memory store. | Internal Only |
| [`core/memory/session.ts`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/core/memory/session.ts) | Tracks composition history across turns in a conversation for anti-repetition. | Internal Only |

---

## 3. Client & Presentation Applications (External to Core)

| Directory Path | Responsibility | Relation to Limo |
| :--- | :--- | :--- |
| [`app/server/`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/app/server) | Standalone local web server and interactive Studio web UI panel. | Independent client. Limo does not import or use this. |
| [`app/cli/`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/app/cli) | Standalone terminal CLI runner for generation and export. | Independent client. Limo does not import or use this. |
| [`templates/`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/templates) | Shipped HTML/CSS template archetypes used by `PosterTemplateRegistry`. | Bundled assets loaded by Prismo core on demand. |
| [`tests/`](file:///c:/Users/Admin/Downloads/image%20creation/Prismo/tests) | Deterministic and smoke test suites validating engine invariants. | Test automation. |
