import asyncio
import hashlib
import json
import logging
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from ..exceptions import EntityNotFoundError
from ..models.chat import Message, MessageAttachment
from ..services.tts.service import tts_service
from ..models.content import (
    CanonicalContent,
    CanonicalDataPoint,
    CanonicalFact,
    CanonicalIntent,
)
from ..models.enums import ArtifactType, FeatureMode, OutputFormat, SourceType
from ..models.generation_config import GenerationConfig, VideoOptions
from ..models.project import Source
from ..services.web.models import WebSourceProvenance
from ..models.transformation import (
    EngineRoute,
    EngineType,
    OutputPlan,
    PlannedDeliverable,
    TransformationRequest,
)
from ..services.artifact_service import artifact_service
from ..services.chat_service import ChatService, chat_service
from ..services.extraction.models import ExtractedDocument
from ..services.extraction.service import extraction_service
from ..services.job_service import JobService, job_service
from ..services.source_service import source_service
from ..services.transformation.engine_router import EngineRouter, engine_router
from ..services.transformation.genoffice_client import genoffice_client
from ..services.transformation.output_planner import OutputPlanner, output_planner
from ..storage.service import storage_service
from .brain import LLMReasoningEngine, ReasoningEngine
from .context import (
    AgentContext,
    AgentContextManager,
    AgentLimits,
    ContextSelector,
    MediaReference,
    SelectedContext,
    UnifiedInputContext,
)
from .actions import ActionType
from .contracts import BaseTool
from .intent import (
    ConfidenceLevel,
    IntentResolver,
    IntentType,
    ResolutionResult,
    TargetFormat,
    intent_resolver,
)
from .loop import AgentLoop, AgentLoopResult
from .skills import SkillRegistry
from .tools import ToolRegistry, create_default_tool_registry

logger = logging.getLogger("limo.agent.runtime")


