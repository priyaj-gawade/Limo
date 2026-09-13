---
name: research
description: Deep source analysis, entity extraction, fact synthesis, and literature cross-referencing.
category: analysis
triggers:
  - research
  - analyze sources
  - extract facts
  - investigate
  - background
  - deep dive
deliverables:
  - summary
  - brief
modes:
  - docs
  - chat
intents:
  - deep_research
  - analyze_sources
  - extract_entities
required_tools:
  - source_read
  - project_tool
  - chat_tool
---

# Deep Research & Source Analysis Skill

## Objective
Guide the agent in conducting thorough, evidence-grounded research across ingested project sources without hallucinations.

## Domain Guidelines
1. **Evidence-Grounded Synthesis**:
   - Every major assertion or statistical figure must be directly attributable to an ingested source.
   - Explicitly note conflicting data points across sources rather than silently picking one.
   - When information is missing from sources, clearly state: "The ingested sources do not provide data on X."
2. **Analysis Structure**:
   - Core Findings: Bulleted list of confirmed facts with source attribution.
   - Entity & Timeline Mapping: Key organizations, actors, dates, and milestone events.
   - Unresolved Questions / Knowledge Gaps: Nuances requiring further investigation.
3. **Execution Pattern**:
   - List available sources via `source_read(action='list_sources')`.
   - Read specific passages using `source_read(action='get_source_content')`.
   - Synthesize research findings into conversational responses or structured notes.
