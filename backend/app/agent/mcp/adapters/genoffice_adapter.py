"""GenOffice External Boundary Contract (Scheduled for full implementation in Phase D7)."""

from typing import Any, Dict, List
from ..client import MCPClientAdapter, MCPToolWrapper, MCPTransportType


class GenOfficeBoundaryContract:
    """Defines the formal external MCP interface for the GenOffice workspace engine."""

    SERVER_NAME = "genoffice"

    @classmethod
    def get_tool_definitions(cls) -> List[Dict[str, Any]]:
        """Declare standard GenOffice external tools."""
        return [
            {
                "name": "create_document",
                "description": "Create a DOCX/PDF document via GenOffice engine (Phase D7)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Document title"},
                        "content_markdown": {"type": "string", "description": "Markdown body"},
                    },
                    "required": ["title", "content_markdown"],
                },
            },
            {
                "name": "create_presentation",
                "description": "Create a PPTX slide deck via GenOffice engine (Phase D7)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "Presentation topic"},
                        "slides_count": {"type": "integer", "description": "Target number of slides"},
                    },
                    "required": ["topic"],
                },
            },
            {
                "name": "create_spreadsheet",
                "description": "Create an XLSX workbook via GenOffice engine (Phase D7)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sheet_name": {"type": "string", "description": "Primary sheet title"},
                        "data_rows": {"type": "array", "description": "Rows of structured tabular data"},
                    },
                    "required": ["sheet_name"],
                },
            },
        ]

    @classmethod
    def register(cls, adapter: MCPClientAdapter) -> List[MCPToolWrapper]:
        """Register GenOffice server and return namespaced tool wrappers."""
        adapter.register_server(
            server_name=cls.SERVER_NAME,
            transport=MCPTransportType.STREAMABLE_HTTP,
            endpoint_or_command="http://127.0.0.1:8100/mcp",
        )
        return adapter.wrap_tools(cls.SERVER_NAME, cls.get_tool_definitions())
