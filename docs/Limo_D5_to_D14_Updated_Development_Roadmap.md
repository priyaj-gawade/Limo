# Limo Development Roadmap — D5 to D14

## Purpose

This document defines the revised development roadmap for Limo from **D5 onward**.

The roadmap reflects the architectural decision that:

- **Limo Agent** is the intelligent decision/orchestration layer.
- **D5** converts real inputs into structured, reusable content.
- **D6** handles transformation planning, configuration, and engine routing.
- **GenOffice remains the native office execution engine** for supported office workflows.
- **OpenMontage + MoneyPrinterTurbo remain the video execution engine**.
- Limo does **not** recreate GenOffice's document-generation logic in Python.
- GenOffice must remain usable as a normal office application while also supporting background automation from Limo.
- No fake generators, simulated artifacts, or UI-mimicking automation are allowed.

---

# 1. High-Level Architecture

```text
                         Limo Frontend
                              │
                              ▼
                       Limo Agent Runtime
                              │
                ┌─────────────┴─────────────┐
                │                           │
                ▼                           ▼
        Interactive Agent Path       Transformation Path
                │                           │
                │                           ▼
                │                   D5 Content Understanding
                │                           │
                │                           ▼
                │                    Canonical Content
                │                           │
                │                           ▼
                │                  D6 Transformation
                │                     & Routing
                │                           │
                │              ┌────────────┴────────────┐
                │              │                         │
                │              ▼                         ▼
                │           D7 GenOffice             D8 Video
                │           Automation               Engine
                │              │                         │
                │              ▼                         ▼
                │         Native Agent             OpenMontage
                │         + Editors                 + MPT
                │              │                         │
                └──────────────┴─────────────┬───────────┘
                                             ▼
                                      D9 Job Management
                                             │
                                             ▼
                                      D10 Artifacts/UI
                                             │
                                             ▼
                                      D11 Validation
                                       + Provenance
                                             │
                                             ▼
                                      D12 Full Integration
                                             │
                                             ▼
                                    D13 Reliability Testing
                                             │
                                             ▼
                                    D14 Final Prototype
```

---

# 2. Architectural Principles

## 2.1 Reuse Native Engines

Limo should not duplicate generation engines that already exist in GenOffice or OpenMontage.

```text
Incorrect:

Limo
  ↓
Python PPTX generator
  ↓
PPTX


Correct:

Limo Agent
  ↓
D6 generation request
  ↓
D7 GenOffice automation
  ↓
GenOffice native AgentLoop
  ↓
Native PPTX generation
```

The same principle applies to Docs, Sheets, and other supported GenOffice capabilities.

---

## 2.2 Limo and GenOffice Are Separate Product Experiences

Users must be able to use GenOffice normally.

Normal usage:

```text
GenOffice Homescreen
    ↓
Create document manually
    ↓
Open existing files
    ↓
Edit
    ↓
Save / Export
```

Limo-assisted usage:

```text
Limo Chat
    ↓
Agent request
    ↓
GenOffice automation bridge
    ↓
Native GenOffice Agent
    ↓
Generated file
```

The automation layer must not replace or break the normal GenOffice workspace.

---

## 2.3 No UI Automation

Do not use:

- mouse automation
- keyboard simulation
- screen scraping
- accessibility automation
- DOM click simulation
- window-focus manipulation

Preferred boundary:

```text
Limo Python
    ↓
localhost HTTP / JSON-RPC
    ↓
GenOffice Electron Main Process
    ↓
existing GenOffice IPC / AgentLoop
```

---

## 2.4 Real Results Only

A successful operation must correspond to a real result.

Forbidden:

```text
Fake progress
Fake artifact path
Fake PPTX/DOCX/XLSX
Synthetic generation response
Python script pretending to be GenOffice
```

Required:

```text
Real request
→ Real execution
→ Real file
→ Real file validation
→ Real artifact metadata
```

---

# 3. D5 — Content Ingestion & Understanding

## 3.1 Objective & Architecture Overview

Convert raw user information into a structured, reusable representation (**Canonical Content Model - CCM**) that acts as the single source of truth for the Limo Agent and subsequent generation engines, paired with sub-document retrieval to prevent full-document context dumps.

