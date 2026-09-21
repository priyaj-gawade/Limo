"""Bounded multi-turn execution loop with multi-dimensional safety guards."""

import logging
import time
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from .actions import ActionType, AgentAction
from .brain import ReasoningEngine
from .context import AgentContext, AgentContextManager
from .contracts import AgentEventType, AgentState, BaseTool, HookEvent, ToolResult
from .hooks import HookRegistry
from .permissions import PermissionManager
from .subagents import SubagentCoordinator

logger = logging.getLogger("limo.agent.loop")


class AgentLoopResult(BaseModel):
    """Outcome of an agent loop execution cycle."""
    status: AgentState = Field(description="Final terminal state of the agent loop")
    response_text: str = Field(description="Final public response text delivered to user")
    artifact_ids: List[str] = Field(default_factory=list, description="Referenced deliverable artifacts")
    execution_summary: Optional[str] = Field(default=None, description="Public high-level summary of steps taken")
    turns_used: int = Field(default=0, description="Total reasoning turns consumed")
    tool_calls_used: int = Field(default=0, description="Total tool invocations performed")
    duration_sec: float = Field(default=0.0, description="Total execution duration in seconds")
    error: Optional[str] = Field(default=None, description="Error message if state is FAILED")
    approval_id: Optional[str] = Field(default=None, description="Pending approval ID if state is WAITING_APPROVAL")


