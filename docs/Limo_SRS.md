# Software Requirements Specification (SRS)
## Limo — AI-Powered Content Transformation Workspace

**Document Status:** Production Baseline & Phase Traceability Specification (Post-D10)  
**Version:** 3.0 (Comprehensive D1–D10 Implementation)  
**Application:** Limo  
**Problem Statement:** Gen AI Platform for Automated Content Transformation  
**Sponsoring Organization:** National Technical Research Organisation (NTRO)  
**Department:** National Technical Research Organisation (NTRO)  
**Category:** Software  
**Theme:** Blockchain & Cybersecurity  
**Primary Client:** React + TypeScript Desktop Web/Electron Shell (`http://localhost:5190/` / `AppFrame.tsx`)  
**Primary Backend:** Python 3.13 + FastAPI (`http://127.0.0.1:8000`)  
**AI Orchestration:** Limo Agent Runtime + Fast Intent Gate + Google GenAI SDK (Gemini 2.5/3.5)  
**Office Editing:** GenOffice Automation Bridge (Docs, Slides, Sheets)  
**Video Engine:** OpenMontage + MoneyPrinterTurbo + Multi-Provider TTS (Gemini, Azure, Edge-TTS)  
**Infographic Engine:** Prismo Compiler + Visual Contrast/Layout Validators  
**Web Reach Engine:** DDGS Zero-Config Search + Multi-Tier Extraction (Trafilatura → Crawl4AI → BeautifulSoup4) + SSRF Hardening  
**Job & Event Engine:** Background Worker Queue + Durable SSE Streaming (`Last-Event-ID`) + Dual DB Parity (SQLite/PostgreSQL)  
**Social & Skills Layer:** File-Backed Dynamic Skill Registry + LinkedIn / Twitter / Instagram Publishing Engines  

---

## 1. Introduction

### 1.1 Problem Statement & NTRO Identification

| Attribute | Official Specification |
| :--- | :--- |
| **Problem Statement Title** | **Gen AI Platform for Automated Content Transformation** |
| **Organization** | **National Technical Research Organisation (NTRO)** |
| **Department** | **National Technical Research Organisation (NTRO)** |
| **Category** | **Software** |
| **Theme** | **Blockchain & Cybersecurity** |

#### Background
Organisations frequently need to convert information available in different forms such as news articles, reports, advisories, threat intelligence, policy documents, research papers, announcements, incident reports or free-form prompts into specific communication artefacts suitable for various purposes. The process of manually analysing the source content, understanding the desired objective and creating the required output format is time-consuming, resource-intensive and often requires expertise in content creation, communication and domain knowledge.

There is a critical need for an intelligent platform that can transform user-provided content into a desired output format through a simple and configurable interface.

#### Description & Core Objective
The system shall act as an **AI-powered content transformation engine** that converts a common source of information into the specific deliverable requested by the operator, thereby reducing manual effort, improving consistency, accelerating content creation and enhancing operational efficiency.

The platform provides an intuitive conversational dashboard through which an operator can submit source content in the form of high-quality English language text, documents, articles, reports, prompts, images, videos or contextual information. In addition to providing the source content, the operator shall select one or more desired output types through configurable parameters available on the dashboard.

Based on the submitted content and the selected output type(s), the platform analyzes the input, understands the context and intent, extracts ground-truth facts, and generates the requested output artefact. The platform supports multiple output formats simultaneously and allows operators to control generation parameters such as target audience, tone, language, level of detail, communication objective and content style.

In summary, the platform shall generate real, verified deliverables corresponding to the option(s) selected by the operator on the dashboard.

### 1.2 Evaluation Deliverables Mapping

In accordance with NTRO evaluation requirements, the Limo project provides the following verified deliverables:

| Deliverable Requirement | Location / Artifact in Limo | Status |
| :--- | :--- | :--- |
| **1. Source Code Link** | Clean Git repository root containing frontend, backend, GenOffice, and runner engines. | Fully Implemented & Structured |
| **2. Readme with Setup Instructions** | [`README.md`](file:///c:/Users/Admin/Downloads/LIMO/README.md) + [`start-all.ps1`](file:///c:/Users/Admin/Downloads/LIMO/start-all.ps1) one-click unified launcher. | Complete & Verified |
| **3. Architecture Document (Max 2 Pages)** | Executive System Architecture Section (Section 2 & 10 of this SRS, plus [`docs/GENOFFICE_LOCAL_AUTOMATION_ARCHITECTURE.md`](file:///c:/Users/Admin/Downloads/LIMO/docs/GENOFFICE_LOCAL_AUTOMATION_ARCHITECTURE.md)). | Complete & Verified |
| **4. Demo Video (Max 2 Minutes)** | End-to-end screen demonstration showing input ingestion, multi-deliverable transformation, video playback, and GenOffice live editing. | Scripted & Validated via D10 Walkthrough |
| **5. Technical Presentation (Max 5 Slides)** | 5-slide core technical deck covering: Problem & Solution, System Architecture, Core Capabilities & Engines, Security & Blockchain Provenance, Impact & Roadmap. | Structured in Project Artifacts |

### 1.3 Scope & Pipeline Flow

Limo enforces an evidence-based, deterministic pipeline from ingestion to deliverable creation:

```text
Source / Prompt / Threat Intel / URL / Media
      ↓
[Input Processing & Multi-Tier Ingestion (D5, D8.9)]
      ↓
[Context & Intent Understanding + Fast Intent Gate (D4, D7.7)]
      ↓
[Canonical Content Representation & Fact Grounding (D5)]
      ↓
[Output Selection & Multi-Parameter Configuration (D6)]
      ↓
[Distributed Workflow Orchestrator & Engine Router (D6, D9)]
      ├── Native Social Adapters (LinkedIn, X/Twitter, Instagram) (D6, D10)
      ├── GenOffice Automation Bridge (DOCX, PPTX, XLSX, PDF) (D7)
      ├── OpenMontage Subprocess Video Engine (MP4 + Narration + Captions) (D8)
      ├── Prismo Compiler Engine (High-Resolution Infographics/Posters) (D8.8)
      └── Standalone Multi-Provider TTS Narration Engine (MP3) (D8.3)
      ↓
[Deterministic Structural & Visual Validation (D5, D6, D8.8)]
      ↓
[Atomic Artifact Registration & Disk Syncing (D3, D10)]
      ↓
[Conversational Card / In-App Video Player / GenOffice Native Tab (D2, D8.5, D10)]
      ↓
[In-Place Edit, External Sync, & Multi-Platform Export (D10)]
```

### 1.4 Intended Users & Personas

1. **Cybersecurity & Threat Intelligence Analyst**: Ingests incident reports, CVE announcements, and threat intelligence feeds to automatically output structured advisories, executive memos, and alert posts.
2. **Communications & Media Officer**: Ingests policy papers, research reports, and technical announcements to output press releases, social media campaigns (LinkedIn, Twitter/X threads, Instagram carousels), and explainer videos.
3. **Executive Decision Maker / Operator**: Reviews auto-generated executive briefings and presentation decks directly in GenOffice, editing slides and figures seamlessly.

### 1.5 Source of Requirements

The core transformation requirements and problem scenarios are derived from the NTRO problem statement. Implementation parameters, engine integrations, security boundaries, and desktop architecture reflect the verified engineering milestones from Phase D1 through Phase D10.

---

## 2. Product Overview

Limo is a unified conversational workspace and desktop suite in which the operator can:

1. **Start a conversation** or project thread.
2. **Submit heterogeneous sources**: high-quality English text, uploaded documents (DOCX, PDF, XLSX), images, videos, audio recordings, public URLs, or live web search queries.
3. **Select one or more desired output types** (e.g. Video + LinkedIn Post + Advisory + Slides from one prompt).
4. **Configure generation parameters**: Target Audience, Tone, Language, Level of Detail, Communication Objective, and Content Style.
5. **Monitor asynchronous progress**: Non-blocking background worker processes stream real-time stage progress over Server-Sent Events (SSE).
6. **Receive real generated deliverables**: Native deliverable cards appear in the chat stream with zero mock or simulated data.
7. **Preview & interact**: View high-resolution infographics, listen to audio narration, scrub through narrated videos in the embedded player, and inspect structured social cards.
8. **Live Edit in GenOffice**: One-click loopback opens generated DOCX, PPTX, or XLSX files in native GenOffice desktop tabs.
9. **Automatic Disk Synchronization**: Any edits saved in GenOffice or edited in social cards automatically create versioned artifact snapshots with updated SHA-256 hashes.
10. **Export & Share**: Download verified files or copy sanitized, ready-to-publish plain text without markdown boilerplate.

### 2.1 Core Subsystems Matrix (D1–D10)

```text
+-----------------------------------------------------------------------------------+
|                           LIMO UNIFIED DESKTOP SHELL                              |
|   +---------------------------------------------------------------------------+   |
|   |  TabBar: [ Pin 0: Limo AI Chat ] [ Tab 1: Docx ] [ Tab 2: Pptx ] [ Tab 3 ]|   |
|   +---------------------------------------------------------------------------+   |
|   |  [ 💬 Limo AI Chat ] <---------------------> [ 📄 Office Workspace ]      |   |
|   |  * Chat-First Interface                      * GenOffice Editor Tabs          |   |
|   |  * File-backed Skills (LinkedIn, X, IG)      * Native Loopback Opener         |   |
|   |  * Truthful Draft Cards (Copy/Edit/Save)     * Direct Disk File Save          |   |
|   +---------------------------------------------------------------------------+   |
|                                       │                                           |
|                  Bidirectional Loopback & Disk Sync (D10)                         |
|   +---------------------------------------------------------------------------+   |
|   |                       LIMO BACKEND CORE RUNTIME                           |   |
|   |  * Fast Intent Gate & Structural Classifiers (D7.6, D7.7)                 |   |
|   |  * Distributed Background Queue & Lease Manager (D9)                      |   |
|   |  * Multi-Format Ingestion & Dual Provenance Web Reach (D5, D8.9)           |   |
|   |  * Authoritative Engine Router (GenOffice, OpenMontage, Prismo, Social)   |   |
|   |  * Real Physical Storage Sandboxing & Cascading Deletion (D3, D10)        |   |
|   |  * Dual Database Parity (SQLite WAL / PostgreSQL Enterprise Cloud) (D9.6) |   |
|   +---------------------------------------------------------------------------+   |
+-----------------------------------------------------------------------------------+
```

---

## 3. Functional Requirements

> **Marking Convention:**  
> - `[NTRO Problem Statement Core Requirement]` — Directly mandated by the NTRO problem statement description, examples, or deliverables.  
> - `[Limo Platform Engineering Requirement]` — Architectural, security, performance, or system interface requirement established in the Limo design.

---

### 3.1 Source Input and Ingestion

#### FR-001 — High-Quality Text & Free-Form Prompt Submission
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-01]`  
The system shall allow the operator to provide high-quality English language text, free-form instructions, incident descriptions, and threat reports directly through the Limo composer.

#### FR-002 — Document & Multi-Format File Uploads
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-02]`  
The platform shall accept and extract structured information from heterogeneous document and media file formats, including:
1. Microsoft Word documents (`.docx`) via `python-docx`.
2. Adobe PDF documents (`.pdf`) via `pypdf`.
3. Microsoft Excel spreadsheets (`.xlsx`) via `openpyxl`.
4. Web and Markdown documents (`.html`, `.md`, `.txt`) via `BeautifulSoup4`.
5. Static images (`.png`, `.jpg`, `.jpeg`, `.webp`) via multimodal vision analysis.
6. Audio files (`.mp3`, `.wav`) and Video files (`.mp4`) via Google GenAI Files API integration.

#### FR-003 — Multi-Source Ingestion in Single Transformation
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-03]`  
The system shall allow multiple distinct source items (e.g. an incident report PDF, a threat advisory text snippet, and an infrastructure diagram image) to be attached and synthesized simultaneously within one transformation request.

#### FR-004 — Source Normalization & Metadata Extraction
`[Limo Platform Engineering Requirement]`  
The system shall extract and normalize usable text, tabular data, visual semantics, and structural headings from supported sources into structured intermediate representations before executing transformation.

#### FR-005 — Source Identity & Cryptographic Hashing
`[Limo Platform Engineering Requirement]`  
The system shall calculate and retain an immutable SHA-256 cryptographic digest and metadata record (`source_hash`, `filename`, `mime_type`, `size_bytes`, `created_at`) for every submitted source item.

---

### 3.2 Content Understanding & Canonical Representation

#### FR-007 — Context & Domain Understanding
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-04]`  
The system shall analyze submitted content, detect domain context (e.g. cybersecurity breach, intelligence advisory, quarterly financial update, research paper), and identify key themes, actors, and timelines.

#### FR-008 — Objective & Intent Resolution
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-05]`  
The system shall analyze the operator's prompt and active UI mode to infer the primary communication objective (e.g. executive awareness, urgent incident response, public education, technical brief).

#### FR-009 — Grounded Entity & Fact Extraction
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-06]`  
The system shall extract structured entities (organizations, malware variants, threat actors, CVEs, metrics), verified factual statements, and situational context.