```text
Raw Input (File / Media / URL / Text)
       ↓
D5.1 Ingestion & Source Registration (Integrity SHA-256 + Versioned Deduplication)
       ↓
D5.2 Document & Media Extraction (Text, Tables, Structure, Multimodal Understanding)
       ↓
D5.3 Normalization (Common Internal Structure: NormalizedDocument)
       ↓
D5.4 Understanding & Approved Canonicalization Pipeline:
       Local Structured Extraction (Entities, Dates, Metrics)
              ↓
       Gemini Structured Output (Consumes existing D4 Provider Infrastructure)
              ↓
       Deterministic Validation Guards (Pydantic Schema + Repair Loop + Evidence Validation)
              ↓
       CanonicalContent Persistence (Cryptographic SHA-256 Digest)
       ↓
D5.5 Section-Aware & Budget-Enforced Context Retrieval
       ↓
D5.6 Verification & Provenance Grounding
```

---

## 3.2 Reality Classification: Verified vs. Proposed vs. Optional

To adhere to the Reality Rule, all components within D5 are explicitly categorized:

| Component | Status | Description |
|---|---|---|
| **SQLite Schema & Storage Service** | **VERIFIED (Existing)** | D3 SQLite database, atomic file saving, and SHA-256 hashing in `StorageService`. |
| **LLM Provider Infrastructure** | **VERIFIED (Existing)** | D4 `LLMProviderManager` & `GeminiAdapter` wrapping the official `google-genai` SDK. |
| **Base Lexical Retriever** | **VERIFIED (Existing)** | D4 `LexicalRetriever` providing initial BM25 chunk scoring and token budget slicing. |
| **Primary Extractors (DOCX/PDF/XLSX/HTML)** | **PROPOSED (D5)** | Lightweight, standard library extractors (`python-docx`, `PyMuPDF`/`pypdf`, `openpyxl`, `BeautifulSoup4`, `httpx`). |
| **URL Ingestion Pipeline** | **PROPOSED (D5)** | Real HTTP fetch + HTML sanitization into `NormalizedDocument`. |
| **CanonicalService & Deterministic Guards** | **PROPOSED (D5)** | Deterministic service executing schema validation, evidence cross-checking, and SHA-256 hashing. |
| **Advanced Layout / OCR (Docling / PaddleOCR)** | **OPTIONAL (Fallback)** | Triggered only when standard extractors detect complex multi-column tables or rasterized/scanned pages. |
| **Local NER (GLiNER)** | **OPTIONAL (Augment)** | Fast, local zero-shot named entity recognition to accelerate local structured extraction where useful. |
| **Offline Media Fallback (FFmpeg + faster-whisper)** | **OPTIONAL (Fallback)** | Triggered for very large media exceeding cloud limits or specialized offline workloads. |

---

## 3.3 D5.1 — Ingestion, Source Registration & Versioned Deduplication

Accept and register real inputs into sandboxed storage with persistent tracking:

### Supported Input Types:
- **Documents**: PDF, DOCX, PPTX, XLSX, CSV, TXT, Markdown, HTML.
- **Media**: Images (PNG, JPG, WEBP), Audio (MP3, WAV), Video (MP4).
- **Web / Remote**: URLs (HTTP/HTTPS), Raw pasted text snippets.

### Real URL Ingestion Path:
```text
User provides URL
       ↓
URL Validation (Protocol, SSRF & Localhost Block, Format check)
       ↓
HTTP Fetch (httpx async client with redirects, custom User-Agent, timeout guards)
       ↓
Content-Type Verification (Ensures text/html; rejects binary stream bombs)
       ↓
HTML Extraction & Sanitization (BeautifulSoup4: strip <script>, <style>, <nav>, <footer>)
       ↓
Semantic Hierarchy Extraction (Article title, headings H1-H6, paragraphs, tables, hyperlinks)
       ↓
NormalizedDocument
```

### Versioned Deduplication Strategy:
Do not rely solely on `content_hash` if the extraction or canonicalization logic has evolved. Ingestion tracks:
- `source_hash`: SHA-256 digest of the raw source bytes.
- `extraction_version`: Version tag of the extractor code (e.g., `ext_v1.0.0`).
- `canonicalization_version`: Version tag of the CCM schema and extraction rules (e.g., `ccm_v1.0.0`).
- `model_id`: Configured model identifier (e.g., `gemini-2.5-flash`).
- `config_hash`: Hash of extraction/canonicalization configuration.

**Logic**: If `source_hash` matches an existing record in the project **and** all version tags match, the existing extraction/CCM is safely reused. If any version tag or configuration differs, extraction/canonicalization runs fresh.

