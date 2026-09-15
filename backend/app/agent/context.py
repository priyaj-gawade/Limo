"""Selective, token-budgeted context manager and targeted source retrieval for Limo Agent."""

from datetime import datetime, timezone
import re
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ..config import settings
from ..core.ids import generate_id
from ..db.connection import get_connection
from ..db.repositories.chat_repo import ChatRepository
from ..db.repositories.source_repo import SourceRepository
from ..exceptions import EntityNotFoundError
from ..models.chat import Message, MessageAttachment
from ..models.content import CanonicalContent
from ..models.enums import FeatureMode, MessageRole
from ..models.project import Source
from ..services.extraction.models import ExtractedDocument
from .contracts import ToolResult


class AgentLimits(BaseModel):
    """Multi-dimensional safety and operational limits for an agent execution."""
    max_turns: int = Field(default=10, ge=1, le=100, description="Maximum reasoning and decision turns")
    max_tool_calls: int = Field(default=20, ge=1, le=200, description="Maximum cumulative tool executions")
    max_execution_time_sec: float = Field(default=60.0, ge=0.001, le=3600.0, description="Maximum wall-clock execution time")
    max_context_tokens: int = Field(default=16000, ge=10, le=512000, description="Maximum token allocation for context window")


class SourceExcerpt(BaseModel):
    """Lightweight, targeted excerpt from an ingested source to prevent context saturation."""
    source_id: str = Field(description="Unique source identifier")
    name: str = Field(description="Display filename or asset title")
    snippet: str = Field(description="Extracted relevant text excerpt")
    total_chars: int = Field(description="Total characters in the complete source")
    relevance_score: float = Field(default=0.0, description="Heuristic relevance score against prompt")


class Observation(BaseModel):
    """Record of a tool execution observation in the turn scratchpad."""
    tool_name: str = Field(description="Name of executed tool")
    call_id: str = Field(description="Correlating tool call ID")
    result: ToolResult = Field(description="Structured execution result")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MediaReference(BaseModel):
    """Preserved pointer to a native media file on disk."""
    source_id: str = Field(description="Associated source ID")
    media_type: str = Field(description="Media type: image, audio, or video")
    mime_type: str = Field(description="MIME content type")
    file_path: Optional[str] = Field(default=None, description="Absolute file path on disk")
    name: Optional[str] = Field(default=None, description="Original filename")


class UnifiedInputContext(BaseModel):
    """Unified cross-format input representation preserving structured context and native media."""
    user_instruction: str = Field(description="User prompt/instruction for this turn")
    source_ids: List[str] = Field(default_factory=list, description="IDs of linked/attached sources")
    attachments: List[MessageAttachment] = Field(default_factory=list, description="Message attachment references")
    sources: List[Source] = Field(default_factory=list, description="Resolved Source records")
    extracted_documents: List[ExtractedDocument] = Field(default_factory=list, description="D5 extracted documents")
    canonical_contents: List[CanonicalContent] = Field(default_factory=list, description="D5 canonical content objects")
    media_references: List[MediaReference] = Field(default_factory=list, description="Preserved native media references")
    resolved_intent: Optional[Dict[str, Any]] = Field(default=None, description="Intent gate resolution")


class SelectedContext(BaseModel):
    """Token-budgeted context projection selected for LLM or downstream engine."""
    prompt_context_snippet: str = Field(default="", description="Token-budgeted text to inject into prompt")
    media_parts: List[Dict[str, Any]] = Field(default_factory=list, description="Native media parts (e.g. image parts) for multimodal inference")
    canonical_slice: Optional[Dict[str, Any]] = Field(default=None, description="Targeted slice of canonical content for deliverable generation")


class ContextSelector:
    """Projects task-specific, token-budgeted context from UnifiedInputContext."""

    @staticmethod
    def select(
        unified_input: Optional[UnifiedInputContext],
        intent_type: Optional[str] = None,
        max_text_chars: int = 1500,
        max_facts: int = 5,
    ) -> SelectedContext:
        if not unified_input:
            return SelectedContext()

        selected = SelectedContext()
        prompt_lines = []

        # 1. Native Media Selection: Images for visual perception
        for media in unified_input.media_references:
            if media.media_type == "image" and media.file_path:
                selected.media_parts.append({
                    "type": "image",
                    "file_path": media.file_path,
                    "mime_type": media.mime_type,
                    "name": media.name or "image",
                })

        # 2. Structured Context Selection: Budgeted text & canonical facts
        if unified_input.sources or unified_input.extracted_documents:
            prompt_lines.append("### Attached Inputs:")

            for src in unified_input.sources:
                matching_doc = next((d for d in unified_input.extracted_documents if d.source_id == src.id), None)
                text_content = ""
                if matching_doc and matching_doc.raw_text:
                    text_content = matching_doc.raw_text.strip()
                elif src.extracted_text:
                    text_content = src.extracted_text.strip()

                if text_content:
                    if len(text_content) > max_text_chars:
                        excerpt = text_content[:max_text_chars].rsplit(" ", 1)[0] + "... [truncated]"
                    else:
                        excerpt = text_content
                    prompt_lines.append(f"- Input [{src.name}] (Type: {src.mime_type}):\n{excerpt}")
                else:
                    prompt_lines.append(f"- Input [{src.name}] (Type: {src.mime_type}, Size: {src.size_bytes} bytes)")

        # 3. Canonical Facts Selection
        if unified_input.canonical_contents:
            facts_collected = []
            for can in unified_input.canonical_contents:
                for f in can.facts[:max_facts]:
                    if f.statement:
                        facts_collected.append(f.statement)

            if facts_collected:
                prompt_lines.append("\nKey Grounded Facts:")
                for fact in facts_collected[:max_facts]:
                    prompt_lines.append(f"• {fact}")

            # Prepare canonical slice for deliverables
            primary_can = unified_input.canonical_contents[0]
            selected.canonical_slice = {
                "title": primary_can.title,
                "context": primary_can.context,
                "core_narrative": primary_can.intent.core_narrative if primary_can.intent else "",
                "facts": facts_collected[:max_facts],
                "data_points": [
                    {"metric": dp.metric, "value": dp.value, "unit": dp.unit or ""}
                    for dp in primary_can.data_points[:8]
                ],
            }

        selected.prompt_context_snippet = "\n".join(prompt_lines).strip()
        return selected