#### FR-010 — Canonical Content Model (Single Source of Truth)
`[Limo Platform Engineering Requirement]`  
The system shall compile normalized source facts into a structured, vendor-neutral Canonical Content Model (`CanonicalContent`). All downstream generators shall draw from this model to prevent cross-deliverable hallucination or drift.

#### FR-011 — Multi-Source Synthesis & Deduplication
`[Limo Platform Engineering Requirement]`  
When multiple sources are provided, the system shall resolve conflicting statements, cross-reference facts, and synthesize a single coherent canonical representation tagged with source attribution.

---

### 3.3 Generation Configuration & Parameter Control

#### FR-012 — Multi-Output Selection
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-07]`  
The operator shall be able to select one or multiple desired output types simultaneously from the dashboard (e.g. Video, Presentation, LinkedIn Post, and Advisory) for a single execution.

#### FR-013 — Target Audience Parameter Control
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-08]`  
The operator shall be able to specify the target audience (e.g. *Executive Leadership / C-Suite*, *Technical Cyber Specialists*, *General Public*, *Legal / Compliance*), and the engine shall modulate vocabulary, depth, and framing accordingly.

#### FR-014 — Tone Parameter Control
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-09]`  
The operator shall be able to control output tone (e.g. *Urgent / Authoritative*, *Professional / Neutral*, *Persuasive / Engaging*, *Direct / Crisp*).

#### FR-015 — Language Control
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-10]`  
The operator shall be able to specify the output language for generated text, presentation slides, speech narration, and subtitles.