---

## 3.4 D5.2 — Document & Media Extraction Stack

### Tiered PDF Extraction Strategy:
Do not claim basic PDF libraries reliably solve complex tables or scanned documents. Use a clear 3-tier strategy:

```text
Incoming PDF
     │
     ├─► Tier 1: Text-Layer Vector PDF (Standard)
     │   └─► PyMuPDF / pypdf: Extracts text, page markers, font metadata, and simple layout.
     │
     ├─► Tier 2: Complex Layout & Tables (Heuristic Triggered)
     │   └─► pdfplumber / Docling: Triggered when multi-column text or grid-aligned tables are detected.
     │
     └─► Tier 3: Scanned / Rasterized PDF (Fallback)
         └─► PaddleOCR / Gemini Vision: Triggered when text layer is absent (<50 characters per page).
```

### Multimodal Media Routing:
Avoid hardcoded file size limits. Use explicit, configurable routing tiers:

```text
Incoming Media (Video / Audio / Image)
     │
     ├─► Tier 1: Small/Medium Media (size <= INLINE_MEDIA_MAX_BYTES, default 20 MB)
     │   └─► Send directly inline as multimodal content part to Gemini API.
     │
     ├─► Tier 2: Large Media (INLINE_MEDIA_MAX_BYTES < size <= FILES_API_MAX_BYTES, up to 2 GB)
     │   └─► Upload via Gemini Files API (client.files.upload), process asynchronously,
     │       and delete temporary file handle after canonicalization.
     │
     └─► Tier 3: Very Large / Offline / Specialized Media (Fallback)
         └─► Local preprocessing:
             - FFmpeg: Audio stream extraction & keyframe sampling.
             - faster-whisper: High-speed local speech-to-text transcription.
             - Transcribed text & timestamps then fed to normalization.
```

### Open-Source Tool Purpose Matrix:

| Category | Tool | Exact Role in Limo D5 |
|---|---|---|
| **Primary Document Extraction** | `python-docx` | Structured paragraph, heading hierarchy, and table cell extraction from DOCX. |
| | `PyMuPDF` / `pypdf` | Fast, page-boundary-aware text and metadata extraction from native PDFs. |
| | `openpyxl` | Spreadsheet extraction: workbook metadata, sheets, cell values, and formulas. |
| | `BeautifulSoup4` | HTML/web page sanitization, tag hierarchy parsing, and table extraction. |
| | `httpx` | Async HTTP client for URL fetching with timeout, header, and redirect control. |
| **Optional / Advanced Extraction** | `Docling` | Complex document layout analysis, reading-order reconstruction, and markdown table output. |
| | `PaddleOCR` | Optical character recognition for scanned/image-only PDFs and screenshots. |
| **Local Structured Extraction** | `GLiNER` *(Optional)* | Lightweight, fast local zero-shot named entity recognition (NER) for offline preprocessing. |
| **Media Fallback** | `FFmpeg` | Media splitting, audio stream extraction, and video frame extraction. |
| | `faster-whisper` | Fast local GPU/CPU speech-to-text transcription when offline or exceeding API limits. |
| **LLM Understanding** | `google-genai` | Official Google GenAI SDK for Gemini multimodal reasoning and structured outputs. |
| **Schema Validation** | `Pydantic` (v2) | Strict type checking, schema enforcement, and JSON serialization for canonical models. |
| **Evidence & Consistency** | Deterministic Python | Regex, N-gram text matching, and chronology validators to guard LLM output. |

---

## 3.5 D5.3 — Normalization & Content Processing

Convert all disparate extractor outputs into a single, standardized internal data model:

```python
class NormalizedSection(BaseModel):
    title: Optional[str]
    level: int  # 1 for H1, 2 for H2, etc.
    content: str
    page_number: Optional[int] = None
    timestamp: Optional[str] = None  # e.g., "04:12" for video/audio

class NormalizedTable(BaseModel):
    name: Optional[str]
    headers: List[str]
    rows: List[List[str]]
    source_reference: Optional[str]

class NormalizedDocument(BaseModel):
    source_id: str
    source_name: str
    source_type: SourceType
    mime_type: str
    sections: List[NormalizedSection]
    tables: List[NormalizedTable]
    raw_text: str
    metadata: Dict[str, Any]
```

