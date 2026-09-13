Problem Statement Title

Gen AI Platform for Automated Content Transformation

Description

• Background Organisations frequently need to convert information available in different forms such as news articles, reports, advisories, threat intelligence, policy documents, research papers, announcements, incident reports or free-form prompts into specific communication artefacts suitable for various purposes. The process of manually analysing the source content, understanding the desired objective and creating the required output format is time-consuming, resource-intensive and often requires expertise in content creation, communication and domain knowledge.

There is a need for an intelligent platform that can transform user-provided content into a desired output format through a simple and configurable interface.

• Description The system shall act as an AI-powered content transformation engine that converts a common source of information into the specific deliverable requested by the operator, thereby reducing manual effort, improving consistency, accelerating content creation and enhancing operational efficiency.

The platform shall provide a dashboard through which an operator can submit source content in the form of high quality English language text, documents, articles, reports, prompts, images, videos or contextual information. In addition to providing the source content, the operator shall select one or more desired output types through configurable parameters available on the dashboard.

Based on the submitted content and the selected output type(s), the platform shall analyze the input, understand the context and intent, and generate the requested output artefact. The platform should support multiple output formats and allow operators to control generation parameters such as target audience, tone, language, level of detail, communication objective and content style.

In summary, platform shall generate output corresponding to the option(s) selected by the operator on the dashboard.

• Examples include
• If 'Video' is selected, generate a complete video package including script, storyboard, scene descriptions, narration text, subtitles and visual recommendations.
• If 'LinkedIn Post' is selected, generate a professional LinkedIn post suitable for publication.
• If 'Twitter/X Post' is selected, generate platform-optimized tweets or tweet threads.
• If 'Advisory' is selected, generate a structured advisory document.
• If 'Infographic' is selected, generate infographic content, layout recommendations and key messaging.
• If 'Executive Summary' is selected, generate a concise executive briefing.
• If 'Presentation' is selected, generate presentation slides and speaker notes.
• If multiple output formats are selected, generate all selected deliverables from the same source content.
• Expected Solution/Deliverables for Evaluation
• Source Code Link (GitHub/Drive Link)
• Readme with Setup Instructions
• Architecture Document (Max 2 Pages)
• Demo Video (Max 2 Minutes)
• Technical Presentation (Max 5 Slides)


Organization

National Technical Research Organisation (NTRO)

Department

National Technical Research Organisation (NTRO)

Category

Software

Theme

Blockchain & Cybersecurity

## NTRO Content Transformation Modules

| #  | Module                                  | What it does                                                                                                  | Build / Reuse                               | Open-source tools                               |
| -- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------- | ----------------------------------------------- |
| 1  | **Universal Input Processing**          | Accept text, PDF/DOCX, articles, reports, images, videos and prompts and convert them into normalized content | **Build + integrate**                       | Unstructured, PaddleOCR, FFmpeg, faster-whisper |
| 2  | **Content Extraction & Normalization**  | Extract text, tables, metadata, headings and useful information from inputs                                   | **Mostly integrate + custom normalization** | Unstructured, PaddleOCR                         |
| 3  | **Content Understanding Engine**        | Understand topic, context, intent, entities, facts and important information                                  | **Build**                                   | LLM + LangGraph                                 |
| 4  | **Canonical Content Model**             | Convert the understood source into one structured representation used by every generator                      | **Build**                                   | Pydantic/JSON Schema                            |
| 5  | **Generation Configuration Engine**     | Apply audience, tone, language, detail level, objective and style                                             | **Build**                                   | LLM + structured prompts                        |
| 6  | **Output Orchestrator / Router**        | Decide which generators to execute when one or multiple outputs are selected                                  | **Build**                                   | LangGraph                                       |
| 7  | **LinkedIn Post Generator**             | Produce a professional LinkedIn post                                                                          | **Build**                                   | LLM                                             |
| 8  | **Twitter/X Generator**                 | Produce optimized post or thread                                                                              | **Build**                                   | LLM                                             |
| 9  | **Advisory Generator**                  | Produce a structured advisory document                                                                        | **Build**                                   | LLM + python-docx/WeasyPrint                    |
| 10 | **Executive Summary Generator**         | Produce a concise executive briefing                                                                          | **Build**                                   | LLM                                             |
| 11 | **Infographic Generator**               | Generate infographic content, key messages and layout/visual recommendations                                  | **Build**                                   | LLM + SVG/HTML/CSS; optional image model        |
| 12 | **Presentation Generator**              | Generate slides + speaker notes                                                                               | **Build logic + reuse renderer**            | PptxGenJS                                       |
| 13 | **Video Planning Generator**            | Generate script, storyboard, scenes, narration, subtitles plan and visual recommendations                     | **Build**                                   | LLM                                             |
| 14 | **Video Generation/Rendering**          | Convert video plan into actual video                                                                          | **Reuse/integrate**                         | MoneyPrinterTurbo + FFmpeg                      |
| 15 | **Subtitle Generation**                 | Generate/transcribe subtitle timings                                                                          | **Reuse/integrate**                         | faster-whisper                                  |
| 16 | **Output Validation / Quality Control** | Check generated content for structure, missing fields, unsupported claims, length and format                  | **Build**                                   | LLM-as-judge + JSON Schema/Pydantic             |
| 17 | **Source-to-Output Traceability**       | Preserve which source facts contributed to each generated output                                              | **Build**                                   | Metadata + hashes                               |
| 18 | **Content Provenance / Integrity**      | Create tamper-evident records for source and generated artefacts                                              | **Build**                                   | SHA-256 + Hyperledger Fabric                    |

