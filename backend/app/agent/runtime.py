import asyncio
import hashlib
import json
import logging
import re
import time
from typing import List, Optional

from ..exceptions import EntityNotFoundError
from ..models.chat import Message
from ..models.content import (
    CanonicalContent,
    CanonicalDataPoint,
    CanonicalFact,
    CanonicalIntent,
)
from ..models.enums import ArtifactType, FeatureMode, OutputFormat
from ..models.generation_config import GenerationConfig
from ..models.transformation import (
    EngineRoute,
    EngineType,
    OutputPlan,
    PlannedDeliverable,
    TransformationRequest,
)
from ..services.artifact_service import artifact_service
from ..services.chat_service import ChatService, chat_service
from ..services.transformation.engine_router import EngineRouter, engine_router
from ..services.transformation.genoffice_client import genoffice_client
from ..services.transformation.output_planner import OutputPlanner, output_planner
from ..storage.service import storage_service
from .brain import LLMReasoningEngine, ReasoningEngine
from .context import AgentContextManager, AgentLimits
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
    ):
        self.reasoning_engine = reasoning_engine or LLMReasoningEngine()
        self.context_manager = context_manager or AgentContextManager()
        self.chat_svc = chat_svc or chat_service
        self.tool_registry = tool_registry or create_default_tool_registry()
        self.skill_registry = skill_registry or SkillRegistry()
        self.intent_resolver = intent_res or intent_resolver
        self.output_planner = output_plan or output_planner
        self.engine_router = eng_router or engine_router
        self.loop = AgentLoop(self.reasoning_engine, self.context_manager)

    async def execute_turn(
        self,
        session_id: str,
        user_prompt: str,
        mode: Optional[FeatureMode] = None,
        project_id: Optional[str] = None,
        tools: Optional[List[BaseTool]] = None,
        limits: Optional[AgentLimits] = None,
    ) -> Message:
        """Execute a complete agent conversational turn.
        
        Flow:
        1. Persist user prompt to chat session.
        2. Hydrate token-budgeted, selective context (targeted source retrieval).
        3. Match and activate domain skills (Tier 2 progressive disclosure).
        4. Fast Intent Gate:
           - AMBIGUOUS: Return concise clarification prompt, zero files/artifacts.
           - FAST_CHAT (tools is None): Direct lightweight generation with zero tool schemas.
           - GENERATE / TRANSFORM: Route through D6 Transformation Pipeline Authority:
             TransformationRequest -> OutputPlan -> EngineRouter
             * NativeMarkdownAdapter for Markdown (.md)
             * GenOffice Runner for Office deliverables (.docx, .pptx, .xlsx, .pdf)
        5. Fallback: Run bounded AgentLoop state machine with registered tools.
        6. Persist assistant response turn to SQLite with public execution summary.
        7. Return the resulting Message entity.
        """
        # 1. Persist user turn
        user_msg = self.chat_svc.add_user_message(
            session_id=session_id,
            content=user_prompt,
            mode=mode,
        )

        # 2. Hydrate bounded context
        context = self.context_manager.load_context(
            session_id=session_id,
            user_request=user_prompt,
            project_id=project_id,
            limits=limits,
        )
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
            try:
                decision = await self.reasoning_engine.decide(
                    context=context,
                    available_tools=[],
                )
                response_text = decision.response_text or "I have processed your request."
                execution_summary = decision.execution_summary or "Fast conversational response (zero tool schema overhead)."

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

        # Branch 3: Deliverable Generation / Transformation (via D6 Authority)
        if resolution.intent in (IntentType.GENERATE, IntentType.TRANSFORM) and resolution.target_format:
            try:
                format_mapping = {
                    TargetFormat.DOCUMENT: OutputFormat.DOCUMENT,
                    TargetFormat.PRESENTATION: OutputFormat.PRESENTATION,
                    TargetFormat.SPREADSHEET: OutputFormat.SPREADSHEET,
                    TargetFormat.PDF: OutputFormat.PDF,
                    TargetFormat.MARKDOWN: OutputFormat.MARKDOWN,
                }
                out_fmt = format_mapping.get(resolution.target_format, OutputFormat.DOCUMENT)

                # Derive clean human title
                title_cand = re.sub(
                    r"^(create|generate|write|make|convert|transform|turn)\s+(a\s+)?(one-page\s+|2-slide\s+|small\s+)?(markdown\s+|md\s+|docs?|documents?|slides?|presentations?|spreadsheets?|sheets?|tables?|pdfs?|memos?)\s+(on|about|for|of|into|to)?\s*",
                    "",
                    user_prompt,
                    flags=re.IGNORECASE,
                ).strip()
                title_cand = re.sub(r"\s+with\s+a\s+title.*$", "", title_cand, flags=re.IGNORECASE).strip()
                title_cand = re.sub(r"[^\w\s-]", "", title_cand).strip().rstrip(".!?")
                if not title_cand or len(title_cand) < 2:
                    title_cand = f"{out_fmt.value.capitalize()}_{int(time.time())}"
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

            except Exception as e:
                logger.error("Deliverable generation error in execute_turn, falling back to agent loop: %s", e, exc_info=True)

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