### Normalization Operations:
- Standardize character encoding to UTF-8; normalize Unicode ligatures and punctuation.
- Collapse irregular whitespace while preserving semantic paragraph breaks.
- Retain explicit source anchors: every paragraph and table records its page number or timestamp.
- Deduplicate identical consecutive fragments.

---

## 3.6 D5.4 — Understanding & Approved Canonicalization Pipeline

### Architectural Principle: Do NOT Create a Second Agent
D5 canonicalization is **not** an autonomous agent loop. It does not run multi-turn planning, tool scheduling, or prompt iteration loops.
Instead, **`CanonicalService`** is a deterministic business service that consumes the **existing D4 `LLMProviderManager` / `GeminiAdapter` infrastructure** to execute structured canonical extraction.

### Approved Canonicalization Pipeline:

```text
NormalizedDocument
       ↓
Step 1: Local Structured Extraction
       ├── Deterministic Regex/Rules: Dates, currency, percentages, numerical metrics
       └── Local NER (GLiNER / Rule-based): Preliminary entity candidates
       ↓
Step 2: Gemini Structured Output Request
       ├── Input: NormalizedDocument text + Local candidates
       ├── System Instruction: Grounded canonicalization rules (no hallucination)
       └── Schema: CanonicalContent JSON Schema (Pydantic constrained)
       ↓
Step 3: Deterministic Validation Guards (DO NOT TRUST RAW LLM JSON)
       ├── Guard 3a: Pydantic Validation
       │   └─► If invalid: Bounded repair loop (max 2 retries with exact validation error fed back)
       │
       ├── Guard 3b: Evidence & Source-Reference Validation
       │   └─► Verify that every CanonicalFact.statement and CanonicalClaim.evidence
       │       corresponds to real text in the referenced source_id and page/timestamp.
       │       Reject or unground unverifiable claims.
       │
       └── Guard 3c: Deterministic Consistency Checks
           └─► Chronological ordering checks on events.
           └─► Data point value sanity (numerical values match textual statements).
           └─► Entity deduplication and reference key alignment.
       ↓
Step 4: Persist CanonicalContent + SHA-256 Digest
       └─► Compute cryptographic content_hash over canonical JSON representation.
       └─► Persist to database and link to Source record.
```

---

## 3.7 D5.5 — Retrieval & Context Integration

Prevent context pollution and token waste by replacing full-document dumps with sub-document targeted retrieval.

```text
User Request / Subagent Query
       ↓
Identify Target Source(s) (by project / conversation / filter)
       ↓
Section-Aware & Source-Aware Chunking (Preserves Section title, H1/H2 hierarchy, and page/timestamp)
       ↓
Lexical BM25 Scoring + Candidate Filtering
       ↓
Token Budget Slicing (Strict enforcement of max_tokens budget, e.g., 2,000 tokens)
       ↓
Return List[RetrievedChunk] -> Injected into Agent Context
```

* **Interface Contract**: Built on the abstract `BaseRetriever` class so semantic/embedding-based retrievers can be dropped in later without modifying agent orchestration.
* **Chunk Grounding**: Every `RetrievedChunk` carries `source_id`, `chunk_index`, `section_title`, and `page_number` or `timestamp`.

---

## 3.8 D5.6 — Validation & Real Verification Plan

Following Rule 10: *Implementation → Automated Tests → Real Verification → Documented Result*.

### Verification Matrix Across Real Formats:

| Input Format | Real Test Asset | Verification Target |
|---|---|---|
| **DOCX** | Real multi-page Word report | Extract paragraphs, headings H1-H3, tables, and generate valid CCM. |
| **PDF** | Real vector PDF document | Extract page-numbered sections, tables, citations, and verify source references. |
| **XLSX** | Real financial/tabular spreadsheet | Extract sheet names, headers, numeric rows, and generate `CanonicalDataPoint` entries. |
| **TXT / Markdown** | Technical specification document | Extract structured sections, code blocks, lists, and generate valid CCM. |
| **HTML / URL** | Real public article / web page | Real HTTP fetch, HTML sanitization, clean text extraction, and canonicalization. |
| **Image** | Scanned receipt or infographic | OCR/Vision extraction of structured data and entity mapping. |
| **Audio** | Real speech recording | Transcription, timestamp alignment, key points extraction. |
| **Video** | `Nobody Wanted Chicken Wings Before This.mp4` | Direct Gemini multimodal understanding: extract timeline events, topics, and key facts. |

