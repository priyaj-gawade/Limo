---
name: instagram
description: "Engaging Instagram captions, Reel hooks, carousel outlines, and visual media suggestions"
version: "1.0.0"
category: "social"
triggers:
  - "instagram"
  - "ig"
  - "caption"
  - "reel"
  - "instagram carousel"
  - "ig post"
deliverables:
  - "instagram"
  - "post"
modes:
  - "none"
  - "image"
  - "video"
intents:
  - "social_draft"
  - "repurpose"
supported_inputs:
  - "raw text"
  - "canonical content"
  - "media assets"
  - "user instructions"
supported_outputs:
  - "caption"
  - "reel hook and script"
  - "carousel outline"
  - "hashtag suggestions"
required_tools:
  - "social_adapter"
---

# Instagram Visual Storytelling Skill

## Overview
Adapts analytical insights and stories into visual social formats: feed captions, Reel scripts with hooks, and structured educational carousel outlines.

## Core Capabilities
1. **Feed Caption Drafting**: Compelling opening line visible before "...more", micro-paragraphs, clean spacing, and conversational tone.
2. **Reel Hook & Script Cues**:
   - 0-3s visual and spoken hook.
   - Pacing cues for fast-retention delivery.
   - Audio/B-roll prompt recommendations.
3. **Carousel Outline**:
   - Slide 1: High-contrast cover slide concept & title.
   - Slides 2-7: One idea per slide with headline, visual graphic cue, and brief body text.
   - Final Slide: Summary & Save/Share call to action.
4. **Context-Aware Hashtags**: Categorized hashtag cluster (domain, community, niche).
5. **Media Suggestions**: Recommended aspect ratio (4:5 vertical portrait for feed, 9:16 for Reels, 1:1 square).

## Publication-Ready Format
Write clean, ready-to-publish Instagram content:
- **Carousels**:
  - Caption text at the top with hashtags at the end of the caption.
  - Slide by slide breakdown:
    `Slide 1: [Cover Headline]`
    `Slide 2: [Headline & body]`
- **Feed / Reels**: A compelling hook opening, clean spaced paragraphs, and hashtags at the bottom.
- **No Schema Noise**: Do not output database schema keys or YAML headers like `platform:`, `hook:`, or `media_suggestion:`. Provide clean, ready-to-publish text.

## Integrity & Non-Faking Rules
- DEFAULT STATUS IS ALWAYS `Draft`.
- NEVER claim an Instagram account is connected.
- NEVER claim a Reel or post was published.
- NEVER fabricate reach, views, or trending analytics without a real connected API.
