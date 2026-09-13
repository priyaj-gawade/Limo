"""Source management tools for Limo Agent Infrastructure.

Strictly separates READ operations (inspecting sources) from WRITE operations
(registering new text sources) to uphold security and permission boundaries.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from ..contracts import BaseTool, ToolResult, PermissionType
from ..context import AgentContext
from ...services.source_service import SourceService, source_service
from ...exceptions import EntityNotFoundError, StorageError


class SourceReadArgs(BaseModel):
    action: str = Field(description="Action to perform: 'list_sources', 'get_source_content', or 'retrieve_context'")
    project_id: Optional[str] = Field(default=None, description="Project ID (required for 'list_sources' if not in context)")
    source_id: Optional[str] = Field(default=None, description="Source ID (required for 'get_source_content', optional target for 'retrieve_context')")
    query: Optional[str] = Field(default=None, description="Informational search query (required for 'retrieve_context')")
    max_tokens: Optional[int] = Field(default=None, description="Max token budget for retrieved chunks (defaults to context budget)")
    max_chars: Optional[int] = Field(default=4000, description="Max text characters to return for content read (to prevent context bloat)")


class SourceReadTool(BaseTool):
    """Read-only tool for inspecting sources, direct content reading, and section-aware context retrieval."""

    name: str = "source_read"
    description: str = "Inspect project sources, read direct content, or retrieve grounded section-aware context chunks within a token budget."
    permission_type: PermissionType = PermissionType.READ

    def __init__(
        self,
        service: Optional[SourceService] = None,
        retrieval: Optional[Any] = None,
    ) -> None:
        self.service = service or source_service
        self._retrieval = retrieval

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return SourceReadArgs.model_json_schema()

    async def execute(self, args: Dict[str, Any], context: Optional[AgentContext] = None) -> ToolResult:
        parsed = SourceReadArgs(**args)
        
        if parsed.action == "list_sources":
            project_id = parsed.project_id or (context.project_id if context else None)
            if not project_id:
                return ToolResult.fail("Missing required 'project_id' for listing sources")
            
            sources = self.service.list_sources(project_id)
            summaries = [
                {
                    "id": s.id,
                    "name": s.name,
                    "source_type": s.source_type.value if hasattr(s.source_type, "value") else str(s.source_type),
                    "size_bytes": s.size_bytes,
                    "mime_type": s.mime_type,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in sources
            ]
            return ToolResult.ok({"sources": summaries, "count": len(summaries)})

        elif parsed.action == "get_source_content":
            if not parsed.source_id:
                return ToolResult.fail("Missing required 'source_id' for get_source_content")
            
            try:
                source = self.service.get_source(parsed.source_id)
                raw_bytes = self.service.read_source_content(parsed.source_id)
                text = raw_bytes.decode("utf-8", errors="replace")
                
                # Apply character budget to protect context
                truncated = False
                if parsed.max_chars and len(text) > parsed.max_chars:
                    text = text[:parsed.max_chars]
                    truncated = True

                return ToolResult.ok({
                    "source_id": source.id,
                    "name": source.name,
                    "mime_type": source.mime_type,
                    "content": text,
                    "total_chars": len(raw_bytes),
                    "truncated": truncated,
                })
            except EntityNotFoundError:
                return ToolResult.fail(f"Source '{parsed.source_id}' not found")
            except StorageError as e:
                return ToolResult.fail(f"Storage error reading source: {str(e)}")

        elif parsed.action == "retrieve_context":
            if not parsed.query:
                return ToolResult.fail("Missing required 'query' for retrieve_context")

            from ...services.retrieval.service import retrieval_service
            retriever_svc = self._retrieval or retrieval_service

            try:
                result = await retriever_svc.retrieve_context(
                    query=parsed.query,
                    source_id=parsed.source_id,
                    max_tokens=parsed.max_tokens,
                    context=context,
                )
                return ToolResult.ok({
                    "query": result.query,
                    "chunks": [c.model_dump() for c in result.chunks],
                    "chunks_count": len(result.chunks),
                    "total_tokens": result.total_tokens_returned,
                    "budget_exhausted": result.budget_exhausted,
                })
            except EntityNotFoundError as e:
                return ToolResult.fail(f"Source not found: {str(e)}")
            except StorageError as e:
                return ToolResult.fail(f"Storage error reading source: {str(e)}")
            except Exception as e:
                return ToolResult.fail(f"Retrieval error: {str(e)}")
        else:
            return ToolResult.fail(f"Unknown action '{parsed.action}'. Supported: 'list_sources', 'get_source_content', 'retrieve_context'")


class SourceRegisterArgs(BaseModel):
    name: str = Field(description="Human-readable title/name of the source snippet")
    text_content: str = Field(description="Raw text content to persist as a source file")
    project_id: Optional[str] = Field(default=None, description="Target Project ID (defaults to active context)")


class SourceRegisterTool(BaseTool):
    """Guarded WRITE tool for registering new text sources into project persistence."""

    name: str = "source_register"
    description: str = "Register a new text source into a project. Requires explicit WRITE capability."
    permission_type: PermissionType = PermissionType.WRITE

    def __init__(self, service: Optional[SourceService] = None) -> None:
        self.service = service or source_service

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return SourceRegisterArgs.model_json_schema()

    async def execute(self, args: Dict[str, Any], context: Optional[AgentContext] = None) -> ToolResult:
        parsed = SourceRegisterArgs(**args)
        
        project_id = parsed.project_id or (context.project_id if context else None)
        if not parsed.name.strip():
            return ToolResult.fail("Source name cannot be blank")
        if not parsed.text_content.strip():
            return ToolResult.fail("Source text_content cannot be empty")

        try:
            source = self.service.register_text_source(
                name=parsed.name,
                text_content=parsed.text_content,
                project_id=project_id,
            )
            return ToolResult.ok({
                "source_id": source.id,
                "name": source.name,
                "project_id": source.project_id,
                "size_bytes": source.size_bytes,
                "content_hash": source.content_hash,
            })
        except EntityNotFoundError:
            return ToolResult.fail(f"Target project '{project_id}' not found")
        except Exception as e:
            return ToolResult.fail(f"Failed to register source: {str(e)}")
