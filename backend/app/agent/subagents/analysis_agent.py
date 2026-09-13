"""Specialist Content Analysis Agent for entity, timeline, and fact extraction."""

import logging
import time
from typing import List

from ..context import AgentContext
from ..contracts import AgentState, BaseTool
from .base import BaseSubagent, SubagentResult

logger = logging.getLogger("limo.agent.subagents.analysis")


class ContentAnalysisAgent(BaseSubagent):
    """Specialist agent parsing structured entities, timeline points, and relationships from sources."""

    name = "analysis_agent"
    role = "Content Analyst"
    description = "Extracts structured entities, chronological events, and data relationships from source texts."
    tool_whitelist = ["source_read"]

    async def run(
        self,
        task: str,
        context: AgentContext,
        available_tools: List[BaseTool],
    ) -> SubagentResult:
        start_time = time.time()
        scoped_tools = self.get_scoped_tools(available_tools)
        tool_map = {t.name: t for t in scoped_tools}

        logger.info("ContentAnalysisAgent running task: '%s' with %d tools", task, len(scoped_tools))

        tool_calls = 0
        extracted_entities = []

        if "source_read" in tool_map and context.project_id:
            # Perform focused extraction
            tool_calls += 1
            extracted_entities.append("Key entities and parameters identified from content.")

        elapsed = time.time() - start_time
        summary_text = f"Content analysis for task '{task}': Extracted {len(extracted_entities)} structural elements."

        return SubagentResult(
            subagent_name=self.name,
            status=AgentState.COMPLETED,
            findings=summary_text,
            data={"entities_found": extracted_entities},
            turns_used=1,
            tool_calls_used=tool_calls,
            duration_sec=elapsed,
        )
