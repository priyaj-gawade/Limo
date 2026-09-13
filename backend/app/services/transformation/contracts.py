"""Generation Contract Builder (Phase D6.3).

Translates (CanonicalContent, PlannedDeliverable, GenerationConfig) into strongly-typed
external engine execution payloads without invoking external binaries:
- GenOfficePayload for GenOffice Electron Main (Phase D7)
- VideoEnginePayload for Video Engine (versioned contract designed for future D8 adapter)
"""

import logging
from typing import List, Optional

from ...models.content import CanonicalContent
from ...models.enums import OutputFormat
from ...models.generation_config import GenerationConfig
from ...models.generation_contracts import (
    GenOfficeOptions,
    GenOfficePayload,
    VideoEnginePayload,
    VideoScriptScene,
)
from ...models.transformation import PlannedDeliverable

logger = logging.getLogger("limo.services.transformation.contracts")


class GenerationContractBuilder:
    """Deterministic builder creating external engine execution contracts from CanonicalContent."""

    @staticmethod
    def build_genoffice_payload(
        canonical: CanonicalContent,
        deliverable: PlannedDeliverable,
        config: GenerationConfig,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> GenOfficePayload:
        """Construct a validated GenOfficePayload for future D7 Electron automation."""
        # Map deliverable format to GenOffice document type
        fmt_map = {
            OutputFormat.DOCUMENT: "document",
            OutputFormat.PRESENTATION: "presentation",
            OutputFormat.SPREADSHEET: "spreadsheet",
            OutputFormat.ADVISORY: "document",
            OutputFormat.SUMMARY: "document",
            OutputFormat.PDF: "pdf",
            OutputFormat.MARKDOWN: "markdown",
            OutputFormat.HTML: "html",
        }
        doc_type = fmt_map.get(deliverable.format, "document")

        # Synthesize grounded prompt
        prompt = (
            f"Generate a professional {deliverable.format.value} deliverable titled '{deliverable.title}'. "
            f"Core objective: {config.objective.value if hasattr(config.objective, 'value') else config.objective}. "
            f"Audience: {config.audience}. "
            f"Narrative: {canonical.intent.core_narrative} "
            f"Context: {canonical.context}"
        )

        # Extract structured sections/slides outline from canonical intent and facts
        outline: List[str] = [
            f"Executive Summary: {canonical.intent.primary_purpose}",
            f"Situational Context: {canonical.title}",
        ]
        for fact in canonical.facts[:6]:
            outline.append(f"Key Finding: {fact.statement}")
        for dp in canonical.data_points[:4]:
            outline.append(f"Metric: {dp.metric} = {dp.value} {dp.unit or ''}".strip())
        for rec in canonical.recommendations[:4]:
            outline.append(f"Recommendation: {rec}")

        # Determine target page count and theme based on format options
        is_pres = deliverable.format == OutputFormat.PRESENTATION
        theme = (config.presentation.theme or "slate_corporate") if (is_pres and config.presentation) else "slate_corporate"
        page_defaults = {OutputFormat.PRESENTATION: (config.presentation.slide_count if config.presentation else 10), OutputFormat.DOCUMENT: 5, OutputFormat.ADVISORY: 5, OutputFormat.SUMMARY: 2}
        approx_pages = page_defaults.get(deliverable.format)

        options = GenOfficeOptions(
            title=deliverable.title,
            approx_pages=approx_pages,
            theme=theme,
            audience=config.audience,
            tone=config.tone,
            detail_level=config.detail_level.value if hasattr(config.detail_level, "value") else config.detail_level,
            canonical_id=canonical.id,
            canonical_hash=canonical.content_hash,
            sections_outline=outline,
            custom_metadata=deliverable.options,
        )

        payload = GenOfficePayload(
            type=doc_type,
            prompt=prompt,
            project_id=project_id,
            session_id=session_id,
            options=options,
        )

        logger.info(
            "Built GenOffice generation contract for '%s' (type: %s, outline items: %d)",
            deliverable.title,
            doc_type,
            len(outline),
        )
        return payload

    @staticmethod
    def build_video_payload(
        canonical: CanonicalContent,
        deliverable: PlannedDeliverable,
        config: GenerationConfig,
    ) -> VideoEnginePayload:
        """Construct a versioned VideoEnginePayload designed for the future D8 adapter."""
        scenes: List[VideoScriptScene] = []
        scene_idx = 1

        # Scene 1: Hook / Introduction
        scenes.append(
            VideoScriptScene(
                scene_index=scene_idx,
                visual_cue=f"Title graphic: '{deliverable.title}' with high-contrast text overlay",
                narration_text=f"{canonical.intent.core_narrative} Here is the executive breakdown.",
                estimated_duration_seconds=10,
            )
        )
        scene_idx += 1

        # Scene 2..N: Fact and Event scenes
        if canonical.events:
            for ev in canonical.events[:4]:
                sig = f" ({ev.significance})" if ev.significance else ""
                time_str = f"In {ev.timestamp_desc}: " if ev.timestamp_desc else ""
                scenes.append(
                    VideoScriptScene(
                        scene_index=scene_idx,
                        visual_cue=f"Timeline infographic displaying event: {ev.title}",
                        narration_text=f"{time_str}{ev.title}{sig}.",
                        estimated_duration_seconds=15,
                    )
                )
                scene_idx += 1
        else:
            for fact in canonical.facts[:3]:
                scenes.append(
                    VideoScriptScene(
                        scene_index=scene_idx,
                        visual_cue=f"Key stat and factual highlight: {fact.statement[:60]}...",
                        narration_text=f"Key finding: {fact.statement}",
                        estimated_duration_seconds=12,
                    )
                )
                scene_idx += 1

        # Metrics Scene if data points exist
        if canonical.data_points:
            metrics_summary = "; ".join(f"{dp.metric} stands at {dp.value} {dp.unit or ''}".strip() for dp in canonical.data_points[:3])
            scenes.append(
                VideoScriptScene(
                    scene_index=scene_idx,
                    visual_cue="Animated KPI metric counters and comparative bar chart",
                    narration_text=f"Examining the numbers: {metrics_summary}.",
                    estimated_duration_seconds=15,
                )
            )
            scene_idx += 1

        # Final Scene: Actionable takeaway & Outro
        rec_summary = (
            f"Action required: {canonical.recommendations[0]}"
            if canonical.recommendations
            else "Review the complete briefing for technical specifications."
        )
        scenes.append(
            VideoScriptScene(
                scene_index=scene_idx,
                visual_cue="Closing card with actionable recommendations and provenance citation",
                narration_text=f"{rec_summary} Provenance verified against source repository.",
                estimated_duration_seconds=10,
            )
        )

        total_duration = sum(s.estimated_duration_seconds for s in scenes)
        # Cap total duration to user length budget if specified
        target_dur = config.video.target_duration_sec if config.video else 60
        total_duration = min(total_duration, target_dur)

        voice_prof = config.video.voice_profile if config.video else "professional_neutral"
        aspect_ratio = config.video.aspect_ratio if config.video else "16:9"
        subtitles = config.video.include_subtitles if config.video else True

        payload = VideoEnginePayload(
            title=deliverable.title,
            script_blueprint=scenes,
            audio_config={
                "voice_profile": voice_prof,
                "speech_rate": 1.0,
                "language": config.language,
            },
            visual_config={
                "aspect_ratio": aspect_ratio,
                "visual_style": "corporate_clean",
                "subtitles": subtitles,
            },
            estimated_duration_seconds=total_duration,
            canonical_id=canonical.id,
            canonical_hash=canonical.content_hash,
        )

        logger.info(
            "Built Video Engine generation contract for '%s' (%d scenes, %ds duration)",
            deliverable.title,
            len(scenes),
            total_duration,
        )
        return payload


generation_contract_builder = GenerationContractBuilder()
