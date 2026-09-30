---
name: twitter
description: "High-impact single posts, viral hooks, and concise multi-tweet threads strictly within 280 characters"
version: "1.0.0"
category: "social"
triggers:
  - "twitter"
  - "x"
  - "tweet"
  - "thread"
  - "twitter thread"
  - "tweetstorm"
deliverables:
  - "twitter"
  - "post"
modes:
  - "none"
intents:
  - "social_draft"
  - "repurpose"
supported_inputs:
  - "raw text"
  - "canonical content"
  - "pdf"
  - "research"
  - "user instructions"
supported_outputs:
  - "single tweet"
  - "multi-tweet thread"
  - "reply draft"
required_tools:
  - "social_adapter"
---

# X / Twitter High-Impact Publishing Skill

## Overview
Engineers concise, high-signal single posts and multi-tweet threads from complex source materials, respecting strict platform character constraints.

## Core Capabilities
1. **Single Post Drafting**: Punchy, standalone insights with strong hooks.
2. **Multi-Tweet Threads**:
   - Numbered sequence formatting (`1/N` through `N/N`).
   - Dedicated hook tweet.
   - Core finding / data breakdown tweets.
   - Actionable takeaway / recommendation tweets.
   - Closing provenance / conclusion tweet.
3. **Strict 280-Character Boundary**: Every tweet item is verified to remain <= 280 characters.
4. **Concise Repurposing**: Compresses dense reports and data into atomic, readable ideas.
5. **Reply Drafting**: Thoughtful replies for joining relevant community discussions.

## Publication-Ready Format
Write clean, ready-to-publish tweets directly (each tweet strictly <= 280 characters):
- **Single Tweets**: Output the clean tweet text with hashtags at the bottom.
- **Threads**: Format each tweet cleanly using numbered indicators (e.g. `1/3 ...`, `2/3 ...`, `3/3 ...`) or separated by `---`.
- **No Schema Noise**: Do not output database schema keys or YAML headers like `platform:`, `hook:`, or `items:`. Provide clean, ready-to-publish text.

## Integrity & Non-Faking Rules
- DEFAULT STATUS IS ALWAYS `Draft`.
- ZERO simulated posting, scheduling, or automated publishing.
- ZERO fabricated Twitter API connections or fake metrics (retweets, likes, impressions).
