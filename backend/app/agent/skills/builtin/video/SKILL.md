---
name: video
description: Video scripts, scene pacing, visual prompts, and narration timing cues.
category: deliverable
triggers:
  - video
  - script
  - narration
  - storyboard
  - mp4
  - voiceover
deliverables:
  - video
modes:
  - video
intents:
  - generate_video
  - write_video_script
  - create_storyboard
required_tools:
  - source_read
  - transform_contract
  - artifact_tool
---

# Video Script & Storyboard Skill

## Objective
Guide the agent in structuring timed narration scripts, scene transitions, and visual prompts for downstream video rendering (OpenMontage / MoneyPrinterTurbo).

## Domain Guidelines
1. **Scene Architecture**:
   - Scene ID & Timestamp Range (e.g. `[00:00 - 00:05] Scene 1: Hook`).
   - Visual Description: Concrete imagery, camera angle, and on-screen text overlays.
   - Narration Script: Exact spoken dialogue optimized for text-to-speech cadence.
   - Pacing: Target ~130-150 words per minute for engaging pacing.
2. **Structural Flow**:
   - Hook (0-5s): Gripping premise or provocative question.
   - Core Explanation (5-50s): Rapid delivery of 3 key points with distinct visual changes every 3-5 seconds.
   - Call to Action / Resolution (50-60s): Crisp summary and next step.
3. **Execution Pattern**:
   - Synthesize script and visual scene prompts from sources using `source_read`.
   - Queue video transformation contract using `transform_contract` with `requested_formats=['video']`.
