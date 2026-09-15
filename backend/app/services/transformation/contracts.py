"""Generation Contract Builder (Phase D6.3).

Translates (CanonicalContent, PlannedDeliverable, GenerationConfig) into strongly-typed
external engine execution payloads without invoking external binaries:
- GenOfficePayload for GenOffice Electron Main (Phase D7)
- VideoEnginePayload for Video Engine (versioned contract designed for future D8 adapter)
"""

import logging
import re
import time
from typing import List, Optional

from ...models.content import CanonicalContent
from ...models.enums import OutputFormat
from ...models.generation_config import GenerationConfig
from ...models.generation_contracts import (
    GenOfficeOptions,
    GenOfficePayload,
    VideoEnginePayload,
    VideoGenerationContract,
    VideoScriptScene,
    VideoScriptSection,
    VideoVoiceConfig,
    VideoBrief,
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

    @staticmethod
    def build_video_generation_contract(
        canonical: CanonicalContent,
        deliverable: PlannedDeliverable,
        config: GenerationConfig,
        job_id: str,
        conversation_id: Optional[str] = None,
    ) -> VideoGenerationContract:
        """Construct an authoritative D8.1/D8.2 VideoGenerationContract for OpenMontage runner."""
        clean_job_id = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", job_id)
        if not clean_job_id or clean_job_id in (".", ".."):
            clean_job_id = f"job_{int(time.time())}"

        target_dur = float(config.video.target_duration_sec if config.video else 15.0)
        target_dur = max(3.0, min(300.0, target_dur))

        aspect_ratio = config.video.aspect_ratio if config.video else "16:9"
        if aspect_ratio not in ("16:9", "9:16", "1:1"):
            aspect_ratio = "16:9"

        # Resolve voice provider and voice ID from config or deliverable options
        selected_provider = (
            (config.video.voice_provider if config.video else None)
            or (deliverable.options or {}).get("voice_provider")
        )
        selected_voice = (
            (config.video.voice_id if config.video else None)
            or (deliverable.options or {}).get("voice_id")
            or (config.video.voice_profile if config.video and config.video.voice_profile != "professional_neutral" else None)
        )

        try:
            from ..tts.registry import tts_registry
            p_adapter, v_meta = tts_registry.resolve_voice(voice_id=selected_voice, provider=selected_provider)
            final_provider = p_adapter.id
            final_voice_id = v_meta.voice_id
        except Exception:
            final_provider = selected_provider or "edge_tts"
            final_voice_id = selected_voice or "en-US-AndrewMultilingualNeural"

        voice_config = VideoVoiceConfig(
            provider=final_provider,
            voice_id=final_voice_id,
            speed=1.0,
            pitch=0.0,
        )

        stock_prov = (deliverable.options or {}).get("stock_provider", "auto")
        subtitles = config.video.include_subtitles if config.video else True
        options = {
            "stock_provider": stock_prov,
            "burn_subtitles": subtitles,
        }

        # 1. Clean topic from raw prompt or title to prevent command leakage
        raw_topic = canonical.title or deliverable.title or "Informative Overview"
        clean_topic = re.sub(r"^(?:please\s+)?(?:create|make|generate|produce|build|draft)\s+(?:a|an)?\s*", "", raw_topic, flags=re.IGNORECASE)
        clean_topic = re.sub(r"\b(?:\d+)\s*(?:-|secs?|seconds?)\s*(?:video|clip|reel)?\s*(?:about|on|covering|explaining)?\b", "", clean_topic, flags=re.IGNORECASE)
        clean_topic = re.sub(r"^(?:video|clip|reel)\s+(?:about|on|covering|explaining)\s*", "", clean_topic, flags=re.IGNORECASE)
        clean_topic = re.sub(r"\b(?:video|clip|reel)\b", "", clean_topic, flags=re.IGNORECASE)
        clean_topic = " ".join(clean_topic.split()).strip().title()
        if not clean_topic:
            clean_topic = "Informative Overview"

        # 2. Extract sanitized key factual points (not command text)
        key_points: List[str] = []
        if canonical.facts:
            key_points.extend(f.statement for f in canonical.facts if f.statement)
        if canonical.events:
            key_points.extend(f"{e.title}: {e.significance}" for e in canonical.events if e.title)
        if canonical.data_points:
            key_points.extend(f"{dp.metric}: {dp.value} {dp.unit}" for dp in canonical.data_points)
        if not key_points and canonical.context and len(canonical.context) > 20:
            key_points.append(canonical.context[:150])

        # 3. Construct sanitized creative VideoBrief
        audience = (
            canonical.intent.target_audiences[0]
            if canonical.intent and canonical.intent.target_audiences
            else "General Audience"
        )
        brief = VideoBrief(
            topic=clean_topic,
            target_duration_seconds=target_dur,
            aspect_ratio=aspect_ratio,
            audience=audience,
            tone="inspirational, educational",
            language=config.language or "en",
            key_points=key_points[:5],
            voice_config=voice_config,
        )

        # 4. Pre-planned script sections: only if explicitly provided in deliverable options.
        # Otherwise empty by default so OpenMontage Director Agent writes the authentic script.
        sections: List[VideoScriptSection] = (deliverable.options or {}).get("script_sections", [])

        contract = VideoGenerationContract(
            job_id=clean_job_id,
            title=clean_topic,
            conversation_id=conversation_id,
            topic=clean_topic,
            target_duration_seconds=target_dur,
            aspect_ratio=aspect_ratio,
            style_playbook="clean-professional",
            render_runtime="ffmpeg",
            voice_config=voice_config,
            subtitles=subtitles,
            script_sections=sections,
            brief=brief,
            user_directive=(deliverable.options or {}).get("user_directive") or (deliverable.options or {}).get("raw_prompt") or None,
            options=options,
        )

        logger.info(
            "Built VideoGenerationContract for job '%s': topic='%s' (target: %.1fs, brief key_points: %d)",
            clean_job_id,
            clean_topic,
            target_dur,
            len(key_points),
        )
        return contract


generation_contract_builder = GenerationContractBuilder()
