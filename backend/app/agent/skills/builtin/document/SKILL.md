---
name: document
description: Professional executive briefs, formal reports, and multi-section documentation.
category: deliverable
triggers:
  - document
  - report
  - executive brief
  - docx
  - article
  - whitepaper
  - writeup
deliverables:
  - docx
  - brief
  - summary
modes:
  - docs
intents:
  - generate_document
  - write_report
  - create_brief
required_tools:
  - source_read
  - transform_contract
  - artifact_tool
---

# Document Generation & Synthesis Skill

## Objective
Guide the agent in structuring high-quality, professional written documents, executive briefs, and whitepapers.

## Domain Guidelines
1. **Structural Hierarchy**:
   - Executive Summary (150-250 words): Key findings, metrics, and strategic recommendations.
   - Background & Objectives: Problem framing and relevant context.
   - Core Analysis & Detailed Findings: Thematic sections with data points, qualitative synthesis, and structured callouts.
   - Strategic Recommendations & Action Items: Prioritized next steps with assigned owners/milestones.
2. **Tone & Style**:
   - Objective, analytical, and authoritative.
   - Avoid generic AI filler phrases (e.g. "In today's fast-paced world", "delve into").
   - Prefer concrete numbers, percentages, and direct source attributions over vague adjectives.
3. **Execution Pattern**:
   - Inspect project sources using `source_read`.
   - Formulate structured document outline.
   - Queue the document transformation contract using `transform_contract` with `requested_formats=['document']`.
