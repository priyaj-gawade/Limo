"""Deterministic native social media adapters (Phase D6.3).

Synthesizes structured professional social media drafts strictly derived from CanonicalContent:
- OutputFormat.LINKEDIN: Professional markdown article / post (.md)
- OutputFormat.TWITTER: Multi-tweet thread JSON with strictly <= 280 character tweets (.json)
"""

import json
import re
from typing import List

from ....models.content import CanonicalContent
from ....models.enums import ArtifactType, OutputFormat
from ....models.generation_config import GenerationConfig
from ....models.generation_contracts import TweetItem, TwitterThreadPayload
from ....models.transformation import PlannedDeliverable
from .base import BaseNativeAdapter, GeneratedContent, make_slug


class NativeSocialAdapter(BaseNativeAdapter):
    """Deterministic native adapter for professional LinkedIn, X/Twitter, and Instagram content."""

    def synthesize(
        self,
        canonical: CanonicalContent,
        deliverable: PlannedDeliverable,
        config: GenerationConfig,
    ) -> GeneratedContent:
        if deliverable.format == OutputFormat.TWITTER:
            return self._synthesize_twitter(canonical, deliverable, config)
        elif deliverable.format == OutputFormat.INSTAGRAM:
            return self._synthesize_instagram(canonical, deliverable, config)
        return self._synthesize_linkedin(canonical, deliverable, config)

    def _synthesize_linkedin(
        self,
        canonical: CanonicalContent,
        deliverable: PlannedDeliverable,
        config: GenerationConfig,
    ) -> GeneratedContent:
        lines: List[str] = []

        # 1. Professional Hook
        hook = f"🚨 {deliverable.title}: What every leader needs to know today."
        lines.append(hook)
        lines.append("")
        lines.append(canonical.intent.core_narrative)
        lines.append("")

        # 2. Key Grounded Takeaways
        lines.append("Here are the critical takeaways from our analysis:")
        lines.append("")
        for fact in canonical.facts[:4]:
            lines.append(f"📌 {fact.statement}")
        lines.append("")

        # 3. Data & Metrics Highlight
        if canonical.data_points:
            lines.append("By the numbers:")
            for dp in canonical.data_points[:3]:
                ctx = f" ({dp.context})" if dp.context else ""
                lines.append(f"🔹 {dp.metric}: **{dp.value} {dp.unit or ''}**{ctx}".strip())
            lines.append("")

        # 4. Strategic Recommendation / Call to Action
        if canonical.recommendations:
            lines.append("Strategic next steps:")
            for rec in canonical.recommendations[:2]:
                lines.append(f"👉 {rec}")
            lines.append("")

        lines.append("What are your teams prioritizing to address this? Let's discuss in the comments below.")
        lines.append("")

        # 5. Curated Hashtags from entities & domain topics
        hashtags: List[str] = ["#Leadership", "#Strategy", "#ExecutiveBriefing"]
        for ent in canonical.entities[:3]:
            clean_tag = "#" + re.sub(r"[^a-zA-Z0-9]", "", ent.name)
            if len(clean_tag) > 2 and clean_tag not in hashtags:
                hashtags.append(clean_tag)
        lines.append(" ".join(hashtags[:5]))

        content_str = "\n".join(lines)
        content_bytes = content_str.encode("utf-8")

        clean_slug = make_slug(deliverable.title, fallback="linkedin_post")
        filename = f"{clean_slug}_linkedin.md"

        word_count = len(content_str.split())
        stats = f"{word_count} words • LinkedIn Post • Draft"

        # Structured draft object
        structured_draft = {
            "platform": "linkedin",
            "format": "post",
            "hook": hook,
            "content": content_str,
            "hashtags": hashtags[:5],
            "source_references": [f.source_reference for f in canonical.facts if f.source_reference],
            "warnings": [],
            "media_suggestion": "Single high-contrast infographic chart or executive portrait",
            "status": "Draft",
        }

        return GeneratedContent(
            content_bytes=content_bytes,
            filename=filename,
            file_format=".md",
            artifact_type=ArtifactType.POST,
            stats=stats,
            metadata={
                "platform": "linkedin",
                "format": "post",
                "status": "Draft",
                "hook": hook,
                "hashtags": hashtags[:5],
                "word_count": word_count,
                "social_draft": structured_draft,
                "engine": "social",
                "skill": "linkedin",
            },
        )

    def _synthesize_twitter(
        self,
        canonical: CanonicalContent,
        deliverable: PlannedDeliverable,
        config: GenerationConfig,
    ) -> GeneratedContent:
        raw_tweets: List[str] = []

        # 1. Opening Tweet / Hook
        hook = f"🧵 1/{{total}}: {deliverable.title}\n\n{canonical.intent.core_narrative}"
        raw_tweets.append(hook)

        # 2. Key Facts Tweets
        for fact in canonical.facts[:3]:
            body = f"Key finding:\n\n{fact.statement}"
            ref = f"\n\nSource ref: {fact.source_reference}" if fact.source_reference else ""
            raw_tweets.append(f"{{num}}/{{total}} {body}{ref}")

        # 3. Data Points Tweet
        if canonical.data_points:
            metrics = "\n".join(f"• {dp.metric}: {dp.value} {dp.unit or ''}".strip() for dp in canonical.data_points[:2])
            raw_tweets.append(f"{{num}}/{{total}} The data behind the trend:\n\n{metrics}")

        # 4. Actionable Takeaway Tweet
        if canonical.recommendations:
            rec = canonical.recommendations[0]
            raw_tweets.append(f"{{num}}/{{total}} Key recommendation:\n\n{rec}")

        # 5. Closing / Provenance Tweet
        raw_tweets.append(
            f"{{num}}/{{total}} End of thread. Verified against canonical provenance digest: {canonical.content_hash[:12]}..."
        )

        total_tweets = len(raw_tweets)
        tweet_items: List[TweetItem] = []

        for idx, tmpl in enumerate(raw_tweets, 1):
            formatted_text = tmpl.replace("{total}", str(total_tweets)).replace("{num}", str(idx))

            # Strictly enforce the 280 character limit with deterministic truncation if necessary
            if len(formatted_text) > 280:
                suffix = "..."
                formatted_text = formatted_text[: 280 - len(suffix)] + suffix

            tweet_items.append(
                TweetItem(
                    tweet_number=idx,
                    text=formatted_text,
                    char_count=len(formatted_text),
                )
            )

        thread_payload = TwitterThreadPayload(
            topic=deliverable.title,
            tweets=tweet_items,
            total_tweets=total_tweets,
        )

        # Structured draft object
        structured_draft = {
            "platform": "twitter",
            "format": "thread",
            "hook": tweet_items[0].text if tweet_items else "",
            "content": "\n\n---\n\n".join(t.text for t in tweet_items),
            "items": [t.model_dump() for t in tweet_items],
            "total_tweets": total_tweets,
            "hashtags": [],
            "source_references": [f.source_reference for f in canonical.facts if f.source_reference],
            "warnings": [],
            "status": "Draft",
        }

        content_bytes = thread_payload.model_dump_json(indent=2).encode("utf-8")
        clean_slug = make_slug(deliverable.title, fallback="twitter_thread")
        filename = f"{clean_slug}_thread.json"

        stats = f"{total_tweets} Tweets • X/Twitter Thread • Draft"

        return GeneratedContent(
            content_bytes=content_bytes,
            filename=filename,
            file_format=".json",
            artifact_type=ArtifactType.POST,
            stats=stats,
            metadata={
                "platform": "twitter",
                "format": "thread",
                "status": "Draft",
                "total_tweets": total_tweets,
                "hook": tweet_items[0].text if tweet_items else "",
                "max_char_count": max(t.char_count for t in tweet_items) if tweet_items else 0,
                "social_draft": structured_draft,
                "engine": "social",
                "skill": "twitter",
            },
        )

    def _synthesize_instagram(
        self,
        canonical: CanonicalContent,
        deliverable: PlannedDeliverable,
        config: GenerationConfig,
    ) -> GeneratedContent:
        # 1. Catchy Visual Hook
        hook = f"✨ {deliverable.title}: The 3-minute breakdown."

        # 2. Carousel Slide Outlines
        slides: List[Dict[str, Any]] = []
        slides.append({
            "slide_number": 1,
            "type": "cover",
            "headline": deliverable.title,
            "subheadline": canonical.intent.core_narrative[:100],
            "visual_prompt": "Bold high-contrast title card on dark background",
        })

        for idx, fact in enumerate(canonical.facts[:4], 2):
            slides.append({
                "slide_number": idx,
                "type": "insight",
                "headline": f"Insight #{idx - 1}",
                "body": fact.statement,
                "visual_prompt": "Clean minimalist infographic layout with emphasis on key statistic",
            })

        if canonical.data_points:
            metrics_str = ", ".join(f"{dp.metric}: {dp.value}" for dp in canonical.data_points[:2])
            slides.append({
                "slide_number": len(slides) + 1,
                "type": "data",
                "headline": "By The Numbers",
                "body": metrics_str,
                "visual_prompt": "Data callout card with large typography and clean icon",
            })

        slides.append({
            "slide_number": len(slides) + 1,
            "type": "cta",
            "headline": "Save this for later",
            "body": "Follow for daily high-signal research breakdowns. Share with someone who needs this.",
            "visual_prompt": "Save/Bookmark prompt with clean aesthetic branding",
        })

        # 3. Instagram Caption
        caption_lines: List[str] = [
            hook,
            "",
            canonical.intent.core_narrative,
            "",
            "SWIPE ➡️ for the complete breakdown.",
            "",
            "Key Highlights:",
        ]
        for fact in canonical.facts[:3]:
            caption_lines.append(f"• {fact.statement}")
        caption_lines.append("")
        caption_lines.append("Drop your thoughts in the comments below! 👇")
        caption_lines.append("")

        # 4. Context-aware Hashtags
        hashtags = ["#infographic", "#research", "#learning", "#insights", "#data"]
        for ent in canonical.entities[:3]:
            clean_tag = "#" + re.sub(r"[^a-zA-Z0-9]", "", ent.name.lower())
            if len(clean_tag) > 2 and clean_tag not in hashtags:
                hashtags.append(clean_tag)
        caption_lines.append(" ".join(hashtags[:7]))

        caption_str = "\n".join(caption_lines)

        structured_draft = {
            "platform": "instagram",
            "format": "carousel",
            "hook": hook,
            "content": caption_str,
            "slides": slides,
            "total_slides": len(slides),
            "hashtags": hashtags[:7],
            "source_references": [f.source_reference for f in canonical.facts if f.source_reference],
            "media_suggestion": "Carousel 4:5 portrait (1080x1350px) or Reel 9:16 (1080x1920px)",
            "warnings": [],
            "status": "Draft",
        }

        content_bytes = json.dumps(structured_draft, indent=2).encode("utf-8")
        clean_slug = make_slug(deliverable.title, fallback="instagram_carousel")
        filename = f"{clean_slug}_instagram.json"

        stats = f"{len(slides)} Slides • Instagram Carousel • Draft"

        return GeneratedContent(
            content_bytes=content_bytes,
            filename=filename,
            file_format=".json",
            artifact_type=ArtifactType.POST,
            stats=stats,
            metadata={
                "platform": "instagram",
                "format": "carousel",
                "status": "Draft",
                "total_slides": len(slides),
                "hook": hook,
                "hashtags": hashtags[:7],
                "social_draft": structured_draft,
                "engine": "social",
                "skill": "instagram",
            },
        )