The core problem statement specifically requires the system to analyze the source, understand context and intent, support configurable generation parameters, and generate Video, LinkedIn, X, Advisory, Infographic, Executive Summary and Presentation outputs. 

---

# 1. Universal Input Processing

This is the first major module.

```text
TEXT ──────┐
PDF ───────┤
DOCX ──────┤
ARTICLE ───┤
IMAGE ────►│ Input Processing
VIDEO ─────┤
PROMPT ────┘
```

### Use

**Unstructured** for extracting content from complex documents; its open-source repository is Apache 2.0. ([GitHub][1])

**PaddleOCR** for image/scanned-document OCR and document parsing. Its repository is Apache 2.0 and its current project includes document-layout and parsing capabilities. ([GitHub][2])

**faster-whisper** for extracting speech from video/audio. It is a faster implementation of Whisper using CTranslate2. ([GitHub][3])

Your own code then normalizes all of that into a common format.

---

# 2. Content Understanding Engine

This is one of the **most important modules you should build yourself**.

```text
Normalized Input
       ↓
Content Understanding
       ↓
Topic
Context
Intent
Entities
Facts
Events
Key Points
```

For example, an intelligence report could become:

```json
{
  "topic": "Cyber attack",
  "intent": "Inform",
  "entities": ["Organization A", "Threat Actor B"],
  "key_facts": [],
  "events": [],
  "impact": [],
  "recommendations": []
}
```

### Tool

**LangGraph** is a good orchestration framework for building stateful, multi-step LLM workflows. ([GitHub][4])

---

# 3. Canonical Content Model

I would consider this **your main original engineering component**.

Every input becomes something like:

```json
{
  "source": {},
  "context": {},
  "intent": {},
  "facts": [],
  "entities": [],
  "events": [],
  "claims": [],
  "references": []
}
```

Then:

```text
              Canonical Content
                    │
       ┌────────────┼────────────┐
       ↓            ↓            ↓
    LinkedIn      Video         PPT
       ↓            ↓            ↓
     Output       Output        Output
```

This prevents you from building seven unrelated prompt systems.

---

# 4. Generation Configuration Engine

The NTRO statement explicitly requires:

* Target audience
* Tone
* Language
* Level of detail
* Communication objective
* Content style 

Create one shared configuration:

```json
{
  "audience": "Executive",
  "tone": "Formal",
  "language": "English",
  "detail": "Detailed",
  "objective": "Inform",
  "style": "Professional"
}
```

Every generator receives this.

---

# 5. Output Orchestrator

Suppose the operator selects:

```text
☑ Video
☑ Advisory
☑ LinkedIn
☐ PPT
```