#### FR-016 — Level of Detail Parameter Control
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-11]`  
The operator shall be able to configure the level of detail across three tiers:
1. *High-Level / Executive*: Bullet summaries, key takeaways, bottom-line recommendations.
2. *Standard / Balanced*: Comprehensive overview with contextual supporting points.
3. *Deep-Dive / Comprehensive*: Full operational details, technical indicators, methodologies, and raw evidence.

#### FR-017 — Communication Objective Parameter Control
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-12]`  
The operator shall be able to set the communication objective (e.g. *Actionable Mitigation*, *Strategic Decision-Making*, *Stakeholder Awareness*, *Public Engagement*).

#### FR-018 — Content Style Parameter Control
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-13]`  
The operator shall be able to configure styling constraints such as slide count, aspect ratio (`16:9`, `3:4`, `9:16`), video duration (`15s`, `30s`, `60s`), and tweet thread lengths.

#### FR-019 — Deterministic Configuration Reconciliation
`[Limo Platform Engineering Requirement]`  
The platform's `TransformationConfigResolver` shall reconcile prompt-specified parameters with dashboard options into a validated `TransformationConfig` entity.

---

### 3.4 Specific Output Transformations (NTRO Problem Statement Examples)

#### FR-020 — Simultaneous Multi-Deliverable Generation
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-14]`  
If multiple output formats are selected, the platform shall generate **all selected deliverables from the same source content** in a unified, coordinated orchestration without requiring separate operator submissions.

#### FR-021 — Structured Advisory Document Generation
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-15]`  
If **'Advisory'** is selected, the system shall generate a structured advisory document (DOCX and Markdown) containing:
1. Advisory Header (Title, Reference ID, Severity Level, Date, Target Sector).
2. Executive Summary / Incident Description.
3. Threat / Technical Analysis & Indicators of Compromise (IoCs).
4. Impact Assessment.
5. Specific, Prioritized Mitigation Actions & Defensive Recommendations.

#### FR-022 — Concise Executive Summary Generation
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-16]`  
If **'Executive Summary'** is selected, the system shall generate a concise executive briefing document formatted for rapid decision-making, emphasizing bottom-line implications, strategic impact, and key decisions.

#### FR-023 — Presentation Slides & Speaker Notes Generation
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-17]`  
If **'Presentation'** is selected, the system shall generate a complete presentation package (native `.pptx` editable in GenOffice Slides) including:
1. Title slide and agenda structure.
2. Modular content slides with headlines, subheadings, and concise bullet items.
3. Embedded visual/graphic recommendations for each slide.
4. Detailed speaker notes attached to each slide to assist oral presentation.

#### FR-024 — Professional LinkedIn Post Generation
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-18]`  
If **'LinkedIn Post'** is selected, the system shall generate a professional, publication-ready LinkedIn post (up to 3,000 characters) featuring:
1. Attention-grabbing opening hook.
2. Structured insights or numbered takeaways formatted with clean paragraph breaks.
3. Clear call to action (CTA).
4. Curated, industry-relevant hashtags (`#CyberSecurity`, `#ThreatIntel`).
5. Truthful draft staging card with in-place editing and markdown-stripping plain text clipboard export.

#### FR-025 — Platform-Optimized Twitter/X Thread Generation
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-19]`  
If **'Twitter/X Post'** is selected, the system shall generate platform-optimized tweets or a multi-part tweet thread adhering strictly to:
1. Numbered sequence (`1/N` through `N/N`).
2. Hard character limits ($ \le 280 $ characters per tweet).
3. Strong thread-opening hook and conclusive summary tweet.
4. Selective, high-impact hashtags.

#### FR-026 — Infographic Content & High-Fidelity Visual Poster Generation
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-20]`  
If **'Infographic'** is selected, the system shall generate infographic content, layout recommendations, key messaging, and compile a high-resolution visual PNG poster (1080x1440, 3:4 or 16:9) via the integrated Prismo design compiler.

