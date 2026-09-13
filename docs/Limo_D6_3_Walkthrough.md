# Walkthrough — Phase D6.3: Generation Contracts & Native Output Adapters

Phase D6.3 completes the generation-contract and native-adapter portion of D6 by bridging abstract transformation planning to concrete generation contracts and executable native output adapters.

> [!IMPORTANT]
> **Roadmap Boundary & D6 Status**:
> Phase D6 is **not** finished. D6.3 implements generation contracts and native adapters. The remaining sub-phases are:
> - **D6.4**: Transformation Workflow Orchestration (multi-stage workflows, dependency resolution)
> - **D6.5**: Job & Artifact Handoff (broader job ↔ artifact lifecycle orchestration and status integration)
> - **D6.6**: Testing & Real Verification (end-to-end transformation suite)
>
> **D6.3 vs D6.5 Boundary**:
> - **D6.3 Scope**: Concrete adapter execution, deterministic synthesis strictly derived from CanonicalContent (with no new factual claims), atomic file storage with SHA-256 integrity, and returning registered `Artifact` models.
> - **D6.5 Scope**: Comprehensive job ↔ artifact lifecycle integration, end-to-end handoff, event dispatching, and full job state management.

---

## 1. Accomplished Work

### Component 1: Generation Contracts & External Payload Schemas
- **`backend/app/models/generation_contracts.py`**:
  - `GenOfficeOptions`: Document options including title, approx_pages, theme, audience, tone, detail_level, `canonical_id`, and `canonical_hash`.
  - `GenOfficePayload`: Conforms to GenOffice Electron Main's `POST /api/v1/generate` specification (`type`, `prompt`, `project_id`, `session_id`, `options`).
  - `VideoScriptScene`: Timeline scenes with visual cues, narration text, and duration.
  - `VideoEnginePayload`: Versioned contract designed for the future D8 video engine adapter (OpenMontage + MoneyPrinterTurbo), including audio config, visual config, aspect ratio, and provenance grounding.
  - `TweetItem` & `TwitterThreadPayload`: Strict <= 280 character tweet items with sequential numbering (`1/N`).
- **`backend/app/services/transformation/contracts.py`**:
  - `GenerationContractBuilder`: Pure builder translating `CanonicalContent` into versioned `GenOfficePayload` and `VideoEnginePayload` without invoking external binaries.

### Component 2: Deterministic Native Output Adapters
- **`backend/app/services/transformation/adapters/base.py`**:
  - `BaseNativeAdapter`: Unified abstract protocol executing synthesis, atomic file persistence via `StorageService.save_artifact_file()`, and registration in SQLite via `ArtifactService.register_artifact()`.
  - Guarantees outputs are **strictly derived from CanonicalContent with no new factual claims** while preserving source and evidence references.
- **`backend/app/services/transformation/adapters/markdown_adapter.py`**:
  - `NativeMarkdownAdapter` (`OutputFormat.MARKDOWN`): Renders complete GitHub-Flavored Markdown document (`.md`) with Executive Summary, Situational Context, Key Findings with evidence tags, Claims, Data Points table, and References.
  - `NativeHtmlAdapter` (`OutputFormat.HTML`): Renders standalone, responsive HTML5 document (`.html`) with embedded modern CSS, responsive KPI cards, and fact callouts.
- **`backend/app/services/transformation/adapters/social_adapter.py`**:
  - `NativeSocialAdapter`:
    - **LinkedIn Mode** (`OutputFormat.LINKEDIN`): Deterministic structural formatting with professional hook, bulleted takeaways, bold metrics, and curated hashtags (`.md`).
    - **Twitter/X Mode** (`OutputFormat.TWITTER`): Thread formatted as JSON (`.json`) where every tweet is strictly bounded to `<= 280` characters and numbered `1/N`.
- **`backend/app/services/transformation/adapters/infographic_adapter.py`**:
  - `NativeInfographicAdapter` (`OutputFormat.INFOGRAPHIC`): Generates a standalone, well-formed vector SVG diagram (`.svg`, `viewBox="0 0 1200 800"`) with header banner, KPI metric stat cards, critical findings, entity chips, and SHA-256 provenance footer.

### Component 3: Engine Router & Centralized TransformService Execution
- **`backend/app/services/transformation/engine_router.py`**:
  - Updated `ROUTING_TABLE`:
    - Native formats (`MARKDOWN`, `HTML`, `LINKEDIN`, `TWITTER`, `INFOGRAPHIC`) marked `is_implemented=True`.
    - External engines (`DOCUMENT`, `PRESENTATION`, `SPREADSHEET`, `ADVISORY`, `SUMMARY`, `PDF`, `VIDEO`) remain strictly `is_implemented=False` until D7/D8.
  - `dispatch(...)`: Dispatches native formats to execute in-process and register real artifacts; strictly raises `UnimplementedEngineError` (HTTP 501) for external engines.
  - `build_contract(...)`: Exposes payload creation via `GenerationContractBuilder`.
