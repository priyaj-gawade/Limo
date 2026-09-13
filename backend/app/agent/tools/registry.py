"""Tool Registry for Limo Agent Infrastructure.

Manages tool lifecycle:
- Tool registration and schema validation
- Duplicate prevention
- Standard JSON schema generation for LLM function calling
- Safe tool execution with structured error handling and diagnostics
"""

import time
import re
from typing import Any, Dict, List, Optional
from pydantic import ValidationError

from ..contracts import BaseTool, ToolResult, PermissionType
from ..context import AgentContext


class ToolRegistry:
    """Central registry of executable agent tools."""

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance.
        
        Enforces naming convention (snake_case) and uniqueness.
        """
        if not tool.name or not isinstance(tool.name, str):
            raise ValueError(f"Tool name must be a non-empty string. Got: {tool.name}")
        
        if not re.match(r"^[a-z][a-z0-9_]*$", tool.name):
            raise ValueError(
                f"Tool name '{tool.name}' must be snake_case (e.g. 'source_read', 'transform_contract')"
            )

        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered in ToolRegistry")

        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Retrieve a registered tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Generate standardized function calling schemas for all registered tools.
        
        Compatible with OpenAI/Anthropic function calling formats.
        """
        schemas = []
        for tool in self._tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters_schema,
                },
                "permission_type": tool.permission_type.value,
            })
        return schemas

    async def execute(
        self,
        name: str,
        args: Dict[str, Any],
        context: Optional[AgentContext] = None,
    ) -> ToolResult:
        """Execute a tool safely by name.
        
        Catches all exceptions, prevents crashes in the agent loop,
        and returns a structured ToolResult with execution metrics.
        """
        tool = self.get(name)
        if not tool:
            return ToolResult.fail(
                error=f"Tool '{name}' is not registered in ToolRegistry",
                metadata={"tool_name": name, "error_code": "TOOL_NOT_FOUND"},
            )

        start_time = time.perf_counter()
        try:
            result = await tool.execute(args, context=context)
            elapsed = time.perf_counter() - start_time
            result.metadata.setdefault("elapsed_seconds", round(elapsed, 4))
            result.metadata.setdefault("tool_name", name)
            return result
        except ValidationError as e:
            elapsed = time.perf_counter() - start_time
            return ToolResult.fail(
                error=f"Parameter validation failed for tool '{name}': {str(e)}",
                metadata={"tool_name": name, "error_code": "VALIDATION_ERROR", "elapsed_seconds": round(elapsed, 4)},
            )
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            return ToolResult.fail(
                error=f"Tool '{name}' failed with unexpected exception: {str(e)}",
                metadata={"tool_name": name, "error_code": "EXECUTION_ERROR", "elapsed_seconds": round(elapsed, 4)},
            )