The orchestrator executes:

```text
Canonical Content
       ↓
Output Router
   ├── Video
   ├── Advisory
   └── LinkedIn
```

### Recommended tool

**LangGraph** because the workflow can branch into multiple generation paths. ([GitHub][4])

---

# 6. LinkedIn Generator

Custom module:

```text
Canonical Content
       ↓
LinkedIn Transformation
       ↓
Professional Post
```

No specialized open-source generator is necessary. This is mostly **your transformation prompt/schema/validation logic + LLM**.

---

# 7. X/Twitter Generator

```text
Canonical Content
       ↓
X Transformation
       ↓
Single Post / Thread
```

Again, build this yourself around your LLM.

---

# 8. Advisory Generator

```text
Canonical Content
       ↓
Advisory Template
       ↓
Structured Advisory
       ↓
PDF / DOCX
```

The problem specifically asks for a **structured advisory document**. 

You can use:

* `python-docx`
* WeasyPrint
* ReportLab

for document rendering.

The **actual advisory intelligence and structure** should be yours.

---

# 9. Executive Summary Generator

```text
Large Source
    ↓
Content Understanding
    ↓
Prioritization
    ↓
Executive Summary
```

The LLM performs the transformation, while your module controls the schema and constraints.

---

# 10. Infographic Generator

The problem requires:

**content + layout recommendations + key messaging**. 

So don't start by trying to build Canva.

Generate:

```json
{
  "title": "...",
  "headline": "...",
  "key_message": "...",
  "sections": [],
  "visual_elements": [],
  "layout": {
    "type": "timeline"
  }
}
```

Then optionally render that to SVG/PNG.

---

# 11. Presentation Generator

Pipeline:

```text
Canonical Content
       ↓
Slide Planner
       ↓
Slide JSON
       ↓
PptxGenJS
       ↓
.pptx
```

**PptxGenJS** is an MIT-licensed library that generates real PowerPoint files and supports text, images, shapes, tables, charts and media. ([GitHub][5])

This means you don't have to write PowerPoint XML yourself.

---

# 12. Video Generator

This needs to be split into two modules.

### A. Video Planner — **build**

```text
Content
 ↓
Script
 ↓
Storyboard
 ↓
Scenes
 ↓
Narration
 ↓
Visual Recommendations
```

### B. Video Renderer — **reuse**

**MoneyPrinterTurbo** already provides an automated AI workflow for generating short videos and is MIT licensed. ([GitHub][6])

So:

```text
Your Video Planner
        ↓
MoneyPrinterTurbo
        ↓
     MP4
```

This is a major time saver.

---

# 13. Subtitle Module

Use **faster-whisper** rather than implementing speech recognition.

It supports transcription and can be used to create timestamped subtitle data. ([GitHub][3])

---

# 14. Output Validation

This isn't explicitly named in the problem statement, but **I strongly recommend it**.

For example:

```text
LLM Output
   ↓
Schema Validation
   ↓
Fact / Citation Check
   ↓
Length Check
   ↓
Safety / Policy Check
   ↓
Final Output
```

This is particularly valuable for the **cybersecurity/NTRO context**, because blindly publishing hallucinated information would be a serious weakness.

---

# 15. Provenance + Blockchain

This is where I would connect the SIH theme to the actual platform.

```text
Original Source
      ↓
SHA-256
      ↓
Blockchain Record
      ↓
AI Transformation
      ↓
Generated Output
      ↓
SHA-256
      ↓
Blockchain Record
```

### Technology

**Hyperledger Fabric** would be the natural permissioned-DLT candidate for this architecture.

Store things such as:

```text
Source Hash
Output Hash
Transformation ID
Timestamp
Version
Model ID
```

Don't put the actual PDF/video/report on-chain.

Put the **proof of integrity** on-chain.

---

# Recommended final module architecture