#### FR-027 — Complete Video Package & Rendered MP4 Generation
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-21]`  
If **'Video'** is selected, the system shall generate a complete video package and produce a rendered `.mp4` deliverable, including:
1. Narrative script structured into timed scenes.
2. Storyboard with scene descriptions and visual framing prompts.
3. Natural voice narration synthesized through the integrated multi-provider TTS layer.
4. Timestamp-accurate, synchronized subtitles (SRT/ASS burned into composition).
5. Visual asset recommendations and background composition rendered through the OpenMontage engine.

#### FR-028 — Output-Specific Parameter Enforcement
`[Limo Platform Engineering Requirement]`  
The system shall apply output-specific constraints (e.g. video duration bounds 8s–300s; slide counts 3–15; aspect ratios 16:9 / 3:4 / 9:16) during planning and compilation.

#### FR-029 — Mandatory Physical Artifact Registration
`[Limo Platform Engineering Requirement]`  
Every successful output transformation shall result in an official registered `Artifact` entity persisted in SQLite/PostgreSQL with verified physical file existence on disk.

---

### 3.5 AI Agent, Intent Gate & Orchestration

#### FR-030 — Autonomous Request Planning
`[Limo Platform Engineering Requirement]`  
The Limo Agent Runtime shall interpret user prompts, analyze context, and select execution branches (Fast Conversational Chat, Deliverable Generation, Ambiguity Clarification, or External Web Retrieval).

#### FR-031 — Fast Intent Gate (D7.6–D7.7)
`[Limo Platform Engineering Requirement]`  
The system shall utilize an ultra-low-latency (0.01s) deterministic regex and heuristic classifier (`IntentResolver`) to separate conversational questions from deliverable creation requests, preventing accidental pipeline invocation.

#### FR-032 — Strict Feature Mode Isolation (Audio vs. Video)
`[Limo Platform Engineering Requirement]`  
When an operator is in an explicit mode (e.g. Audio mode or Video mode), the engine shall strictly lock format resolution to that mode:
- Audio mode shall **never** generate a video deliverable, regardless of keywords inside the prompt.
- Video mode shall **never** generate standalone audio deliverables.
- Conversational directives with colons (`read this aloud: ...`) shall decouple command extraction from speech body content.

#### FR-033 — Progressive Skill Loading (Tier 2 Architecture)
`[Limo Platform Engineering Requirement]`  
The agent shall dynamically discover and inject domain-specific instructions (`SkillRegistry`) from filesystem markdown documents (e.g. LinkedIn, Twitter, Instagram, GenOffice) only when matching the active turn, preserving context window capacity.

---

### 3.6 Distributed Background Jobs & Resilience (Phase D9)

#### FR-094 — Distributed Background Job Execution & Decoupled Worker Model
`[Limo Platform Engineering Requirement]`  
Transformation requests shall be dispatched to asynchronous background jobs (`TransformationJob`), returning an immediate HTTP 202/201 response with job ID to ensure long-running video, office, or infographic tasks never block the web server or client requests.

#### FR-095 — Cooperative Job Cancellation & Atomic Subprocess Reaping
`[Limo Platform Engineering Requirement]`  
The operator shall be able to issue `POST /api/v1/jobs/{id}/cancel`. The system shall cooperatively signal cancellation tokens, terminate spawned FFmpeg or headless browser processes, and transition job state to `cancelled`.

#### FR-096 — Durable SSE Streaming & Last-Event-ID Reconnect
`[Limo Platform Engineering Requirement]`  
The system shall stream real-time stage progress over Server-Sent Events (`/api/v1/jobs/{id}/stream`). All events shall be persisted in the database; disconnected clients supplying `Last-Event-ID` shall receive missed events without duplicate execution.

#### FR-097 — Multi-Worker DB Claims, Lease Management & Crash Recovery
`[Limo Platform Engineering Requirement]`  
Background workers shall claim queued jobs via database row locking (`lease_owner`, `lease_expires_at`). On system restart, stale/abandoned jobs shall be identified and recovered or marked failed safely.

#### FR-098 — Dual-Surface Authentication (Google OAuth vs. Desktop Bypass)
`[Limo Platform Engineering Requirement]`  
The platform shall support dual authentication modes:
- **Hosted Web Demo**: Enforces Google Sign-In (OAuth 2.0 / PKCE) across API endpoints with secure, HTTP-only session cookies.
- **Offline / Desktop Electron**: Bypasses authentication automatically to provide zero-friction local desktop usability.

#### FR-099 — Dual-Database Parity (SQLite / PostgreSQL)
`[Limo Platform Engineering Requirement]`  
The repository layer shall maintain identical schema and query semantics across local SQLite (with WAL mode) and enterprise cloud PostgreSQL.

---

### 3.7 Advanced Artifact Lifecycle, Unified Desktop Shell & Social Skills (Phase D10)

#### FR-100 — Real Physical Artifact Integrity & Cascading Deletion
`[Limo Platform Engineering Requirement]`  
The system shall strictly verify physical file presence on disk before registering artifact records. `DELETE /api/v1/artifacts/{id}` shall execute cascading deletion of physical storage files, thumbnail images, version history, and database rows.

#### FR-101 — External Disk Edit Detection & Automatic Versioning (`sync_artifact_file`)
`[Limo Platform Engineering Requirement]`  
When an external application (e.g. GenOffice Docs, Slides, Sheets) modifies an artifact on disk, the system shall detect changes via SHA-256 comparison, save an `ArtifactVersion` snapshot of the previous state, update the parent artifact metadata, and increment version numbers automatically.

#### FR-102 — Unified Desktop Shell Container (`AppFrame.tsx`)
`[Limo Platform Engineering Requirement]`  
The platform shall operate within a unified Electron desktop shell featuring a top view switcher allowing instant toggle between `💬 Limo AI` chat and `📄 Office Workspace`, keeping all activities in a single window.

#### FR-103 — Native Loopback Document Opener
`[Limo Platform Engineering Requirement]`  
Clicking **'Edit in GenOffice'** on a document deliverable card shall issue an authenticated loopback command (`POST http://127.0.0.1:48123/api/v1/open`), spawning GenOffice if closed and opening the file as an active tab immediately.

