"""OpenMontage Video Engine Boundary Contract (Scheduled for full implementation in Phase D8)."""

from typing import Any, Dict, List
from ..client import MCPClientAdapter, MCPToolWrapper, MCPTransportType


class VideoEngineBoundaryContract:
    """Defines the formal external MCP interface for the OpenMontage video rendering engine."""

    SERVER_NAME = "openmontage"

    @classmethod
    def get_tool_definitions(cls) -> List[Dict[str, Any]]:
        """Declare standard OpenMontage external tools."""
        return [
            {
                "name": "render_video",
                "description": "Render a short-form video deliverable via OpenMontage (Phase D8)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "script": {"type": "string", "description": "Narration script text"},
                        "aspect_ratio": {"type": "string", "description": "16:9 or 9:16", "default": "16:9"},
                        "voice": {"type": "string", "description": "TTS voice name"},
                    },
                    "required": ["script"],
                },
            },
        ]

    @classmethod
    def register(cls, adapter: MCPClientAdapter) -> List[MCPToolWrapper]:
        """Register OpenMontage server and return namespaced tool wrappers."""
        adapter.register_server(
            server_name=cls.SERVER_NAME,
            transport=MCPTransportType.STREAMABLE_HTTP,
            endpoint_or_command="http://127.0.0.1:8200/mcp",
        )
        return adapter.wrap_tools(cls.SERVER_NAME, cls.get_tool_definitions())