### Edge Case & Negative Testing:
1. **Malformed Documents**: Test truncated DOCX, encrypted PDF, and empty files (must raise clean, diagnosable exceptions).
2. **Invalid LLM JSON**: Inject schema-violating LLM mock response; verify the bounded repair loop triggers and successfully repairs or cleanly errors out.
3. **Evidence Mismatch**: Simulate hallucinated facts with fake source references; verify deterministic evidence validator strips or rejects ungrounded claims.
4. **Duplicate Ingestion**: Upload identical file twice; verify zero redundant extraction and exact `content_hash` matching.
5. **Modified Source**: Modify 1 byte in source file; verify change in `source_hash` triggers fresh extraction and prevents stale cache reuse.
6. **Large Media Threshold Routing**: Test media files at boundary sizes to verify correct routing between inline multimodal, Files API, and local fallback.
7. **Retrieval Token Budget**: Test retrieval on 100-page document query; verify returned chunks strictly respect `max_tokens` budget.
8. **Hash Stability**: Verify that serializing identical `CanonicalContent` data produces a bit-for-bit identical SHA-256 `content_hash`.

---

## 3.9 D5 Phase Boundary

```text
D5 Scope Closes Exactly Here:
Ingestion → Extraction → Normalization → Understanding → CanonicalContent → Retrieval → Validation
```
* **Explicitly Excluded from D5**:
  * D6 Output Planning & Generation Routing.
  * D7 GenOffice Localhost Automation Bridge.
  * D8 Video Engine Integration (OpenMontage + MPT).
  * D9 Background Job Queue & SSE streaming.
  * D10 UI Artifact Cards & GenOffice file opening.
  * Redesigning or replacing existing D3 / D4 agent infrastructure.

---

# 4. D6 — Transformation & Generation Orchestration

## Objective

D6 does **not** rebuild document-generation engines.

Its purpose is to determine:

```text
What output is required?
What configuration is required?
Which execution engine should perform it?
How should the result be tracked?
```

## D6 Responsibilities

### Output Planning

Interpret requests such as:

```text
Create a presentation
Create a report
Create a spreadsheet
Create a video
```

### Generation Configuration

Use shared configuration such as:

- audience
- tone
- language
- detail level
- objective
- style

plus format-specific options.

### Engine Routing

Example:

```text
DOCX       → GenOffice
PPTX       → GenOffice
XLSX       → GenOffice
PDF        → selected native/local engine
Markdown   → appropriate renderer
HTML       → appropriate renderer
Video      → OpenMontage + MoneyPrinterTurbo
```

### Generation Contract

Produce a structured request for the selected execution engine.

### Result Handoff

Return a real artifact reference after actual execution.

## D6 does not include

- Python PPTX renderer
- Python DOCX renderer
- Python XLSX renderer
- duplicate GenOffice editor logic
- fake document generators
- fake video generation

---

# 5. D7 — GenOffice Local Automation Integration

## Objective

Connect Limo to the **existing native GenOffice Agent and editors** without breaking normal GenOffice use.

## D7 Architecture

```text
Limo Agent
    ↓
GenOffice Client
    ↓
localhost HTTP / JSON-RPC
    ↓
GenOffice Electron Main Process
    ↓
Background WebContentsView
    ↓
GenOffice AgentLoop
    ↓
Native Skill
    ↓
Docs / Slides / Sheets / PDF
    ↓
Native Save
    ↓
Real File
    ↓
File-Saved Hook
    ↓
Limo Artifact
```

## D7.1 — Local Automation Server

Add a lightweight server inside GenOffice's Electron Main process.

Bind only to:

```text
127.0.0.1
```

Expose minimal operations such as:

```text
POST /api/v1/generate
GET  /api/v1/jobs/{job_id}
POST /api/v1/jobs/{job_id}/cancel
GET  /api/v1/artifacts/{artifact_id}
GET  /api/v1/health
```

Use asynchronous job IDs.

## D7.2 — Background Execution

The Main process creates the appropriate document view:

```text
Docs
Slides
Sheets
```

The view may remain hidden while still executing the existing renderer/agent code.

Do not activate the visible tab or steal window focus.

## D7.3 — Native Agent Invocation

Invoke the existing GenOffice AgentLoop and native skills.

Examples:

```text
Document
→ existing Docs skill

Presentation
→ existing Slides skill / generate_deck

Spreadsheet
→ existing Sheets skill / propose_operations
```