#### FR-104 — Modular File-Backed Skill Discovery Engine
`[Limo Platform Engineering Requirement]`  
The system shall dynamically index skills from root `skills/` and `builtin/skills/` directories, exposing metadata and prompt contracts via `GET /api/v1/skills`.

#### FR-105 — Interactive Social Draft Presentation Cards
`[NTRO Problem Statement Core Requirement]` `[NTRO PS-FR-22]`  
Generated social media outputs (LinkedIn, Twitter/X, Instagram) shall render inside specialized `SocialDraftCard` components featuring platform branding, prominent `Draft` indicators, live character counts, in-place edit/save capabilities, and direct download buttons.

#### FR-106 — Ready-to-Publish Clipboard Sanitizer (`toPublishablePlainText`)
`[Limo Platform Engineering Requirement]`  
Copying social draft content to the clipboard shall automatically strip markdown formatting (bold asterisks, heading hashes, markdown link syntax) while preserving actual hashtags and natural spacing, producing paste-ready text for publishing.

---

### 3.8 Web Reach, Research & SSRF Hardening (Phase D8.9)

#### FR-082 — Zero-Configuration Web Search Discovery
`[Limo Platform Engineering Requirement]`  
The system shall provide zero-configuration web search discovery using `ddgs` as the default search provider, enabling live information retrieval without requiring external cloud API keys or programmable search engine IDs.

#### FR-083 — Multi-Tier Resilient Web Content Extraction
`[Limo Platform Engineering Requirement]`  
The system shall extract structured article content across three bounded tiers:
1. Fast HTTP fetch + `trafilatura` for clean structured article extraction.
2. `crawl4ai` dynamic headless browser fallback for JavaScript-rendered web applications.
3. In-process `BeautifulSoup4` fallback for resilient extraction.

#### FR-084 — Full-Spectrum SSRF Protection & Network Interception
`[Limo Platform Engineering Requirement]`  
All outbound HTTP requests and Playwright browser page navigations/subresources (scripts, images, stylesheets, iframes, fetch/XHR) shall be intercepted and validated before leaving the host, blocking private IP ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback interfaces (`127.0.0.0/8`, `::1`, `localhost`), and cloud instance metadata (`169.254.169.254`).

#### FR-085 — Dual Provenance Tracking
`[Limo Platform Engineering Requirement]`  
The system shall track and persist dual provenance metadata for all web-derived sources, recording both `search_provider` (`"ddgs" | "google"`) and `scrape_provider` (`"trafilatura" | "crawl4ai" | "fallback"`).

#### FR-086 — Single-Authority Freshness & Search Exhaustion Guard
`[Limo Platform Engineering Requirement]`  
Temporal intent translation shall be strictly governed by the intent resolver (`timelimit="d" | "w" | "m" | "y"`). If search returns zero results, the system shall report an explicit negative disclosure rather than hallucinating from LLM model memory.

---

## 4. Non-Functional Requirements

### 4.1 Security & Sandboxing
- **NFR-001 — Secret Protection:** API keys and credentials shall remain strictly server-side and masked in logging.
- **NFR-002 — Storage Path Sandboxing:** All file operations shall be bounded to the canonical `data/` directory, preventing path traversal attacks.
- **NFR-003 — SSRF Network Isolation:** Outbound HTTP clients and headless browser runners shall validate IP addresses against reserved and cloud-metadata ranges.
- **NFR-004 — Model Reasoning Privacy:** Private model chain-of-thought shall never be persisted or displayed as public user-facing chat history.

### 4.2 Performance & Responsiveness
- **NFR-005 — Asynchronous Non-Blocking Execution:** Long-running transformations shall execute asynchronously in background tasks without blocking client HTTP threads.
- **NFR-006 — Low-Latency Intent Resolution:** Fast intent gate shall classify user requests in less than 20 milliseconds.
- **NFR-007 — Real-Time Streaming:** Background job progress and status shall stream over SSE with sub-second event latency.