class AgentLoop:
    """Bounded, sequential multi-turn state machine managing agent reasoning and tool dispatch."""

    def __init__(
        self,
        reasoning_engine: ReasoningEngine,
        context_manager: Optional[AgentContextManager] = None,
        hook_registry: Optional[HookRegistry] = None,
        permission_manager: Optional[PermissionManager] = None,
        subagent_coordinator: Optional[SubagentCoordinator] = None,
    ):
        self.reasoning_engine = reasoning_engine
        self.context_manager = context_manager or AgentContextManager()
        self.hook_registry = hook_registry or HookRegistry()
        self.permission_manager = permission_manager or PermissionManager()
        self.subagent_coordinator = subagent_coordinator or SubagentCoordinator()

    async def run(
        self,
        context: AgentContext,
        available_tools: Optional[List[BaseTool]] = None,
    ) -> AgentLoopResult:
        """Execute the multi-turn agent loop until terminal answer, failure, or limit exhaustion."""
        tools = available_tools or []
        tools_by_name: Dict[str, BaseTool] = {t.name: t for t in tools}

        context.start_time = time.time()
        context.current_turn = 0
        state = AgentState.PLANNING

        logger.info(
            "Starting agent loop for session '%s' (max_turns=%d, max_tools=%d, timeout=%.1fs)",
            context.session_id,
            context.limits.max_turns,
            context.limits.max_tool_calls,
            context.limits.max_execution_time_sec,
        )

        while True:
            # 1. Check multi-dimensional safety limits
            if context.is_timed_out():
                logger.warning("Agent execution exceeded time limit of %.1fs", context.limits.max_execution_time_sec)
                return self._build_timeout_result(context, "Execution timed out: wall-clock limit exceeded")

            if context.is_turn_limit_reached():
                logger.warning("Agent execution reached max turn limit of %d", context.limits.max_turns)
                return self._build_limit_result(context, f"Maximum reasoning turns ({context.limits.max_turns}) exceeded")

            if context.is_tool_limit_reached():
                logger.warning("Agent execution reached max tool call limit of %d", context.limits.max_tool_calls)
                return self._build_limit_result(context, f"Maximum tool calls ({context.limits.max_tool_calls}) exceeded")

            # 2. Advance turn count and ensure context is pruned within token budget
            context.current_turn += 1
            context = self.context_manager.prune_or_truncate(context)

            # 3. Decision phase: Reasoning engine chooses the next action
            state = AgentState.PLANNING
            try:
                action = await self.reasoning_engine.decide(context, tools)
            except Exception as e:
                logger.error("Reasoning engine failed on turn %d: %s", context.current_turn, str(e), exc_info=True)
                return AgentLoopResult(
                    status=AgentState.FAILED,
                    response_text="I encountered an internal reasoning failure while processing your request.",
                    turns_used=context.current_turn,
                    tool_calls_used=context.total_tool_calls,
                    duration_sec=time.time() - context.start_time,
                    error=str(e),
                )

            # 4. Handle Terminal Response
            if action.action_type == ActionType.FINAL_RESPONSE:
                logger.info(
                    "Agent loop completed on turn %d with %d tool calls",
                    context.current_turn,
                    context.total_tool_calls,
                )
                stop_payload = await self.hook_registry.trigger(
                    HookEvent.AGENT_STOP,
                    {"response_text": action.response_text or "Task completed successfully.", "artifact_ids": action.artifact_ids},
                    context,
                )
                summary = action.execution_summary or self._generate_default_summary(context)
                return AgentLoopResult(
                    status=AgentState.COMPLETED,
                    response_text=stop_payload.get("response_text", action.response_text or "Task completed successfully."),
                    artifact_ids=stop_payload.get("artifact_ids", action.artifact_ids),
                    execution_summary=summary,
                    turns_used=context.current_turn,
                    tool_calls_used=context.total_tool_calls,
                    duration_sec=time.time() - context.start_time,
                )

            # 5. Handle Error Action
            if action.action_type == ActionType.ERROR:
                err_msg = action.error or "Agent encountered an execution error"
                logger.error("Agent returned error action: %s", err_msg)
                return AgentLoopResult(
                    status=AgentState.FAILED,
                    response_text=f"An error occurred: {err_msg}",
                    turns_used=context.current_turn,
                    tool_calls_used=context.total_tool_calls,
                    duration_sec=time.time() - context.start_time,
                    error=err_msg,
                )

            # 6. Handle Subagent Delegation (Phase D4.4)
            if action.action_type == ActionType.DELEGATE:
                subagent_name = action.subagent_name or "research_agent"
                task_desc = action.response_text or context.user_request
                logger.info("Delegating to subagent '%s' for task: %s", subagent_name, task_desc)
                sub_res = await self.subagent_coordinator.dispatch(
                    subagent_name=subagent_name,
                    task=task_desc,
                    context=context,
                    available_tools=tools,
                )
                obs_result = ToolResult.ok(
                    output=sub_res.findings,
                    metadata={"subagent": subagent_name, "status": sub_res.status.value, "data": sub_res.data},
                )
                self.context_manager.record_observation(context, f"delegate:{subagent_name}", f"sub_{context.current_turn}", obs_result)
                continue

            # 7. Sequential Tool Execution Phase
            if action.action_type == ActionType.TOOL_CALL:
                state = AgentState.EXECUTING_TOOL

                for call in action.tool_calls:
                    # Check safety limits prior to each sequential tool invocation
                    if context.is_timed_out():
                        return self._build_timeout_result(context, "Execution timed out during tool execution")

                    if context.is_tool_limit_reached():
                        return self._build_limit_result(context, "Tool call limit reached during sequential execution")

                    tool = tools_by_name.get(call.tool_name)
                    if not tool:
                        res = ToolResult.fail(f"Tool '{call.tool_name}' is not registered")
                        self.context_manager.record_observation(context, call.tool_name, call.call_id, res)
                        continue

                    # Duplicate execution & search loop guard
                    past_calls = [
                        (obs.tool_name, obs.result.success)
                        for obs in context.observations
                    ]
                    if call.tool_name == "web_search" and any(t == "web_search" and s for t, s in past_calls):
                        logger.info("web_search already succeeded in current turn; skipping duplicate search to enforce synthesis.")
                        res = ToolResult.fail("Live web search results have already been retrieved. Please synthesize your final response now without invoking web_search again.")
                        self.context_manager.record_observation(context, call.tool_name, call.call_id, res)
                        continue

                    # Hook: PRE_TOOL_USE
                    try:
                        hook_payload = await self.hook_registry.trigger(
                            HookEvent.PRE_TOOL_USE,
                            {"tool_name": call.tool_name, "arguments": call.arguments},
                            context,
                        )
                        call.arguments = hook_payload.get("arguments", call.arguments)
                    except Exception as e:
                        logger.warning("PreToolUse hook rejected tool '%s': %s", call.tool_name, str(e))
                        res = ToolResult.fail(f"PreToolUse hook rejected call: {str(e)}")
                        self.context_manager.record_observation(context, call.tool_name, call.call_id, res)
                        continue

                    # Permission check
                    decision = self.permission_manager.check_tool(tool, context.session_id, call.arguments)
                    if decision == "requires_approval":
                        appr = self.permission_manager.approval_mgr.request_approval(
                            session_id=context.session_id,
                            tool_name=call.tool_name,
                            arguments=call.arguments,
                        )
                        logger.info("Paused tool '%s' waiting approval (approval_id=%s)", call.tool_name, appr.approval_id)
                        summary = self._generate_default_summary(context)
                        return AgentLoopResult(
                            status=AgentState.WAITING_APPROVAL,
                            response_text=f"Action '{call.tool_name}' requires confirmation before proceeding.",
                            execution_summary=summary,
                            turns_used=context.current_turn,
                            tool_calls_used=context.total_tool_calls,
                            duration_sec=time.time() - context.start_time,
                            approval_id=appr.approval_id,
                        )

                    try:
                        logger.info("Executing tool '%s' (call_id=%s)", call.tool_name, call.call_id)
                        res = await tool.execute(call.arguments, context=context)
                    except Exception as e:
                        logger.error("Tool '%s' execution threw exception: %s", call.tool_name, str(e), exc_info=True)
                        res = ToolResult.fail(f"Tool execution failed: {str(e)}")

                    # Hook: POST_TOOL_USE
                    try:
                        post_payload = await self.hook_registry.trigger(
                            HookEvent.POST_TOOL_USE,
                            {"tool_name": call.tool_name, "output": res.output, "metadata": res.metadata},
                            context,
                        )
                        res.output = post_payload.get("output", res.output)
                        res.metadata = post_payload.get("metadata", res.metadata)
                    except Exception as e:
                        logger.warning("PostToolUse hook error for tool '%s': %s", call.tool_name, str(e))

                    # Record observation in turn scratchpad
                    self.context_manager.record_observation(context, call.tool_name, call.call_id, res)

    def _build_timeout_result(self, context: AgentContext, reason: str) -> AgentLoopResult:
        """Create a safe timeout degradation result."""
        summary = self._generate_default_summary(context)
        return AgentLoopResult(
            status=AgentState.FAILED,
            response_text=f"The operation timed out before completion: {reason}.",
            execution_summary=summary,
            turns_used=context.current_turn,
            tool_calls_used=context.total_tool_calls,
            duration_sec=time.time() - context.start_time,
            error=reason,
        )

    def _build_limit_result(self, context: AgentContext, reason: str) -> AgentLoopResult:
        """Create a safe operational limit degradation result."""
        summary = self._generate_default_summary(context)
        return AgentLoopResult(
            status=AgentState.FAILED,
            response_text=f"Operation stopped: {reason}.",
            execution_summary=summary,
            turns_used=context.current_turn,
            tool_calls_used=context.total_tool_calls,
            duration_sec=time.time() - context.start_time,
            error=reason,
        )

    @staticmethod
    def _generate_default_summary(context: AgentContext) -> Optional[str]:
        """Compile a clean, safe public execution summary from scratchpad observations.
        
        Strictly zero private model chain-of-thought.
        """
        if not context.observations:
            return None

        tools_executed = [obs.tool_name for obs in context.observations]
        unique_tools = sorted(set(tools_executed))
        return f"Executed {len(context.observations)} tool operations across: {', '.join(unique_tools)}."
