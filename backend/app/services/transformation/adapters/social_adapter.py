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
    """Deterministic native adapter for professional LinkedIn and X/Twitter content."""

    def synthesize(
        self,
        canonical: CanonicalContent,
        deliverable: PlannedDeliverable,
        config: GenerationConfig,
    ) -> GeneratedContent:
        if deliverable.format == OutputFormat.TWITTER:
            return self._synthesize_twitter(canonical, deliverable, config)
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
        stats = f"{word_count} words • LinkedIn Post (.md)"

        return GeneratedContent(
            content_bytes=content_bytes,
            filename=filename,
            file_format=".md",
            artifact_type=ArtifactType.POST,
            stats=stats,
            metadata={"platform": "linkedin", "hashtags": hashtags[:5], "word_count": word_count},
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

        content_bytes = thread_payload.model_dump_json(indent=2).encode("utf-8")
        clean_slug = make_slug(deliverable.title, fallback="twitter_thread")
        filename = f"{clean_slug}_thread.json"

        stats = f"{total_tweets} Tweets • X/Twitter Thread (.json)"

        return GeneratedContent(
            content_bytes=content_bytes,
            filename=filename,
            file_format=".json",
            artifact_type=ArtifactType.POST,
            stats=stats,
            metadata={"platform": "twitter", "total_tweets": total_tweets, "max_char_count": max(t.char_count for t in tweet_items)},
        )