### 4.3 Reliability & Truthful Generation
- **NFR-008 — Zero-Mock Guarantee:** The platform shall never output fake artifacts, mock file paths, or simulated generation progress.
- **NFR-009 — Graceful Job Recovery:** Interrupted or crashed jobs shall be safely identified and transitioned to failed/recoverable states upon restart.
- **NFR-010 — Atomic Artifact Writes:** Artifacts shall be staged and validated before registration, preventing partial or corrupted deliverable records.

---

## 5. Phase Implementation Status & Traceability (D1 to D14)

### 5.1 Completed Phases (D1 to D10)

| Phase | Title | Status | Verifiable Engineering Deliverables |
| :--- | :--- | :--- | :--- |
| **D1** | Project Foundation & Isolation | **COMPLETED & VERIFIED** | FastAPI backend, Vite React frontend, multi-process isolation boundaries, environment validation. |
| **D2** | Conversational UI & Shell | **COMPLETED & VERIFIED** | Chat workspace, dark mode UI, composer feature pills, markdown renderer, artifact cards. |
| **D3** | Backend Core & Persistence | **COMPLETED & VERIFIED** | SQLite with WAL mode, Pydantic v2 domain schemas, sandboxed storage service, SHA-256 digests. |
| **D4** | Limo Agent & LLM Runtime | **COMPLETED & VERIFIED** | Agent loop, tool registry, hook system, token budgeting, Google GenAI SDK (Gemini) provider adapter. |
| **D5** | Content Ingestion & Canonical | **COMPLETED & VERIFIED** | Multi-format extraction (DOCX, PDF, XLSX, HTML), Canonical Content Model, lexical BM25 retrieval. |
| **D6** | Transformation Planning & Native | **COMPLETED & VERIFIED** | `TransformationConfigResolver`, `OutputPlanner`, native adapters (MD, HTML, LinkedIn, X, SVG), SSE broker. |
| **D7** | GenOffice Desktop Automation | **COMPLETED & VERIFIED** | JSON-RPC automation bridge, native office routing (Docs, Slides, Sheets), Fast Intent Gate (`IntentResolver`). |
| **D8** | Media, Video, Prismo & Web | **COMPLETED & VERIFIED** | OpenMontage MP4 video engine, multi-provider TTS (Azure, Edge, Gemini), Prismo 1080x1440 infographic compiler, DDGS web search with SSRF browser hardening. |
| **D9** | Distributed Background Jobs & Security | **COMPLETED & VERIFIED** | Multi-worker background queue, lease management, durable SSE replay (`Last-Event-ID`), cooperative cancellation, Google OAuth 2.0 PKCE authentication, dual DB parity. |
| **D10** | Artifact Lifecycle, Unified Shell & Social | **COMPLETED & VERIFIED** | Real physical artifact validation, cascading deletion, `sync_artifact_file` external change detection, unified Electron desktop shell (`AppFrame.tsx`), loopback opener (`POST /open`), file-backed skill registry (`GET /api/v1/skills`), interactive social draft cards with markdown-stripping plain text copy. |

### 5.2 Remaining Phases (D11 to D14 — Future Roadmap)

| Phase | Title | Target Scope |
| :--- | :--- | :--- |
| **D11** | Cryptographic Integrity & Blockchain Provenance | Merkle-tree verification over `Source -> Canonical -> Output Plan -> Artifact`. Exportable W3C Verifiable Credentials and pluggable decentralized ledger anchors for tamper-evident provenance (directly addressing NTRO Theme: *Blockchain & Cybersecurity*). |
| **D12** | Desktop Packaging & Installer | Multi-platform Electron builder packaging, one-click installer (NSIS, DMG, AppImage) bundling embedded Python runtime. |
| **D13** | Stress, Chaos & Fault Tolerance | High-concurrency load testing (20+ concurrent multi-deliverable jobs), network chaos injection, memory leak and subprocess orphan audits. |
| **D14** | Final Polish & Evaluation Demonstrations | Final latency optimizations, demo scenarios covering intelligence advisories, multi-document synthesis, and video publication. |

---

## 6. Requirement Traceability Matrix

### 6.1 NTRO Problem Statement Compliance Matrix