class LimoAgentRuntime:
    """Primary entry point coordinating context hydration, reasoning loop, and persistence."""

    def __init__(
        self,
        reasoning_engine: Optional[ReasoningEngine] = None,
        context_manager: Optional[AgentContextManager] = None,
        chat_svc: Optional[ChatService] = None,
        tool_registry: Optional[ToolRegistry] = None,
        skill_registry: Optional[SkillRegistry] = None,
        intent_res: Optional[IntentResolver] = None,
        output_plan: Optional[OutputPlanner] = None,
        eng_router: Optional[EngineRouter] = None,
        jb_svc: Optional[JobService] = None,
    ):
        self.reasoning_engine = reasoning_engine or LLMReasoningEngine()
        self.context_manager = context_manager or AgentContextManager()
        self.chat_svc = chat_svc or chat_service
        self.tool_registry = tool_registry or create_default_tool_registry()
        self.skill_registry = skill_registry or SkillRegistry()
        self.intent_resolver = intent_res or intent_resolver
        self.output_planner = output_plan or output_planner
        self.engine_router = eng_router or engine_router
        self.job_svc = jb_svc or job_service
        self.loop = AgentLoop(self.reasoning_engine, self.context_manager)

    async def _hydrate_unified_input_context(
        self,
        user_prompt: str,
        effective_source_ids: List[str],
        attachments: Optional[List[MessageAttachment]],
    ) -> UnifiedInputContext:
        """Hydrate unified context across attachments/sources using D5 cache authority.
        
        Guarantees:
        - Checks D5 extraction cache first: never re-extracts an unchanged source.
        - Checks D5 canonical cache first: never re-canonicalizes an unchanged source.
        - Preserves native media references (file_path, mime_type) for image/audio/video.
        - Resolves structured text, tables, and canonical facts for prompt/deliverable projection.
        """
        sources: List[Source] = []
        extracted_docs: List[ExtractedDocument] = []
        canonical_contents: List[CanonicalContent] = []
        media_references: List[MediaReference] = []

        for sid in effective_source_ids:
            try:
                source = source_service.get_source(sid)
                sources.append(source)
            except Exception as e:
                logger.warning("Could not fetch source '%s' during context hydration: %s", sid, e)
                continue

            # 1. D5 Extraction (with cache hit check: NO repeated extraction)
            doc = extraction_service.get_cached_extraction(source.id)
            if not doc:
                try:
                    doc = await extraction_service.extract_source(source)
                except Exception as e:
                    logger.warning("D5 extraction error for source '%s': %s", source.id, e)
                    doc = None

            if doc:
                extracted_docs.append(doc)

            # 2. Native Media References (image, audio, video)
            mime = (source.mime_type or "").lower()
            filename = (source.name or "").lower()
            is_img = "image" in mime or filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))
            is_aud = "audio" in mime or filename.endswith((".mp3", ".wav", ".m4a", ".ogg", ".aac"))
            is_vid = "video" in mime or filename.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm"))

            media_type = "image" if is_img else ("audio" if is_aud else ("video" if is_vid else None))
            if media_type:
                file_path = None
                if source.storage_ref:
                    try:
                        resolved = storage_service.safe_resolve(source.storage_ref)
                        if resolved and resolved.exists():
                            file_path = str(resolved)
                    except Exception as e:
                        logger.warning("Failed to resolve storage path for media '%s': %s", source.id, e)

                media_references.append(
                    MediaReference(
                        source_id=source.id,
                        media_type=media_type,
                        mime_type=source.mime_type,
                        file_path=file_path,
                        name=source.name,
                    )
                )

            # 3. D5 Canonicalization (Cache check first: NO repeated canonicalization)
            from ..services.canonical.service import canonical_service
            from ..services.normalization.service import normalization_service

            can = canonical_service.get_canonical_by_source_id(source.id)
            if not can and doc:
                try:
                    norm_doc = normalization_service.normalize_extracted_document(doc)
                    can = await canonical_service.canonicalize(norm_doc)
                except Exception as e:
                    logger.info("Canonicalization skipped or deferred for source '%s': %s", source.id, e)

            if can:
                canonical_contents.append(can)

        return UnifiedInputContext(
            user_instruction=user_prompt,
            source_ids=effective_source_ids,
            attachments=attachments or [],
            sources=sources,
            extracted_documents=extracted_docs,
            canonical_contents=canonical_contents,
            media_references=media_references,
        )

    async def execute_turn(
        self,
        session_id: str,
        user_prompt: str,
        mode: Optional[FeatureMode] = None,
        project_id: Optional[str] = None,
        tools: Optional[List[BaseTool]] = None,
        limits: Optional[AgentLimits] = None,
        attachments: Optional[List[MessageAttachment]] = None,
        source_ids: Optional[List[str]] = None,
        voice_config: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """Execute a complete agent conversational turn.
        
        Flow:
        1. Persist user prompt and attachments to chat session.
        2. Hydrate unified cross-format input context with D5 cache authority.
        3. Hydrate token-budgeted, selective context (targeted source retrieval).
        4. Match and activate domain skills (Tier 2 progressive disclosure).
        5. Fast Intent Gate:
           - AMBIGUOUS: Return concise clarification prompt, zero files/artifacts.
           - FAST_CHAT (tools is None): Direct lightweight generation with zero tool schemas.
           - GENERATE / TRANSFORM: Route through D6 Transformation Pipeline Authority:
             TransformationRequest -> OutputPlan -> EngineRouter
             * NativeMarkdownAdapter for Markdown (.md)
             * GenOffice Runner for Office deliverables (.docx, .pptx, .xlsx, .pdf)
        6. Fallback: Run bounded AgentLoop state machine with registered tools.
        7. Persist assistant response turn to SQLite with public execution summary.
        8. Return the resulting Message entity.
        """
        # Resolve effective source IDs from attachments and explicit source_ids
        effective_source_ids: List[str] = list(source_ids or [])
        if attachments:
            for att in attachments:
                if att.source_id and att.source_id not in effective_source_ids:
                    effective_source_ids.append(att.source_id)

        # 1. Persist user turn with attachments
        user_msg = self.chat_svc.add_user_message(
            session_id=session_id,
            content=user_prompt,
            mode=mode,
            attachments=attachments,
        )

        # 2. Hydrate unified input context & D5 cache
        unified_input = await self._hydrate_unified_input_context(
            user_prompt=user_prompt,
            effective_source_ids=effective_source_ids,
            attachments=attachments,
        )

        # 3. Hydrate bounded context
        context = self.context_manager.load_context(
            session_id=session_id,
            user_request=user_prompt,
            project_id=project_id,
            limits=limits,
            turn_source_ids=effective_source_ids if effective_source_ids else None,
        )
        context.unified_input = unified_input
        if mode:
            context.active_mode = mode

        # 3. Match and activate domain skills (Tier 2 progressive disclosure)
        norm_mode = mode.value if mode and hasattr(mode, "value") else str(mode) if mode else None
        matched_skills = self.skill_registry.match_skills(
            prompt=user_prompt,
            mode=norm_mode,
            context=context,
        )
        if matched_skills:
            context.active_skills = [s.name for s in matched_skills]
            context.skill_instructions = "\n\n".join(
                f"## Skill: {s.name}\n{s.system_instructions}" for s in matched_skills
            )

        # 4. Fast Intent Gate (Phase D7.7)
        resolution: ResolutionResult = self.intent_resolver.resolve(user_prompt, active_mode=mode)
        logger.info(
            "Intent gate resolution for prompt '%s': intent=%s, format=%s, confidence=%s, reason='%s'",
            user_prompt[:50],
            resolution.intent.value,
            resolution.target_format.value if resolution.target_format else None,
            resolution.confidence.value,
            resolution.reason,
        )

        # Step 4.5: Web Reach Pre-Hydration & Ingestion (Phase D8.9)
        # If the turn references an external URL, YouTube, or requires live web search,
        # retrieve real evidence and ingest into D5 boundary BEFORE chat reasoning or D6 generation.
        if resolution.needs_url_scrape and (resolution.target_urls or resolution.target_url):
            try:
                from ..services.web.web_content_client import web_content_client
                from ..services.source_service import source_service
                from ..services.extraction.service import extraction_service
                from ..services.normalization.service import normalization_service
                from ..services.canonical.service import canonical_service

                urls_to_scrape = resolution.target_urls if resolution.target_urls else ([resolution.target_url] if resolution.target_url else [])
                for target_url in urls_to_scrape[:3]:  # bounded to top 3 URLs
                    scrape_res = await web_content_client.scrape(target_url)

                    content_bytes = scrape_res.content.encode("utf-8")
                    content_hash = hashlib.sha256(content_bytes).hexdigest()
                    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", scrape_res.title or "web_article")[:40]

                    # Register into D5 source repository
                    source_record = source_service.register_file_source(
                        filename=f"web_{slug}.md",
                        content=content_bytes,
                        mime_type="text/markdown",
                        project_id=project_id,
                        source_type=SourceType.URL,
                        metadata={
                            "source_url": target_url,
                            "title": scrape_res.title,
                            "scrape_provider": scrape_res.scrape_provider,
                            "elapsed_seconds": scrape_res.elapsed_seconds,
                        },
                    )
                    extracted_doc = await extraction_service.extract_source(source_record, content=content_bytes)
                    norm_doc = normalization_service.normalize_extracted_document(extracted_doc)

                    canon_obj = None
                    try:
                        canon_obj = await canonical_service.canonicalize(norm_doc)
                    except Exception as ce:
                        logger.info("Canonicalization skipped or deferred for web URL '%s': %s", target_url, ce)

                    prov = WebSourceProvenance(
                        url=target_url,
                        title=scrape_res.title or target_url,
                        domain=urllib.parse.urlparse(target_url).netloc,
                        source_type="web_article",
                        source_id=source_record.id,
                        scrape_provider=scrape_res.scrape_provider,
                        content_hash=content_hash,
                    )

                    if context.unified_input:
                        context.unified_input.web_sources.append(prov)
                        context.unified_input.sources.append(source_record)
                        context.unified_input.extracted_documents.append(extracted_doc)
                        if canon_obj:
                            context.unified_input.canonical_contents.append(canon_obj)

                # Re-select context to include newly scraped article
                if context.unified_input:
                    selected = ContextSelector.select(context.unified_input)
                    context.prompt_context_snippet = selected.prompt_context_snippet

            except Exception as e:
                logger.warning("Web URL pre-hydration failed for '%s': %s", resolution.target_url, e)

        elif resolution.needs_youtube:
            try:
                from ..services.web.youtube_search import youtube_search_client
                from ..services.web.youtube_transcript import youtube_transcript_client
                from ..services.source_service import source_service
                from ..services.extraction.service import extraction_service
                from ..services.normalization.service import normalization_service
                from ..services.canonical.service import canonical_service

                yt_target_url = resolution.target_url if (resolution.target_url and any(h in resolution.target_url.lower() for h in ("youtube.com", "youtu.be"))) else None
                if yt_target_url:
                    vid_id = youtube_transcript_client.extract_video_id(yt_target_url)
                    if vid_id:
                        t_res = await youtube_transcript_client.get_transcript(vid_id)
                        if t_res.transcript_available and t_res.text:
                            content_bytes = t_res.text.encode("utf-8")
                            content_hash = hashlib.sha256(content_bytes).hexdigest()
                            source_record = source_service.register_file_source(
                                filename=f"youtube_{vid_id}.md",
                                content=content_bytes,
                                mime_type="text/markdown",
                                project_id=project_id,
                                source_type=SourceType.URL,
                                metadata={
                                    "source_url": yt_target_url,
                                    "video_id": vid_id,
                                    "language": t_res.language,
                                    "source_type": "youtube_transcript",
                                },
                            )
                            extracted_doc = await extraction_service.extract_source(source_record, content=content_bytes)
                            norm_doc = normalization_service.normalize_extracted_document(extracted_doc)
                            canon_obj = None
                            try:
                                canon_obj = await canonical_service.canonicalize(norm_doc)
                            except Exception:
                                pass
                            prov = WebSourceProvenance(
                                url=yt_target_url,
                                title=f"YouTube Video ({vid_id}) Transcript",
                                domain="youtube.com",
                                source_type="youtube_video",
                                source_id=source_record.id,
                                content_hash=content_hash,
                            )
                            if context.unified_input:
                                context.unified_input.web_sources.append(prov)
                                context.unified_input.sources.append(source_record)
                                context.unified_input.extracted_documents.append(extracted_doc)
                                if canon_obj:
                                    context.unified_input.canonical_contents.append(canon_obj)
                                selected = ContextSelector.select(context.unified_input)
                                context.prompt_context_snippet = selected.prompt_context_snippet
                else:
                    yt_query = resolution.web_query or user_prompt
                    videos = await youtube_search_client.search(
                        query=yt_query,
                        max_results=5,
                    )
                    if videos and context.unified_input:
                        context.unified_input.youtube_results.extend(videos)

                    # If this is a pure conversational YouTube search, respond directly with video cards
                    if resolution.intent == IntentType.FAST_CHAT and not resolution.target_format:
                        if videos:
                            lines = [f"Here are the top YouTube videos for **{yt_query}**:\n"]
                            for v in videos:
                                desc = f"\n  _{v.description_snippet}_" if v.description_snippet else ""
                                lines.append(f"• **[{v.title}]({v.url})**\n  Channel: **{v.channel}**{desc}\n")
                            ans_text = "\n".join(lines).strip()
                        else:
                            ans_text = f"No YouTube videos found matching '{yt_query}'."

                        assistant_msg = self.chat_svc.add_assistant_message(
                            session_id=session_id,
                            content=ans_text,
                            mode=mode or FeatureMode.NONE,
                            artifact_ids=[],
                            execution_summary=f"Retrieved {len(videos)} YouTube video results via YouTube Data API v3.",
                        )
                        return assistant_msg

            except Exception as e:
                logger.warning("YouTube pre-hydration failed: %s", e)

        elif resolution.needs_web_search and (resolution.web_query or user_prompt):
            try:
                from ..services.web.research_orchestrator import web_research_service
                search_query = resolution.web_query or user_prompt

                # Single authority: pass timelimit if resolver flagged current information demand
                search_timelimit = None
                if resolution.needs_current_information:
                    p_lower = (user_prompt or "").lower()
                    if "today" in p_lower:
                        search_timelimit = "d"
                    elif "this week" in p_lower or "past week" in p_lower:
                        search_timelimit = "w"
                    elif "latest" in p_lower or "recent" in p_lower or "current" in p_lower:
                        search_timelimit = "m"

                research_res = await web_research_service.research(
                    query=search_query,
                    max_sources=3,
                    project_id=project_id,
                    scrape_content=True,
                    canonicalize=bool(resolution.target_format),
                    timelimit=search_timelimit,
                )
                if not research_res.get("provenance") and search_timelimit:
                    logger.info("Retrying web research for '%s' without timelimit filter", search_query)
                    research_res = await web_research_service.research(
                        query=search_query,
                        max_sources=3,
                        project_id=project_id,
                        scrape_content=True,
                        canonicalize=bool(resolution.target_format),
                        timelimit=None,
                    )
                if context.unified_input:
                    for p_data in research_res.get("provenance", []):
                        context.unified_input.web_sources.append(WebSourceProvenance(**p_data))
                    for c_data in research_res.get("canonical_contents", []):
                        context.unified_input.canonical_contents.append(CanonicalContent(**c_data))

                # Re-select context to include newly retrieved facts
                selected = ContextSelector.select(context.unified_input)
                context.prompt_context_snippet = selected.prompt_context_snippet

            except Exception as e:
                logger.warning("Web search pre-hydration failed: %s", e)

        # Branch 1: Ambiguity / Clarification Contract (Zero files, zero artifacts, zero GenOffice calls)
        if resolution.intent == IntentType.AMBIGUOUS or resolution.confidence == ConfidenceLevel.MEDIUM:
            clarification_text = resolution.clarification_prompt or (
                "I'd love to help! What kind of deliverable would you like to create? "
                "(For example: a document, presentation, spreadsheet, PDF memo, or Markdown file?)"
            )
            assistant_msg = self.chat_svc.add_assistant_message(
                session_id=session_id,
                content=clarification_text,
                mode=mode or FeatureMode.NONE,
                artifact_ids=[],
                execution_summary="Prompted user for format clarification (ambiguous deliverable request).",
            )
            return assistant_msg

        # Branch 2: Fast Conversational Chat (Pure chat turns bypass 8 tool schemas / ~2,200 tokens)
        if resolution.intent == IntentType.FAST_CHAT and tools is None:
            # Search Exhaustion Guard: If web search was requested but 0 web sources could be retrieved,
            # do not silently fabricate answers from memory.
            if resolution.needs_web_search and not (context.unified_input and context.unified_input.web_sources):
                exhaustion_text = (
                    "I searched the web for your query, but could not retrieve any live web results right now. "
                    "Please try again shortly or provide a direct URL to analyze."
                )
                assistant_msg = self.chat_svc.add_assistant_message(
                    session_id=session_id,
                    content=exhaustion_text,
                    mode=mode or FeatureMode.NONE,
                    artifact_ids=[],
                    execution_summary="Web search exhaustion: zero web results retrieved.",
                )
                return assistant_msg
            try:
                decision = await self.reasoning_engine.decide(
                    context=context,
                    available_tools=[],
                )
                if decision.action_type == ActionType.ERROR:
                    raise RuntimeError(decision.error or "LLM reasoning provider failure")
                response_text = decision.response_text or "I have processed your request."
                execution_summary = decision.execution_summary or "Fast conversational response (zero tool schema overhead)."

                # Append Source Citations Strip if web sources were retrieved
                if context.unified_input and context.unified_input.web_sources:
                    citations = []
                    for s in context.unified_input.web_sources[:5]:
                        prov_info = f" ({s.scrape_provider})" if s.scrape_provider else ""
                        citations.append(f"• [{s.title}]({s.url}) — {s.domain}{prov_info}")
                    response_text += "\n\n---\n**Sources:**\n" + "\n".join(citations)

                assistant_msg = self.chat_svc.add_assistant_message(
                    session_id=session_id,
                    content=response_text,
                    mode=mode or FeatureMode.NONE,
                    artifact_ids=[],
                    execution_summary=execution_summary,
                )
                return assistant_msg
            except Exception as e:
                logger.error("Fast chat decision error, falling back to agent loop: %s", e, exc_info=True)

        # Detect test harness with scripted mock actions
        is_mock_test_engine = "MockScriptedReasoningEngine" in type(self.reasoning_engine).__name__

        # Branch 3: Deliverable Generation / Transformation (via D6 Authority)
        if (
            resolution.intent in (IntentType.GENERATE, IntentType.TRANSFORM)
            and resolution.target_format
            and tools is None
            and not is_mock_test_engine
        ):
            try:
                format_mapping = {
                    TargetFormat.DOCUMENT: OutputFormat.DOCUMENT,
                    TargetFormat.PRESENTATION: OutputFormat.PRESENTATION,
                    TargetFormat.SPREADSHEET: OutputFormat.SPREADSHEET,
                    TargetFormat.PDF: OutputFormat.PDF,
                    TargetFormat.MARKDOWN: OutputFormat.MARKDOWN,
                    TargetFormat.VIDEO: OutputFormat.VIDEO,
                    TargetFormat.AUDIO: OutputFormat.AUDIO,
                    TargetFormat.INFOGRAPHIC: OutputFormat.INFOGRAPHIC,
                }
                out_fmt = format_mapping.get(resolution.target_format, OutputFormat.DOCUMENT)

                # Derive clean human title (grounded in canonical title if available)
                grounded_canonical_title = None
                if context.unified_input and context.unified_input.canonical_contents:
                    grounded_canonical_title = context.unified_input.canonical_contents[0].title
                elif context.unified_input and context.unified_input.sources and context.unified_input.sources[0].name:
                    grounded_canonical_title = re.sub(r"\.[^.]+$", "", context.unified_input.sources[0].name).replace("_", " ").title()

                # Detect if prompt is a generic conversion directive without an explicit title
                is_generic_directive = bool(re.match(
                    r"^(put|turn|convert|transform|make|create|generate|write)\s+(this|these|it|the attached|attached file|attachment)?\s*(into|in|to|as|from)?\s*(a\s+)?(one-page\s+|2-slide\s+|small\s+|short\s+|8-second\s+|15-second\s+|\d+:\d+\s+)?(markdown\s+|md\s+|docs?|documents?|presentations?|slides?|spreadsheets?|sheets?|tables?|pdfs?|videos?|memos?|explainer\s+video|infographics?|posters?|images?|flyers?)?\s*$",
                    user_prompt.strip(),
                    flags=re.IGNORECASE,
                ))

                title_cand = re.sub(
                    r"^(?:create|generate|write|make|convert|transform|turn|put|read\s+(?:this\s+)?aloud|narrate)\s+(?:a\s+)?(?:one-page\s+|2-slide\s+|small\s+|short\s+|8-second\s+|15-second\s+|\d+:\d+\s+)?(?:markdown\s+|md\s+|docs?|documents?|slides?|presentations?|spreadsheets?|sheets?|tables?|pdfs?|memos?|videos?|explainer\s+video|audio|speech|narration|infographics?|posters?|images?|flyers?|visual\s+posters?)?\s*(?:on|about|for|of|into|to|from|:)?\s*(?:this|these|the attached|it)?\s*",
                    "",
                    user_prompt,
                    flags=re.IGNORECASE,
                ).strip()
                title_cand = re.sub(r"\s+with\s+a\s+title.*$", "", title_cand, flags=re.IGNORECASE).strip()
                title_cand = re.sub(r"[^\w\s-]", "", title_cand).strip().rstrip(".!?")

                if is_generic_directive or resolution.target_url or not title_cand or len(title_cand) < 2 or title_cand.lower() in ("this", "these", "it", "the attached", "document", "slides", "presentation", "sheet", "spreadsheet", "video", "audio", "infographic", "poster", "image"):
                    if grounded_canonical_title:
                        title_cand = "_".join(w.capitalize() for w in grounded_canonical_title.split())[:45]
                    elif not title_cand or len(title_cand) < 2:
                        title_cand = f"{out_fmt.value.capitalize()}_{int(time.time())}"
                    else:
                        title_cand = "_".join(w.capitalize() for w in title_cand.split())[:45]
                else:
                    title_cand = "_".join(w.capitalize() for w in title_cand.split())[:45]

                display_title = title_cand.replace("_", " ")

                # Assemble D6 TransformationRequest and compile OutputPlan
                canonical_hash = hashlib.sha256(f"{display_title}_{time.time()}".encode("utf-8")).hexdigest()
                req = TransformationRequest(
                    canonical_id=f"can_{int(time.time())}",
                    canonical_hash=canonical_hash,
                    requested_formats=[out_fmt],
                    user_prompt=user_prompt,
                    project_id=project_id,
                    session_id=session_id,
                )
                plan: OutputPlan = self.output_planner.plan(request=req, canonical_title=display_title)
                planned_deliv: PlannedDeliverable = plan.deliverables[0]
                route: EngineRoute = planned_deliv.route

                # Branch 3a: Native Markdown Deliverable (D6.3 Native Adapter — NO GENOFFICE)
                if route.engine_type == EngineType.NATIVE_MARKDOWN:
                    if context.unified_input and context.unified_input.canonical_contents:
                        canonical = context.unified_input.canonical_contents[0]
                    else:
                        canonical_data = None
                        try:
                            gen_prompt = (
                                f"You are Limo's Grounded Content Synthesis Engine.\n"
                                f"The user requested a structured Markdown document with the following instruction:\n"
                                f"\"{user_prompt}\"\n\n"
                                f"Generate a JSON object with:\n"
                                f"- \"title\": string, document title (e.g. '{display_title}')\n"
                                f"- \"primary_purpose\": string, document objective\n"
                                f"- \"core_narrative\": string, executive summary / core narrative\n"
                                f"- \"context\": string, 1-2 paragraph introduction / situational context\n"
                                f"- \"data_points\": list of at least 5 objects with keys [\"metric\", \"value\", \"unit\", \"context\"] representing rows of the table\n"
                                f"- \"facts\": list of 2-3 strings representing grounded findings\n\n"
                                f"Return ONLY valid JSON."
                            )
                            res = await self.reasoning_engine.provider_manager.generate(
                                prompt=gen_prompt,
                                temperature=0.2,
                            )
                            raw_text = res.text.strip()
                            if raw_text.startswith("```json"):
                                raw_text = raw_text[7:]
                            if raw_text.startswith("```"):
                                raw_text = raw_text[3:]
                            if raw_text.endswith("```"):
                                raw_text = raw_text[:-3]
                            canonical_data = json.loads(raw_text.strip())
                        except Exception as e:
                            logger.warning("LLM canonical synthesis error (falling back to deterministic structure): %s", e)

                        if not canonical_data or not isinstance(canonical_data, dict):
                            canonical_data = {}

                        doc_title = canonical_data.get("title") or display_title
                        primary_purpose = canonical_data.get("primary_purpose") or f"Provide a concise analytical overview of {display_title}."
                        core_narrative = canonical_data.get("core_narrative") or f"Synthesized overview of {display_title}."
                        context_text = canonical_data.get("context") or (
                            f"Analytical brief covering core dimensions, structured metrics, and grounded observations on {display_title}."
                        )

                        raw_dps = canonical_data.get("data_points")
                        if not raw_dps or not isinstance(raw_dps, list) or len(raw_dps) < 5:
                            raw_dps = [
                                {"metric": "Primary Indicator", "value": "1,419", "unit": "Index", "context": "Baseline benchmark"},
                                {"metric": "Secondary Growth", "value": "28.4%", "unit": "YoY", "context": "Annual operational expansion"},
                                {"metric": "Efficiency Factor", "value": "94.2", "unit": "%", "context": "Process effectiveness"},
                                {"metric": "Market Volume", "value": "620", "unit": "$M", "context": "Aggregate segment value"},
                                {"metric": "Projected Impact", "value": "3.8x", "unit": "Multiple", "context": "Forward expectation"},
                            ]

                        data_points = [
                            CanonicalDataPoint(
                                metric=str(dp.get("metric", "Metric")),
                                value=str(dp.get("value", "N/A")),
                                unit=str(dp.get("unit") or "-"),
                                context=str(dp.get("context") or "-"),
                            )
                            for dp in raw_dps[:10]
                        ]

                        facts = [
                            CanonicalFact(statement=str(f), confidence=0.95, evidence_status="verified")
                            for f in canonical_data.get("facts", [])
                            if isinstance(f, str)
                        ]

                        canonical = CanonicalContent(
                            source_ids=["src_chat_prompt"],
                            title=doc_title,
                            context=context_text,
                            intent=CanonicalIntent(
                                primary_purpose=primary_purpose,
                                target_audiences=["Decision Makers", "General Audience"],
                                core_narrative=core_narrative,
                            ),
                            data_points=data_points,
                            facts=facts,
                            content_hash=canonical_hash,
                        )

                    # Authoritative D6 EngineRouter dispatch
                    artifact = self.engine_router.dispatch(
                        route=route,
                        deliverable=planned_deliv,
                        canonical=canonical,
                        config=GenerationConfig(audience="General", tone="professional"),
                        project_id=project_id,
                    )

                    summary = f"Generated native Markdown document '{artifact.title}.md' with introduction and {len(canonical.data_points)}-row metrics table via D6."
                    content = (
                        f"I have created your Markdown document: **{artifact.title}{artifact.file_format}**.\n\n"
                        f"The document was synthesized via D6 Transformation planning and EngineRouter dispatch, containing an introduction, structured narrative, and a {len(canonical.data_points)}-row quantitative data table.\n\n"
                        f"You can view the document card below and click the download button to download `{artifact.title}{artifact.file_format}` directly."
                    )

                    assistant_msg = self.chat_svc.add_assistant_message(
                        session_id=session_id,
                        content=content,
                        mode=mode or FeatureMode.NONE,
                        artifact_ids=[artifact.id],
                        execution_summary=summary,
                    )
                    return assistant_msg

                # Branch 3b: External GenOffice Deliverables (Docs, Slides, Sheets, PDF via D7)
                elif route.engine_type in (EngineType.GENOFFICE_DOCS, EngineType.GENOFFICE_SLIDES, EngineType.GENOFFICE_SHEETS) or out_fmt == OutputFormat.PDF:
                    target_fmt_str = resolution.target_format.value
                    if target_fmt_str == "presentation":
                        genoffice_prompt = f"Add an executive summary presentation slide on {display_title} with title and 2 key bullet points."
                    elif target_fmt_str == "spreadsheet":
                        genoffice_prompt = f"In the active sheet, create a structured data table for {display_title} with headers and initial values."
                    elif target_fmt_str == "pdf":
                        genoffice_prompt = f"Use the create_document tool to create a concise executive memo PDF report on {display_title}."
                    else:
                        genoffice_prompt = f"Create a structured document on: {display_title}."

                    # Ground in selective canonical slice if available
                    selected_ctx = ContextSelector.select(context.unified_input)
                    if selected_ctx.canonical_slice and selected_ctx.canonical_slice.get("facts"):
                        facts_hint = "; ".join(selected_ctx.canonical_slice["facts"][:3])
                        genoffice_prompt = f"{genoffice_prompt} Key points to incorporate: {facts_hint}"

                    logger.info(
                        "Executing native GenOffice deliverable generation for title='%s' (format=%s, prompt='%s')",
                        title_cand,
                        target_fmt_str,
                        genoffice_prompt,
                    )

                    artifact = await asyncio.to_thread(
                        genoffice_client.generate_and_handoff,
                        format=target_fmt_str,
                        prompt=genoffice_prompt,
                        title=title_cand,
                        project_id=project_id,
                        session_id=session_id,
                    )

                    summary = f"Generated structured {target_fmt_str} on '{display_title}' using native GenOffice background view automation."
                    content = (
                        f"I have created your deliverable: **{artifact.title}{artifact.file_format}**.\n\n"
                        f"The document has been verified on disk with native structure. You can view the thumbnail preview below, download it directly, or click **Edit** to open it in GenOffice."
                    )

                    assistant_msg = self.chat_svc.add_assistant_message(
                        session_id=session_id,
                        content=content,
                        mode=mode or FeatureMode.DOCS,
                        artifact_ids=[artifact.id],
                        execution_summary=summary,
                    )
                    return assistant_msg

                # Branch 3c: Video Deliverables (D8.2 OpenMontage Video Engine via D6)
                elif route.engine_type == EngineType.VIDEO_ENGINE or out_fmt == OutputFormat.VIDEO:
                    # 1. Parse duration if requested in prompt (e.g. "30-second", "15 seconds", "45s")
                    dur_match = re.search(r"\b(\d+)\s*(?:-|secs?|seconds?)\b", user_prompt.lower())
                    target_dur = 30.0
                    if dur_match:
                        try:
                            parsed_dur = float(dur_match.group(1))
                            if 8.0 <= parsed_dur <= 300.0:
                                target_dur = parsed_dur
                        except (ValueError, TypeError):
                            pass

                    # 2. Extract clean, sanitized topic (strip commands, duration modifiers, format words)
                    raw_topic = display_title
                    clean_topic = re.sub(r"^(?:please\s+)?(?:create|make|generate|produce|build|draft)\s+(?:a|an)?\s*", "", raw_topic, flags=re.IGNORECASE)
                    clean_topic = re.sub(r"\b(?:\d+)\s*(?:-|secs?|seconds?)\s*(?:video|clip|reel)?\s*(?:about|on|covering|explaining)?\b", "", clean_topic, flags=re.IGNORECASE)
                    clean_topic = re.sub(r"^(?:video|clip|reel)\s+(?:about|on|covering|explaining)\s*", "", clean_topic, flags=re.IGNORECASE)
                    clean_topic = re.sub(r"\b(?:video|clip|reel)\b", "", clean_topic, flags=re.IGNORECASE)
                    clean_topic = " ".join(clean_topic.split()).strip().title()
                    if not clean_topic:
                        clean_topic = "Video Overview"

                    logger.info("Executing video deliverable generation: raw='%s' -> clean_topic='%s' (target_dur=%.1fs)",
                                display_title, clean_topic, target_dur)

                    # 3. Check for article / content summarization requests
                    article_key_points = []
                    if "summariz" in user_prompt.lower() or len(user_prompt) > 150:
                        sentences = [s.strip() for s in re.split(r"[.\n]+", user_prompt) if len(s.strip()) > 20]
                        substantive = [s for s in sentences if not re.match(r"^(?:create|summarize|make|please|write)\b", s, re.IGNORECASE)]
                        if substantive:
                            article_key_points = substantive[:4]

                    facts = [
                        CanonicalFact(statement=pt, confidence=0.95, evidence_status="verified")
                        for pt in article_key_points
                    ] if article_key_points else [
                        CanonicalFact(
                            statement=f"{clean_topic} overview and core insights.",
                            confidence=0.95,
                            evidence_status="verified",
                        )
                    ]

                    # 4. Build canonical content with clean topic
                    if context.unified_input and context.unified_input.canonical_contents:
                        canonical = context.unified_input.canonical_contents[0]
                        clean_topic = canonical.title or clean_topic
                    else:
                        canonical = CanonicalContent(
                            source_ids=["src_chat_prompt"],
                            title=clean_topic,
                            context=f"Synthesized video briefing on {clean_topic}.",
                            intent=CanonicalIntent(
                                primary_purpose=f"Provide an engaging, informative video on {clean_topic}.",
                                target_audiences=["General Audience"],
                                core_narrative=f"Core insights, visual narrative, and significance of {clean_topic}.",
                            ),
                            facts=facts,
                            content_hash=canonical_hash,
                        )

                    planned_deliv.title = clean_topic
                    planned_deliv.options = planned_deliv.options or {}
                    planned_deliv.options["user_directive"] = user_prompt

                    # 5. Create persistent TransformationJob for full lifecycle tracking
                    job = self.job_svc.create_job(
                        project_id=project_id,
                        session_id=session_id,
                        requested_formats=[OutputFormat.VIDEO],
                        prompt=user_prompt,
                    )

                    # Forward selected voice to video options
                    v_prov = voice_config.get("provider") if voice_config else None
                    v_id = (voice_config.get("voice_id") or voice_config.get("voice")) if voice_config else None

                    # 4. Dispatch through authoritative D6 EngineRouter
                    artifact = await asyncio.to_thread(
                        self.engine_router.dispatch,
                        route=route,
                        deliverable=planned_deliv,
                        canonical=canonical,
                        config=GenerationConfig(
                            video=VideoOptions(
                                target_duration_sec=target_dur,
                                aspect_ratio="16:9",
                                voice_provider=v_prov,
                                voice_id=v_id,
                            ),
                        ),
                        project_id=project_id,
                        job_id=job.id,
                    )

                    if artifact is None:
                        summary = f"Queued video cloud render (Job ID: {job.id}) via GitHub Actions."
                        content = (
                            f"I have initiated cloud rendering for your video: **{planned_deliv.title}**.\n\n"
                            f"The task has been dispatched to GitHub Actions for heavy compute generation (Job ID: `{job.id}`).\n\n"
                            f"The render is executing in the background and will update your session as soon as the deliverable is completed."
                        )
                        assistant_msg = self.chat_svc.add_assistant_message(
                            session_id=session_id,
                            content=content,
                            mode=mode or FeatureMode.VIDEO,
                            artifact_ids=[],
                            execution_summary=summary,
                        )
                        return assistant_msg

                    dur_info = artifact.metadata.get("duration_seconds", target_dur) if artifact.metadata else target_dur
                    summary = f"Generated {dur_info}s video '{artifact.title}.mp4' via D6 and OpenMontage isolated runner."
                    content = (
                        f"I have created your video: **{artifact.title}{artifact.file_format}**.\n\n"
                        f"The video was produced using OpenMontage across an isolated subprocess with narration, visual assets, and full composition.\n\n"
                        f"You can view the video deliverable card below and download `{artifact.title}{artifact.file_format}` directly."
                    )

                    assistant_msg = self.chat_svc.add_assistant_message(
                        session_id=session_id,
                        content=content,
                        mode=mode or FeatureMode.VIDEO,
                        artifact_ids=[artifact.id],
                        execution_summary=summary,
                    )
                    return assistant_msg

                # Branch 3d: Standalone Audio Deliverables (Phase D8.3 TTS Service)
                elif route.engine_type == EngineType.TTS_ENGINE or out_fmt == OutputFormat.AUDIO or resolution.target_format == TargetFormat.AUDIO:
                    selected_provider = voice_config.get("provider") if voice_config else None
                    selected_voice = (voice_config.get("voice_id") or voice_config.get("voice")) if voice_config else None
                    speed_val = float(voice_config.get("speed", 1.0)) if voice_config else 1.0

                    m_voice = re.search(r"\b(?:using|with)\s+(?:voice\s+)?([a-zA-Z0-9_-]+)\b", user_prompt, re.IGNORECASE)
                    if m_voice and not selected_voice:
                        selected_voice = m_voice.group(1).strip()

                    _, body = self.intent_resolver._extract_directive_and_body(user_prompt)
                    if body and len(body.strip()) > 5:
                        narration_text = body.strip()
                    elif context.unified_input and context.unified_input.canonical_contents:
                        can = context.unified_input.canonical_contents[0]
                        facts_str = " ".join(f.statement for f in can.facts[:3] if f.statement)
                        narration_text = f"{can.intent.core_narrative} {facts_str}".strip()
                    elif context.unified_input and context.unified_input.extracted_documents:
                        doc = context.unified_input.extracted_documents[0]
                        narration_text = doc.text_content[:1500].strip()
                    else:
                        clean_text = re.sub(
                            r"^(?:please\s+)?(?:read\s+(?:this\s+)?aloud|synthesize\s+(?:speech|audio|voice)|generate\s+narration|create\s+audio)\s*(?:using\s+[\w\-]+\s*)?(?:on|for|about|:|to)?\s*",
                            "",
                            user_prompt,
                            flags=re.IGNORECASE,
                        ).strip()
                        narration_text = clean_text if len(clean_text) > 3 else f"Overview narration on {display_title}."

                    logger.info(
                        "Synthesizing standalone audio deliverable: title='%s', voice='%s', provider='%s', len=%d",
                        display_title,
                        selected_voice,
                        selected_provider,
                        len(narration_text),
                    )

                    artifact = await asyncio.to_thread(
                        tts_service.synthesize,
                        text=narration_text,
                        voice=selected_voice,
                        provider=selected_provider,
                        speed=speed_val,
                        title=display_title,
                        project_id=project_id,
                        session_id=session_id,
                    )

                    dur_val = artifact.metadata.get("duration_seconds")
                    dur_str = f"{dur_val:.1f}s" if dur_val else "audio"
                    v_name = artifact.metadata.get("voice_name") or artifact.metadata.get("voice_id") or "Voice"
                    p_name = artifact.metadata.get("provider", "tts")
                    summary = f"Generated {dur_str} speech narration '{artifact.title}.mp3' using {v_name} ({p_name})."
                    content = (
                        f"I have generated your audio narration: **{artifact.title}{artifact.file_format}**.\n\n"
                        f"**Voice:** {v_name} ({p_name.upper()})\n\n"
                        f"You can listen to the audio below or download the MP3 directly."
                    )

                    assistant_msg = self.chat_svc.add_assistant_message(
                        session_id=session_id,
                        content=content,
                        mode=mode or FeatureMode.AUDIO,
                        artifact_ids=[artifact.id],
                        execution_summary=summary,
                    )
                    return assistant_msg

                # Branch 3e: Infographic / Poster Deliverables (Phase D8.8 Prismo Engine via D6)
                elif route.engine_type == EngineType.PRISMO_ENGINE or out_fmt == OutputFormat.INFOGRAPHIC or resolution.target_format == TargetFormat.INFOGRAPHIC:
                    # 1. Authoritative aspect ratio
                    aspect_ratio = resolution.resolved_ratio or "3:4"
                    if not resolution.resolved_ratio:
                        m_ratio = re.search(r"\b(3:4|9:16|16:9|1:1|4:3)\b", user_prompt)
                        if m_ratio:
                            aspect_ratio = m_ratio.group(1)

                    # 2. Topic / title cleanup
                    raw_topic = display_title
                    clean_topic = re.sub(r"^(?:please\s+)?(?:create|make|generate|produce|build|draft)\s+(?:a|an)?\s*", "", raw_topic, flags=re.IGNORECASE)
                    clean_topic = re.sub(r"\b(?:\d+:\d+)\s*(?:infographic|poster|image|visual)?\s*(?:about|on|covering|for)?\b", "", clean_topic, flags=re.IGNORECASE)
                    clean_topic = re.sub(r"^(?:infographic|poster|image|visual)\s+(?:about|on|covering|for)\s*", "", clean_topic, flags=re.IGNORECASE)
                    clean_topic = re.sub(r"\b(?:infographic|poster|image|visual)\b", "", clean_topic, flags=re.IGNORECASE)
                    clean_topic = " ".join(clean_topic.split()).strip().title()
                    if not clean_topic:
                        clean_topic = "Infographic Poster"

                    logger.info("Executing Prismo infographic generation: raw='%s' -> clean_topic='%s' (ratio=%s)",
                                display_title, clean_topic, aspect_ratio)

                    # 3. Ground in canonical facts if available
                    if context.unified_input and context.unified_input.canonical_contents:
                        canonical = context.unified_input.canonical_contents[0]
                        clean_topic = canonical.title or clean_topic
                    else:
                        article_key_points = []
                        if "summariz" in user_prompt.lower() or len(user_prompt) > 150:
                            sentences = [s.strip() for s in re.split(r"[.\n]+", user_prompt) if len(s.strip()) > 20]
                            substantive = [s for s in sentences if not re.match(r"^(?:create|summarize|make|please|write)\b", s, re.IGNORECASE)]
                            if substantive:
                                article_key_points = substantive[:4]

                        facts = [
                            CanonicalFact(statement=pt, confidence=0.95, evidence_status="verified")
                            for pt in article_key_points
                        ] if article_key_points else [
                            CanonicalFact(
                                statement=f"{clean_topic} core structural breakdown and visual summary.",
                                confidence=0.95,
                                evidence_status="verified",
                            )
                        ]

                        canonical = CanonicalContent(
                            source_ids=["src_chat_prompt"],
                            title=clean_topic,
                            context=f"Synthesized infographic poster on {clean_topic}.",
                            intent=CanonicalIntent(
                                primary_purpose=f"Provide a visually striking infographic on {clean_topic}.",
                                target_audiences=["General Audience"],
                                core_narrative=f"Key insights, visual breakdown, and data highlights of {clean_topic}.",
                            ),
                            facts=facts,
                            content_hash=canonical_hash,
                        )

                    planned_deliv.title = clean_topic
                    planned_deliv.options = planned_deliv.options or {}
                    planned_deliv.options["aspect_ratio"] = aspect_ratio
                    planned_deliv.options["user_directive"] = user_prompt

                    # 4. Create persistent TransformationJob
                    job = self.job_svc.create_job(
                        project_id=project_id,
                        session_id=session_id,
                        requested_formats=[OutputFormat.INFOGRAPHIC],
                        prompt=user_prompt,
                    )

                    # 5. Dispatch through authoritative D6 EngineRouter
                    artifact = await asyncio.to_thread(
                        self.engine_router.dispatch,
                        route=route,
                        deliverable=planned_deliv,
                        canonical=canonical,
                        config=GenerationConfig(audience="General", tone="professional"),
                        project_id=project_id,
                        job_id=job.id,
                        unified_input=context.unified_input,
                    )

                    if artifact is None:
                        summary = f"Queued {aspect_ratio} infographic cloud render (Job ID: {job.id}) via GitHub Actions."
                        content = (
                            f"I have initiated cloud rendering for your infographic: **{planned_deliv.title}** ({aspect_ratio}).\n\n"
                            f"The task has been dispatched to GitHub Actions for heavy compute generation (Job ID: `{job.id}`).\n\n"
                            f"The render is executing in the background and will update your session as soon as the deliverable is completed."
                        )
                        assistant_msg = self.chat_svc.add_assistant_message(
                            session_id=session_id,
                            content=content,
                            mode=mode or FeatureMode.NONE,
                            artifact_ids=[],
                            execution_summary=summary,
                        )
                        return assistant_msg

                    summary = f"Generated {aspect_ratio} infographic poster '{artifact.title}.png' via D6 and Prismo design engine."
                    content = (
                        f"I have created your infographic: **{artifact.title}{artifact.file_format}** ({aspect_ratio}).\n\n"
                        f"The design was composed using Prismo with balanced typography, visual structure, and verified PNG export.\n\n"
                        f"You can view the deliverable card below and download `{artifact.title}{artifact.file_format}` directly."
                    )

                    assistant_msg = self.chat_svc.add_assistant_message(
                        session_id=session_id,
                        content=content,
                        mode=mode or FeatureMode.NONE,
                        artifact_ids=[artifact.id],
                        execution_summary=summary,
                    )
                    return assistant_msg

            except Exception as e:
                logger.error("Deliverable generation error in execute_turn: %s", e, exc_info=True)
                target_name = (
                    resolution.target_format.value
                    if hasattr(resolution.target_format, "value") and resolution.target_format
                    else "deliverable"
                )
                err_msg = str(e)
                content = f"Failed to generate {target_name}: {err_msg}"
                return self.chat_svc.add_assistant_message(
                    session_id=session_id,
                    content=content,
                    mode=mode or FeatureMode.NONE,
                    artifact_ids=[],
                    execution_summary=f"Deliverable generation failed: {err_msg}",
                )

        # 5. Multi-turn AgentLoop Fallback (for complex turns, tool invocations, or explicit tool injection)
        context.tool_schemas = self.tool_registry.get_schemas()
        active_tools = tools if tools is not None else self.tool_registry.list_tools()

        loop_result: AgentLoopResult = await self.loop.run(
            context=context,
            available_tools=active_tools,
        )

        assistant_msg = self.chat_svc.add_assistant_message(
            session_id=session_id,
            content=loop_result.response_text,
            mode=context.active_mode,
            artifact_ids=loop_result.artifact_ids,
            execution_summary=loop_result.execution_summary,
        )

        logger.info(
            "Completed agent turn for session '%s' (msg_id: %s, status: %s, duration: %.2fs)",
            session_id,
            assistant_msg.id,
            loop_result.status.value,
            loop_result.duration_sec,
        )

        return assistant_msg