class AgentContext(BaseModel):
    """Active conversational and execution context for a single agent turn."""
    session_id: str = Field(description="Chat session ID")
    project_id: Optional[str] = Field(default=None, description="Active project ID")
    user_request: Optional[str] = Field(default=None, description="Active user prompt for current turn")
    active_mode: FeatureMode = Field(default=FeatureMode.NONE, description="Active creation mode")
    messages: List[Message] = Field(default_factory=list, description="Chronological conversation turns")
    source_excerpts: List[SourceExcerpt] = Field(default_factory=list, description="Targeted excerpts of relevant sources")
    active_artifacts: List[str] = Field(default_factory=list, description="Artifact IDs referenced or created")
    active_skills: List[str] = Field(default_factory=list, description="Names of activated skills")
    skill_instructions: str = Field(default="", description="Tier 2 instructions for activated skills")
    tool_schemas: List[Dict[str, Any]] = Field(default_factory=list, description="Available tool schemas")
    observations: List[Observation] = Field(default_factory=list, description="In-memory scratchpad observations")
    limits: AgentLimits = Field(default_factory=AgentLimits, description="Safety guardrails")
    current_turn: int = Field(default=0, description="Current turn count in the execution loop")
    total_tool_calls: int = Field(default=0, description="Total tool invocations performed in this cycle")
    start_time: float = Field(default_factory=time.time, description="Monotonic start timestamp")
    retrieval_budget_tokens: int = Field(default_factory=lambda: getattr(settings, "default_retrieval_token_budget", 2000), description="Context retrieval token budget")
    unified_input: Optional[UnifiedInputContext] = Field(default=None, description="Preserved unified input context for current turn")

    def is_timed_out(self) -> bool:
        """Check if execution time has breached max_execution_time_sec."""
        return (time.time() - self.start_time) > self.limits.max_execution_time_sec

    def is_tool_limit_reached(self) -> bool:
        """Check if total tool calls have reached or exceeded max_tool_calls."""
        return self.total_tool_calls >= self.limits.max_tool_calls

    def is_turn_limit_reached(self) -> bool:
        """Check if turn count has reached or exceeded max_turns."""
        return self.current_turn >= self.limits.max_turns


