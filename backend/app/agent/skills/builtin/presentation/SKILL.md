---
name: presentation
description: Executive slide decks, keynote outlines, visual hierarchy, and speaker notes.
category: deliverable
triggers:
  - presentation
  - slides
  - slide deck
  - pitch deck
  - pptx
  - keynote
deliverables:
  - pptx
  - presentation
modes:
  - slides
intents:
  - generate_presentation
  - create_slides
  - outline_deck
required_tools:
  - source_read
  - transform_contract
  - artifact_tool
---

# Presentation & Slide Deck Skill

## Objective
Structure visually coherent, impactful slide presentations with disciplined content density and clear speaker notes.

## Domain Guidelines
1. **Slide Architecture**:
   - Title Slide: Clear headline, concise subtitle, context/date/author.
   - Executive Context / The "Why": The central challenge or market opportunity.
   - Key Pillars (3-5 slides): Focused on one main insight per slide with supporting metrics and visual cues.
   - Conclusion / Next Steps: Clear decision requests or roadmaps.
2. **Design Discipline**:
   - 6x6 Rule: Avoid paragraph walls on slides. Prefer bullet points under 6 words and strong visual headlines.
   - Highlight Metrics: Dedicated callout stat cards for key figures (e.g. "+34% YoY", "$12.4M ARR").
   - Speaker Notes: Include detailed rationale and talking points in speaker notes rather than cluttering slide canvas.
3. **Execution Pattern**:
   - Query source facts using `source_read`.
   - Synthesize a slide-by-slide storyboard.
   - Queue transformation contract using `transform_contract` with `requested_formats=['presentation']`.