```text
                ┌─────────────────────┐
                │   INPUT PROCESSOR   │
                └──────────┬──────────┘
                           ↓
                ┌─────────────────────┐
                │ CONTENT UNDERSTANDING│
                └──────────┬──────────┘
                           ↓
                ┌─────────────────────┐
                │ CANONICAL CONTENT   │
                │      MODEL          │
                └──────────┬──────────┘
                           ↓
                ┌─────────────────────┐
                │ GENERATION CONFIG   │
                └──────────┬──────────┘
                           ↓
                ┌─────────────────────┐
                │  OUTPUT ORCHESTRATOR│
                └──────────┬──────────┘
                           ↓
       ┌────────┬────────┬────────┬─────────┬──────────┐
       ↓        ↓        ↓        ↓         ↓          ↓
   LinkedIn     X     Advisory  Summary  Infographic   PPT
                                                   │
                                                   ↓
                                                 Video
                                                   
       └───────────────────┬───────────────────────────┘
                           ↓
                  OUTPUT VALIDATION
                           ↓
                 PROVENANCE / HASHING
                           ↓
                  HYPERLEDGER FABRIC
```

## The stack, condensed

**Your team should build:**

`Content Understanding → Canonical Content → Configuration → Output Router → 7 Output Generators → Validation → Provenance`

**Use open source for:**

`Document parsing → OCR → Video transcription → Video rendering → PPT rendering → RAG/vector search`

### Best tools for each

| Function                  | Recommended tool                    |
| ------------------------- | ----------------------------------- |
| AI orchestration          | **LangGraph** ([GitHub][4])         |
| Document extraction       | **Unstructured** ([GitHub][1])      |
| OCR                       | **PaddleOCR** ([GitHub][2])         |
| Video/audio transcription | **faster-whisper** ([GitHub][3])    |
| Video generation          | **MoneyPrinterTurbo** ([GitHub][6]) |
| PowerPoint generation     | **PptxGenJS** ([GitHub][5])         |
| Vector/RAG                | **Qdrant** ([GitHub][7])            |
| Blockchain/provenance     | **Hyperledger Fabric**              |
| Media processing          | **FFmpeg**                          |
| Structured data           | **Pydantic / JSON Schema**          |

One correction from my earlier answer: **Dify is useful, but I would not make it the core of your implementation if the goal is to demonstrate your own transformation architecture**, especially because its current open-source license is Apache-2.0-based with additional conditions. ([GitHub][8]) **LangGraph is cleaner for making the orchestration layer explicitly yours.**

This gives you a clear division between **"we built the intelligence"** and **"we leveraged proven open-source infrastructure."**

[1]: https://github.com/orgs/Unstructured-IO/repositories?utm_source=chatgpt.com "Unstructured-IO repositories · GitHub"
[2]: https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/index.en.md?utm_source=chatgpt.com "PaddleOCR/docs/index.en.md at main · PaddlePaddle/PaddleOCR · GitHub"
[3]: https://github.com/SYSTRAN/faster-whisper?utm_source=chatgpt.com "GitHub - SYSTRAN/faster-whisper: Faster Whisper transcription with CTranslate2 · GitHub"
[4]: https://github.com/langchain-ai/langgraph?utm_source=chatgpt.com "GitHub - langchain-ai/langgraph: Build resilient agents. · GitHub"
[5]: https://github.com/gitbrent/pptxgenjs?utm_source=chatgpt.com "GitHub - gitbrent/PptxGenJS: Build PowerPoint presentations with JavaScript. Works with Node, React, web browsers, and more. · GitHub"
[6]: https://github.com/harry0703/MoneyPrinterTurbo/blob/main/LICENSE?utm_source=chatgpt.com "MoneyPrinterTurbo/LICENSE at main · harry0703/MoneyPrinterTurbo · GitHub"
[7]: https://github.com/ngogiaphat/Qdrant?utm_source=chatgpt.com "GitHub - ngogiaphat/Qdrant: Qdrant - High-performance, massive-scale Vector Database for the next generation of AI. Also available in the cloud https://cloud.qdrant.io/ · GitHub"
[8]: https://github.com/langgenius/dify?utm_source=chatgpt.com "GitHub - langgenius/dify: Build Agentic workflows, RAG pipelines, with rich AI model and tool support on one collaborative workspace. Deploy on cloud, VPC, or self-hosted, so teams move from prototype to production without rebuilding the stack. · GitHub"