- **`backend/app/services/transform_service.py`**:
  - Added `execute_deliverable(deliverable_id, job_id) -> Artifact`.
  - Added `execute_native_deliverables(job_id) -> List[Artifact]`.
  - Single execution path maintained behind `TransformService` (`Agent` → `TransformContractTool` → `TransformService` → `D6.3 Router`).

---

## 2. Verification Results

### Automated Test Suite
Ran `.venv\Scripts\python.exe -m pytest -q`:
```text
........................................................................ [ 29%]
........................................................................ [ 59%]
........................................................................ [ 88%]
............................                                             [100%]
244 passed in 18.21s
```
**Result**: 244/244 tests passed (232 existing + 12 new D6.3 tests).

### Specific Test Coverage:
1. **Generation Contracts (`tests/test_d6_generation_contracts.py`)**:
   - `test_genoffice_presentation_contract`: Validates `GenOfficePayload` JSON serialization, outline items, slide count, and canonical hash.
   - `test_genoffice_document_contract`: Validates Word/Docs payload schema.
   - `test_video_engine_contract`: Validates `VideoEnginePayload` with scenes, audio/visual config, and duration bounding.
2. **Native Adapters (`tests/test_d6_native_adapters.py`)**:
   - `test_markdown_adapter_produces_real_file`: Confirms physical `.md` file, non-zero byte size, SHA-256 match, and markdown table formatting.
   - `test_html_adapter_produces_real_file`: Confirms physical `.html` file with HTML5 structure and embedded CSS.
   - `test_linkedin_adapter_produces_real_post`: Confirms hook, bullet points, and hashtags derived from canonical content.
   - `test_twitter_adapter_strict_280_character_limit`: Confirms 100% of tweets in thread are strictly `<= 280` characters.
   - `test_infographic_adapter_produces_valid_svg`: Confirms well-formed XML parsing with `xml.etree.ElementTree`, `viewBox="0 0 1200 800"`, and provenance footer.
3. **Execution & Boundary Integrity (`tests/test_d6_native_execution.py`)**:
   - `test_pure_native_job_executes_to_completion`: Confirms pure native job transitions to `COMPLETED` (1.0 progress, 5 artifacts registered).
   - `test_mixed_job_executes_native_and_leaves_external_pending`: Confirms mixed job executes native format, updates to `PROCESSING` (0.5 progress), while external presentation dispatch raises `UnimplementedEngineError`.
   - `test_snapshot_zero_fake_office_and_video_artifacts`: Pre/post filesystem snapshot confirms **zero fake `.docx`, `.pptx`, `.xlsx`, or `.mp4` deliverables leaked to disk**.
4. **Engine Router (`tests/test_d6_engine_router.py`)**:
   - Confirms native engines are `is_implemented=True` and external engines are `is_implemented=False`.

---

## 3. Provenance & Integrity Summary

| Deliverable Format | Engine Type | Extension | Execution Status | Physical Artifact Produced |
|---|---|---|---|---|
| `MARKDOWN` | `NATIVE_MARKDOWN` | `.md` | **Implemented (D6.3)** | Real file in `artifacts/art_.../` with verified SHA-256 |
| `HTML` | `NATIVE_MARKDOWN` | `.html` | **Implemented (D6.3)** | Real file in `artifacts/art_.../` with verified SHA-256 |
| `LINKEDIN` | `NATIVE_SOCIAL` | `.md` | **Implemented (D6.3)** | Real file in `artifacts/art_.../` with verified SHA-256 |
| `TWITTER` | `NATIVE_SOCIAL` | `.json` | **Implemented (D6.3)** | Real file in `artifacts/art_.../` with verified SHA-256 |
| `INFOGRAPHIC` | `NATIVE_INFOGRAPHIC` | `.svg` | **Implemented (D6.3)** | Real file in `artifacts/art_.../` with verified SHA-256 |
| `DOCUMENT` | `GENOFFICE_DOCS` | `.docx` | **Guarded (D7)** | Versioned Contract Payload ready; physical dispatch blocked |
| `PRESENTATION` | `GENOFFICE_SLIDES` | `.pptx` | **Guarded (D7)** | Versioned Contract Payload ready; physical dispatch blocked |
| `SPREADSHEET` | `GENOFFICE_SHEETS` | `.xlsx` | **Guarded (D7)** | Versioned Contract Payload ready; physical dispatch blocked |
| `ADVISORY` | `GENOFFICE_DOCS` | `.docx` | **Guarded (D7)** | Versioned Contract Payload ready; physical dispatch blocked |
| `SUMMARY` | `GENOFFICE_DOCS` | `.docx` | **Guarded (D7)** | Versioned Contract Payload ready; physical dispatch blocked |
| `PDF` | `GENOFFICE_DOCS` | `.pdf` | **Guarded (D7)** | Versioned Contract Payload ready; physical dispatch blocked |
| `VIDEO` | `VIDEO_ENGINE` | `.mp4` | **Guarded (D8)** | Versioned Contract Payload ready; physical dispatch blocked |
