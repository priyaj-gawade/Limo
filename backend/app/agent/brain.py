"""Decoupled reasoning engine interfaces and production LLM integration adapter.

Maintains strict separation between:
- Production reasoning engine (real LLM function-calling)
- Isolated test engines (strictly for deterministic unit test fixtures)
"""

from abc import ABC, abstractmethod
import logging
from typing import Any, Dict, List, Optional

from .actions import ActionType, AgentAction, ToolCallPayload
from .context import AgentContext, ContextSelector, SelectedContext
from .contracts import BaseTool
from .llm.manager import LLMProviderManager, llm_provider_manager

logger = logging.getLogger("limo.agent.brain")


class ReasoningEngine(ABC):
    """Abstract interface for agent decision making and action selection."""

    @abstractmethod
    async def decide(self, context: AgentContext, available_tools: List[BaseTool]) -> AgentAction:
        """Analyze the current conversational context and scratchpad to select the next action.
        
        Returns:
            AgentAction indicating a TOOL_CALL, FINAL_RESPONSE, or ERROR.
        """
        pass


class LLMReasoningEngine(ReasoningEngine):
    """Production reasoning engine utilizing real LLM provider function calling.
    
    Delegates to centralized LLMProviderManager for multi-credential rotation,
    quota protection, and resilience. Never uses hardcoded or rule-based responses.
    """

    def __init__(
        self,
        provider_manager: Optional[LLMProviderManager] = None,
        temperature: float = 0.2,
    ):
        self.provider_manager = provider_manager or llm_provider_manager
        self.temperature = temperature

    def _build_system_instruction(self, context: AgentContext) -> str:
        """Combine core identity guidelines with active domain skill instructions."""
        guidelines = (
            "You are Limo, an intelligent AI workspace agent for conversational ideation and deliverables. "
            "Respond helpfully and concisely. Use available tools when requested information is needed. "
            "When creating or registering sources/projects, ensure parameters are valid."
        )
        if context.skill_instructions:
            return f"{guidelines}\n\n## Active Skill Instructions:\n{context.skill_instructions}"
        return guidelines

    def _build_prompt(
        self,
        context: AgentContext,
        selected_context: Optional[SelectedContext] = None,
    ) -> str:
        """Format conversational history, scratchpad observations, and user request into a single prompt."""
        parts = []

        # Chronological conversation turns
        if context.messages:
            parts.append("### Conversation History:")
            for msg in context.messages[-6:]:  # Keep bounded context
                role_label = "User" if msg.role.value == "user" else "Assistant"
                parts.append(f"{role_label}: {msg.content}")

        # In-memory scratchpad observations
        if context.observations:
            parts.append("\n### Previous Tool Observations in Current Turn:")
            for obs in context.observations:
                status = "SUCCESS" if obs.result.success else "FAILED"
                parts.append(f"Tool [{obs.tool_name}] -> {status}: {obs.result.output}")

        # Selected attached inputs, web sources, or source excerpts
        if selected_context and selected_context.prompt_context_snippet:
            parts.append(f"\n{selected_context.prompt_context_snippet}")
        elif getattr(context, "prompt_context_snippet", None):
            parts.append(f"\n{context.prompt_context_snippet}")
        elif context.source_excerpts:
            parts.append("\n### Relevant Source Context:")
            for exc in context.source_excerpts[:3]:
                parts.append(f"- Source [{exc.name}]: {exc.snippet}")

        # Current user request
        parts.append(f"\nUser: {context.user_request}")
        return "\n".join(parts)

    def _build_tools_declarations(self, available_tools: List[BaseTool]) -> List[Dict[str, Any]]:
        """Format registered Limo tools into provider function declarations."""
        declarations = []
        for tool in available_tools:
            declarations.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters_schema,
            })
        return declarations

    async def decide(self, context: AgentContext, available_tools: List[BaseTool]) -> AgentAction:
        """Invoke LLMProviderManager with formatted prompt and registered tool declarations."""
        system_instruction = self._build_system_instruction(context)
        selected = ContextSelector.select(context.unified_input)
        prompt = self._build_prompt(context, selected_context=selected)
        tools_declarations = self._build_tools_declarations(available_tools) if available_tools else None
        media_parts = selected.media_parts if selected.media_parts else None

        try:
            response = await self.provider_manager.generate(
                prompt=prompt,
                system_instruction=system_instruction,
                tools_declarations=tools_declarations,
                temperature=self.temperature,
                media_parts=media_parts,
            )

            # Check for function calls
            if response.function_calls:
                import uuid
                tool_calls = [
                    ToolCallPayload(
                        tool_name=fc.name,
                        arguments=fc.args,
                        call_id=fc.id or f"call_{uuid.uuid4().hex[:8]}",
                    )
                    for fc in response.function_calls
                ]
                return AgentAction(
                    action_type=ActionType.TOOL_CALL,
                    tool_calls=tool_calls,
                )

            # Text final response
            summary = f"Generated by {response.route_key} (tokens: {response.total_tokens}, latency: {response.latency_sec:.2f}s)"
            return AgentAction.final_response(
                text=response.text or "I did not receive a response from the reasoning model.",
                summary=summary,
            )

        except Exception as e:
            logger.error("LLM reasoning failed: %s", str(e), exc_info=True)
            return AgentAction.fail(f"LLM reasoning provider failure: {str(e)}")