No reimplementation of these pipelines in Python.

## D7.4 — Completion & Artifact Capture

Use existing GenOffice completion/save mechanisms.

```text
Agent completion
→ native save
→ main-process file-saved hook
→ obtain real path
→ validate file
→ return metadata
```

Do not scan directories to guess the output if an existing hook provides the actual path.

## D7.5 — Normal GenOffice Usage Preservation

After automation is added, verify:

- GenOffice homescreen still opens.
- Manual Docs creation works.
- Manual Slides creation works.
- Manual Sheets creation works.
- Existing files open normally.
- Editing works normally.
- Saving/exporting works normally.
- Limo automation works independently.

D7 requires:

```text
Normal GenOffice usage ✅
Limo automation ✅
```

---

# 6. D8 — Video Engine Integration

## Objective

Connect Limo to the existing OpenMontage + MoneyPrinterTurbo pipeline.

```text
Limo Agent
  ↓
D6 Video Generation Request
  ↓
D8 Video Adapter
  ↓
OpenMontage
  ↓
MoneyPrinterTurbo / configured TTS
  ↓
Real MP4
  ↓
Artifact
```

Responsibilities:

- video job submission
- script/configuration handoff
- TTS/audio handling
- rendering
- error handling
- output detection
- artifact registration
- metadata extraction

Do not build a new video engine if OpenMontage already provides the required functionality.

---

# 7. D9 — Background Jobs & SSE

## Objective

Manage long-running generation tasks reliably.

Support:

```text
QUEUED
→ RUNNING
→ COMPLETED
or
→ FAILED
or
→ CANCELLED
```

Responsibilities:

- job manager
- background execution
- progress/status events
- cancellation
- retry/recovery
- persistent job state
- SSE streaming
- event replay
- reconnect support
- startup recovery

Flow:

```text
Limo
→ submit job
→ receive job_id
→ monitor events
→ artifact arrives
```

---

# 8. D10 — Artifact Lifecycle & Limo UI Integration

## Objective

Bring real generated artifacts back into the Limo conversation.

```text
Generation Engine
→ real file
→ ArtifactService
→ Limo Chat
```

Artifact cards should support:

- title
- file type
- metadata
- thumbnail/preview where supported
- Download
- Open/Edit

For GenOffice-supported files:

```text
Artifact Card
→ Open/Edit
→ GenOffice
→ exact generated file
```

No fake previews or fake files.

---

# 9. D11 — Validation & Provenance

## Objective

Verify output quality and source traceability.

### Validation

Check:

- structural validity
- expected format
- file integrity
- factual grounding
- source alignment
- citation/reference consistency where applicable
- output completeness

### Provenance

Maintain relationships such as:

```text
Source
  ↓
Source Hash
  ↓
Canonical Content
  ↓
Transformation
  ↓
Artifact
  ↓
Artifact Hash
```

Important distinction:

```text
SHA-256 = integrity / identity
Validation = factual / structural quality
```

---

# 10. D12 — Full API & Client Integration

## Objective

Connect all production components into one coherent application.

```text
Limo Frontend
      ↓
FastAPI
      ↓
Limo Agent
      ↓
Tools / Skills / Subagents
      ↓
D5 Content
      ↓
D6 Routing
      ↓
D7 GenOffice / D8 Video
      ↓
D9 Jobs
      ↓
D10 Artifacts
      ↓
D11 Validation + Provenance
```

Integrate:

- chat
- projects
- sources
- agent
- transformations
- jobs
- artifacts
- GenOffice
- video
- validation
- provenance

Frontend production state must come from real backend state rather than mock production data.

---

# 11. D13 — End-to-End Testing & Reliability

## Objective

Prove the complete system using real components.

### D13.1 — Generic Chat Regression

```text
Limo UI
→ Agent
→ LLM
→ response
→ SQLite history
```

### D13.2 — Document Transformation

```text
Prompt + Source
→ D5
→ CCM
→ D6
→ GenOffice
→ DOCX
→ Artifact Card
```

### D13.3 — Presentation

```text
Prompt + Source
→ D5
→ D6
→ GenOffice Slides
→ PPTX
→ Artifact Card
→ Open in GenOffice
```

### D13.4 — Spreadsheet

Verify real XLSX generation and editing.

### D13.5 — Video

```text
Prompt
→ D5/D6
→ OpenMontage + MPT
→ MP4
→ Artifact
```

### D13.6 — Failure Testing