def estimate_tokens(text: str) -> int:
    """Estimate token count using a fast 4-character-per-token heuristic (D4.2 standard)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


class AgentContextManager:
    """Manages progressive hydration, targeted source retrieval, and token budgeting."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(settings.db_path)

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count using a fast 4-character-per-token heuristic."""
        return estimate_tokens(text)

    def retrieve_relevant_sources(
        self,
        prompt: str,
        project_id: Optional[str],
        max_sources: int = 3,
        max_chars_per_source: int = 1500,
        token_budget_chars: Optional[int] = None,
    ) -> List[SourceExcerpt]:
        """Identify and retrieve only relevant source snippets based on prompt keywords.
        
        Enforces the rule: NEVER reload the entire project or dump complete multi-megabyte files.
        """
        if not project_id or not prompt:
            return []

        # Extract search terms from prompt (words >= 3 letters, lowercased)
        tokens = [t.lower() for t in re.findall(r"\w{3,}", prompt)]
        unique_tokens = set(tokens)

        with get_connection(self.db_path) as conn:
            all_sources = SourceRepository.list_sources_by_project(conn, project_id)

        if not all_sources:
            return []

        scored_sources = []
        for src in all_sources:
            text = src.extracted_text or ""
            name = src.name.lower()
            text_lower = text.lower()

            # Compute relevance score based on keyword hits in title and content
            score = 0.0
            for token in unique_tokens:
                if token in name:
                    score += 5.0  # Title match is heavily weighted
                count = text_lower.count(token)
                if count > 0:
                    score += min(count, 5) * 1.0

            scored_sources.append((score, src, text))

        # Sort by relevance descending, filter to top sources
        scored_sources.sort(key=lambda item: item[0], reverse=True)
        top_candidates = [item for item in scored_sources[:max_sources] if item[0] > 0 or len(scored_sources) <= 2]

        excerpts = []
        total_chars_allocated = 0
        max_total_budget = token_budget_chars or (max_sources * max_chars_per_source)

        for score, src, full_text in top_candidates:
            if total_chars_allocated >= max_total_budget:
                break

            remaining_budget = max_total_budget - total_chars_allocated
            allowed_chars = min(max_chars_per_source, remaining_budget)

            if not full_text:
                snippet = f"[{src.name}: No extracted text available. Size: {src.size_bytes} bytes]"
            elif len(full_text) <= allowed_chars:
                snippet = full_text
            else:
                # Find best matching window or take prefix
                snippet = full_text[:allowed_chars] + "... [truncated]"

            total_chars_allocated += len(snippet)
            excerpts.append(
                SourceExcerpt(
                    source_id=src.id,
                    name=src.name,
                    snippet=snippet,
                    total_chars=len(full_text),
                    relevance_score=score,
                )
            )

        return excerpts

    def load_context(
        self,
        session_id: str,
        user_request: str,
        project_id: Optional[str] = None,
        limits: Optional[AgentLimits] = None,
        turn_source_ids: Optional[List[str]] = None,
    ) -> AgentContext:
        """Hydrate bounded execution context for an active session turn."""
        effective_limits = limits or AgentLimits()

        with get_connection(self.db_path) as conn:
            session = ChatRepository.get_session(conn, session_id)
            if not session:
                raise EntityNotFoundError("ChatSession", session_id)

            # Resolve project ID from session if not explicitly provided
            resolved_project_id = project_id or session.project_id
            history = ChatRepository.get_messages(conn, session_id)

        # Retrieve targeted source excerpts using keyword matching
        source_excerpts = self.retrieve_relevant_sources(
            prompt=user_request,
            project_id=resolved_project_id,
            max_sources=3,
            max_chars_per_source=1500,
            token_budget_chars=4000,
        )

        # Ensure any explicit turn sources are included in source_excerpts
        if turn_source_ids:
            with get_connection(self.db_path) as conn:
                for sid in turn_source_ids:
                    if not any(ex.source_id == sid for ex in source_excerpts):
                        src = SourceRepository.get_source(conn, sid)
                        if src:
                            txt = src.extracted_text or ""
                            snippet = txt[:1500] if txt else f"[{src.name}: Registered {src.source_type.value}]"
                            source_excerpts.append(
                                SourceExcerpt(
                                    source_id=src.id,
                                    name=src.name,
                                    snippet=snippet,
                                    total_chars=len(txt),
                                    relevance_score=10.0,
                                )
                            )

        # Collect any referenced artifacts across recent turns
        recent_artifacts = []
        for msg in history[-5:]:
            recent_artifacts.extend(msg.artifact_ids)

        context = AgentContext(
            session_id=session_id,
            project_id=resolved_project_id,
            user_request=user_request,
            active_mode=session.mode,
            messages=history,
            source_excerpts=source_excerpts,
            active_artifacts=list(dict.fromkeys(recent_artifacts)),
            limits=effective_limits,
            start_time=time.time(),
        )

        return self.prune_or_truncate(context)

    def prune_or_truncate(self, context: AgentContext) -> AgentContext:
        """Sliding-window compaction to ensure context stays within token budget."""
        budget = context.limits.max_context_tokens

        # Estimate total tokens
        total_tokens = sum(self.estimate_tokens(m.content) for m in context.messages)
        total_tokens += sum(self.estimate_tokens(s.snippet) for s in context.source_excerpts)
        total_tokens += sum(self.estimate_tokens(str(o.result.output)) for o in context.observations)

        if total_tokens <= budget or len(context.messages) <= 3:
            return context

        # Prune oldest middle messages, preserving the first prompt and latest 2 turns
        pruned_messages = [context.messages[0]]
        recent_tail = context.messages[-3:]

        middle_tokens_allowed = budget // 2
        middle_bucket = []
        middle_tokens = 0

        for msg in reversed(context.messages[1:-3]):
            tokens = self.estimate_tokens(msg.content)
            if middle_tokens + tokens <= middle_tokens_allowed:
                middle_bucket.append(msg)
                middle_tokens += tokens
            else:
                break

        middle_bucket.reverse()
        pruned_messages.extend(middle_bucket)
        pruned_messages.extend(recent_tail)

        context.messages = pruned_messages
        return context

    @staticmethod
    def record_observation(
        context: AgentContext,
        tool_name: str,
        call_id: str,
        result: ToolResult,
    ) -> Observation:
        """Record an executed tool observation into the turn scratchpad."""
        obs = Observation(
            tool_name=tool_name,
            call_id=call_id,
            result=result,
            timestamp=datetime.now(timezone.utc),
        )
        context.observations.append(obs)
        context.total_tool_calls += 1
        return obs
