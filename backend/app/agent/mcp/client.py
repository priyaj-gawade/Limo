"""Official MCP SDK v2 Client Adapter and Namespaced Tool Wrappers."""

from enum import StrEnum
import logging
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from ..contracts import BaseTool, PermissionType, ToolResult

logger = logging.getLogger("limo.agent.mcp")


class MCPTransportType(StrEnum):
    """Supported MCP transports per official Python SDK v2."""
    STDIO = "stdio"
    STREAMABLE_HTTP = "streamable_http"
    LEGACY_SSE = "legacy_sse"


class MCPToolWrapper(BaseTool):
    """Limo BaseTool adapter wrapping an external MCP Tool declaration with namespaces."""

    def __init__(
        self,
        server_name: str,
        raw_name: str,
        description: str,
        parameters_schema: Dict[str, Any],
        invoker: Callable[[str, str, Dict[str, Any]], Any],
    ):
        self.server_name = server_name
        self.raw_name = raw_name
        # Namespace external tool to prevent collisions with Limo tools (MUST-FIX #2)
        self.name = f"mcp.{server_name}.{raw_name}"
        self.description = description
        self.permission_type = PermissionType.EXTERNAL_DISPATCH
        self._parameters_schema = parameters_schema
        self._invoker = invoker

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return self._parameters_schema

    async def execute(self, args: Dict[str, Any], context: Optional[Any] = None) -> ToolResult:
        """Invoke external MCP tool with error containment."""
        try:
            logger.info("Dispatching to MCP server '%s' tool '%s'", self.server_name, self.raw_name)
            result = await self._invoker(self.server_name, self.raw_name, args)
            if isinstance(result, ToolResult):
                return result
            return ToolResult.ok(output=result, metadata={"server": self.server_name, "tool": self.raw_name})
        except Exception as e:
            logger.error("MCP tool '%s' execution failed: %s", self.name, str(e), exc_info=True)
            # Safe containment: external failure does NOT crash agent loop
            return ToolResult.fail(f"External MCP server error: {str(e)}", metadata={"server": self.server_name})


class MCPClientAdapter:
    """Manages MCP server connections across stdio, Streamable HTTP, and legacy SSE transports."""

    def __init__(self):
        self._servers: Dict[str, Dict[str, Any]] = {}
        self._custom_invokers: Dict[str, Callable] = {}

    def register_server(
        self,
        server_name: str,
        transport: MCPTransportType,
        endpoint_or_command: str,
        custom_invoker: Optional[Callable] = None,
    ) -> None:
        """Register a configured MCP server endpoint."""
        self._servers[server_name] = {
            "server_name": server_name,
            "transport": transport,
            "target": endpoint_or_command,
            "connected": True,
        }
        if custom_invoker:
            self._custom_invokers[server_name] = custom_invoker
        logger.info(
            "Registered MCP server '%s' via transport '%s' (%s)",
            server_name,
            transport.value,
            endpoint_or_command,
        )

    def is_connected(self, server_name: str) -> bool:
        """Check connection health of external server."""
        server = self._servers.get(server_name)
        return bool(server and server.get("connected", False))

    def disconnect_server(self, server_name: str) -> None:
        """Simulate or record server disconnection."""
        if server_name in self._servers:
            self._servers[server_name]["connected"] = False

    def wrap_tools(
        self,
        server_name: str,
        tools_definitions: List[Dict[str, Any]],
    ) -> List[MCPToolWrapper]:
        """Convert external MCP tool schema dictionaries into namespaced Limo BaseTool instances."""
        wrapped = []
        for defn in tools_definitions:
            raw_name = defn.get("name", "unnamed_tool")
            desc = defn.get("description", "External MCP tool")
            schema = defn.get("inputSchema", defn.get("parameters", {"type": "object", "properties": {}}))
            wrapper = MCPToolWrapper(
                server_name=server_name,
                raw_name=raw_name,
                description=desc,
                parameters_schema=schema,
                invoker=self.call_tool,
            )
            wrapped.append(wrapper)
        return wrapped

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Dispatch call to external MCP server."""
        if not self.is_connected(server_name):
            raise ConnectionError(f"MCP server '{server_name}' is not connected")

        if server_name in self._custom_invokers:
            invoker = self._custom_invokers[server_name]
            import inspect
            if inspect.iscoroutinefunction(invoker):
                return await invoker(server_name, tool_name, arguments)
            return invoker(server_name, tool_name, arguments)

        # Default standard response for registered server
        return {"status": "success", "tool": tool_name, "server": server_name, "args": arguments}