Test:

- provider timeout
- rate limiting
- invalid input
- renderer crash
- save failure
- missing source
- unsupported format
- GenOffice unavailable
- OpenMontage failure
- network interruption

Every failure must be explicit and diagnosable.

### D13.7 — Concurrency

Test multiple simultaneous jobs.

Verify:

- no artifact collisions
- no state corruption
- no cross-session leakage
- safe GenOffice background execution
- bounded resource usage

### D13.8 — Recovery

```text
Generation running
→ application/server interruption
→ restart
→ job recovery
→ explicit final state
```

---

# 12. D14 — Prototype Refinement & Final Demo Readiness

## Objective

Prepare the complete Limo prototype for demonstration and practical use.

Focus on:

- UI polish
- loading/error/empty states
- performance
- startup behavior
- artifact UX
- GenOffice transition UX
- installation/setup
- environment configuration
- logging
- packaging
- documentation
- demo reliability

Avoid major architecture changes unless testing exposes a critical defect.

---

# 13. Phase Dependency Map

```text
D3
Backend Foundation
       ↓
D4
Agent Infrastructure
       ↓
D5
Content Ingestion & Understanding
       ↓
D6
Transformation & Generation Routing
       ↓
D7
GenOffice Automation
       ↓
D8
Video Engine
       ↓
D9
Jobs + SSE
       ↓
D10
Artifacts + Limo UI
       ↓
D11
Validation + Provenance
       ↓
D12
Full Integration
       ↓
D13
End-to-End Reliability
       ↓
D14
Final Prototype
```

---

# 14. Critical Development Rules

## Rule 1 — No Fake Pipelines

Never create a local implementation that pretends to be GenOffice, OpenMontage, or another real execution engine.

## Rule 2 — Real Result Required

Do not report success until a real operation has produced a real result.

## Rule 3 — Native Engine Reuse

When a required capability already exists in GenOffice or OpenMontage, integrate with the existing implementation rather than recreating it.

## Rule 4 — Keep GenOffice Usable

Automation must never disable normal GenOffice homescreen, manual creation, opening, editing, or saving.

## Rule 5 — No UI Automation

Do not depend on mouse/keyboard simulation, screen scraping, or DOM-click automation.

## Rule 6 — Clear Phase Boundaries

```text
D4 = Agent
D5 = Understanding
D6 = Routing
D7 = GenOffice
D8 = Video
D9 = Jobs
D10 = Artifacts/UI
D11 = Validation/Provenance
```

## Rule 7 — Real Data

Production state comes from:

```text
SQLite
Local Files
Real LLM Responses
Real Generation Engines
```

## Rule 8 — No Private Chain-of-Thought

Never expose or persist private model reasoning.

## Rule 9 — Efficient Context

Do not repeatedly load entire projects or large files when targeted retrieval is sufficient.

## Rule 10 — Verify Before Advancing

Every phase requires:

```text
Implementation
→ Automated tests
→ Real verification
→ Documented result
```

Do not mark a phase complete merely because code exists.

---

# 15. Final Product Architecture

```text
                        ┌─────────────────┐
                        │    Limo UI      │
                        └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │  Limo Agent     │
                        │ Context / Tools │
                        │ Skills/Subagents│
                        └────────┬────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
                  D5           D6           Tools
             Understand      Route       Backend/External
                    │            │
                    └──────┬─────┘
                           ▼
                 ┌──────────────────┐
                 │ Execution Engines│
                 ├──────────────────┤
                 │ GenOffice        │
                 │ OpenMontage + MPT│
                 └────────┬─────────┘
                          ▼
                    Real Artifacts
                          │
                          ▼
                  Jobs / Artifacts
                          │
                          ▼
                   Validation
                          │
                          ▼
                    Provenance
                          │
                          ▼
                     Limo Chat
```

---

# 16. Final Development Target

```text
User
 ↓
Limo Chat
 ↓
Limo Agent understands request
 ↓
D5 understands source information
 ↓
D6 decides transformation + engine
 ↓
 ┌───────────────────────┐
 │ GenOffice / Video     │
 │ Native Execution      │
 └───────────────────────┘
 ↓
Real Artifact
 ↓
Validation + Provenance
 ↓
Limo Chat Artifact Card
 ↓
Preview / Download / Open-Edit
```

The final architecture makes **Limo the conversational control layer**, while specialized native engines remain responsible for the work they already perform well.
