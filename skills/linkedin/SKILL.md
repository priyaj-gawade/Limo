---
name: linkedin
description: "Professional LinkedIn post, article, hook generation, and source-grounded repurposing"
version: "1.0.0"
category: "social"
triggers:
  - "linkedin"
  - "linkedin post"
  - "professional post"
  - "repurpose for linkedin"
  - "linkedin carousel"
  - "b2b post"
deliverables:
  - "linkedin"
  - "post"
modes:
  - "docs"
  - "none"
intents:
  - "repurpose"
  - "social_draft"
  - "executive_brief"
supported_inputs:
  - "raw text"
  - "canonical content"
  - "pdf"
  - "docx"
  - "xlsx"
  - "research"
supported_outputs:
  - "linkedin post"
  - "linkedin carousel outline"
  - "linkedin comment draft"
required_tools:
  - "social_adapter"
  - "canonical_content"
---

# LinkedIn Professional Repurposing Skill

## Overview
Transforms research reports, spreadsheets, slide decks, and canonical content into high-engagement, executive-level LinkedIn content.

## Core Capabilities
1. **Professional Hook Generation**: Scroll-stopping first lines with high information density, problem statements, or surprising data points without clickbait.
2. **Source-Grounded Summarization**: Every assertion, figure, or takeaway is strictly cited from D5 Canonical Content and verified sources. Zero hallucination.
3. **Long-Form Repurposing**: Distills lengthy whitepapers, PDF/DOCX reports, or XLSX sheets into punchy executive briefings.
4. **Call to Action (CTA)**: Contextual questions prompting peer discussion or next strategic steps.
5. **Carousel Outline**: Structured slide-by-slide outline (Hook -> Context -> Data -> Analysis -> Conclusion -> CTA).
6. **Comment/Reply Drafting**: Professional, value-adding response templates.
7. **Draft Humanization**: Eliminates corporate buzzwords ("synergy", "paradigm shift", "delve") in favor of direct, authoritative communication.

## Publication-Ready Format
Write a natural, publication-ready LinkedIn post directly:
- **Title / Opening Hook**: A scroll-stopping opening line.
- **Post Body**: Clear, readable paragraphs separated by clean line breaks.
- **Hashtags**: Place 3 to 5 curated hashtags at the very bottom (e.g., `#CareerMilestone #Micron #Management`).
- **No Schema Noise**: Do not output database schema keys, YAML headers, or metadata labels like `platform:`, `hook:`, or `source_references:`. Provide clean, ready-to-publish text.

## Integrity & Non-Faking Rules
- DEFAULT STATUS IS ALWAYS `Draft`.
- NEVER claim an account is connected.
- NEVER claim a post was published or scheduled.
- NEVER fabricate analytics, impression counts, or engagement rates.
- If real publishing is not connected, the artifact remains purely a first-class local draft deliverable.