| NTRO Problem Statement Mandate | Requirement Tag | Limo Implementation Phase | Verified Engine / Component | Automated Test Suite |
| :--- | :--- | :--- | :--- | :--- |
| **Source Submission (Text, Documents, Media, Prompts)** | `[NTRO PS-FR-01, 02, 03]` | Phase D5.1, D5.2 | `SourceService`, `ExtractionService` (DOCX, PDF, XLSX, HTML, Images, Audio, Video) | `test_d5_ingestion.py`, `test_d5_extraction_documents.py` |
| **Context & Objective Understanding** | `[NTRO PS-FR-04, 05, 06]` | Phase D4, D5.3, D5.4 | `CanonicalContent`, Gemini 2.5/3.5 Structured Extraction | `test_d5_canonical.py`, `test_d5_normalization.py` |
| **Configurable Parameters (Audience, Tone, Detail, Style)** | `[NTRO PS-FR-08 to 13]` | Phase D6.1, D6.2 | `TransformationConfigResolver`, `OutputPlanner` | `test_d6_config_resolver.py`, `test_d6_output_planner.py` |
| **Simultaneous Multi-Output Generation** | `[NTRO PS-FR-07, 14]` | Phase D6.4 | `WorkflowOrchestrator` Sibling Dispatch Pipeline | `test_d6_workflow_orchestrator.py`, `test_d6_integration.py` |
| **Example 1: Complete Video Package** | `[NTRO PS-FR-21]` | Phase D8.0–D8.6 | OpenMontage Subprocess + TTS + Synchronized Captions + Video Player | `test_d8_2_video_engine_integration.py`, `test_d8_3_tts_voice_layer.py`, `test_d8_5_video_player_integration.py` |
| **Example 2: Professional LinkedIn Post** | `[NTRO PS-FR-18]` | Phase D6.3, D10.7 | LinkedIn Skill (`skills/linkedin/SKILL.md`) + `SocialDraftCard` | `test_d10_acceptance.py`, `test_social_turn_execution.py` |
| **Example 3: Platform-Optimized Twitter/X Thread** | `[NTRO PS-FR-19]` | Phase D6.3, D10.8 | Twitter Skill (`skills/twitter/SKILL.md`) + Character Limiter | `test_d10_acceptance.py`, `test_social_turn_execution.py` |
| **Example 4: Structured Advisory Document** | `[NTRO PS-FR-15]` | Phase D6.3, D7.5 | Native Markdown Advisory / GenOffice Docs Automation (`.docx`) | `test_d6_native_adapters.py`, `test_genoffice_d7_5_handoff.py` |
| **Example 5: High-Fidelity Infographic** | `[NTRO PS-FR-20]` | Phase D8.8 | Prismo TypeScript Compiler + WCAG AA Contrast Validators (`.png`) | `test_d8_8_prismo_integration.py`, `test_prismo_timeout_fixes.py` |
| **Example 6: Concise Executive Summary** | `[NTRO PS-FR-16]` | Phase D6.3, D7.5 | Native Markdown Executive Memo / GenOffice Docs | `test_d6_native_adapters.py`, `test_genoffice_d7_5_handoff.py` |
| **Example 7: Presentation Slides & Speaker Notes** | `[NTRO PS-FR-17]` | Phase D7.5 | GenOffice Slides Automation Bridge (`.pptx` + Speaker Notes) | `test_genoffice_d7_5_handoff.py` |
| **Interactive Social Draft Cards & Plaintext Copy** | `[NTRO PS-FR-22]` | Phase D10.3, D10.10 | `SocialDraftCard.tsx` + `toPublishablePlainText()` | `test_d10_acceptance.py` |
| **Real-Time Web Search & Ingestion** | `[Limo Platform Engineering]` | Phase D8.9 | Zero-Config DDGS Provider + Multi-Tier Web Extractor + SSRF Protection | `test_d8_9_web_reach.py` (33 tests), Live Browser Matrix |
| **Background Jobs & SSE Reconnection** | `[Limo Platform Engineering]` | Phase D9.1–D9.4 | Background Worker Queue + Lease Manager + `Last-Event-ID` SSE | `test_d9_db_claims_and_queue.py`, `test_d9_cancellation_and_recovery.py`, `test_d9_durable_sse_stream.py` |
| **Unified Shell & External File Sync** | `[Limo Platform Engineering]` | Phase D10.1–D10.5 | Unified Electron Shell (`AppFrame.tsx`) + `sync_artifact_file` | `test_d10_acceptance.py` |

---

## 7. Final Requirement & Compliance Statement

Limo delivers an intelligent, production-ready, and verifiable automated content transformation workspace built to fulfill the mission requirements of the **National Technical Research Organisation (NTRO)** under the **Blockchain & Cybersecurity** theme:

1. **Heterogeneous Input Ingestion**: Seamlessly ingests threat intelligence, incident reports, research papers, news articles, policy documents, raw text, and media.
2. **Deterministic Understanding & Canonical Truth**: Grounded in an immutable Canonical Content Model that prevents AI hallucination and fact drift.
3. **Multi-Deliverable Execution**: Concurrently transforms a single source into complete video packages, structured advisories, executive summaries, presentation decks, infographics, and platform-optimized social posts.
4. **Desktop Native & Office Integration**: Operates within a single unified desktop window with direct bidirectional loopback editing in GenOffice Docs, Slides, and Sheets.
5. **Security & Cryptographic Integrity**: Bounded by full-spectrum SSRF network defenses, sandboxed storage boundaries, streaming SHA-256 digests, and prepared for decentralized Merkle-tree provenance verification.
