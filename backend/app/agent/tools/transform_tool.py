"""Transformation contract management tool for Limo Agent Infrastructure.

Strictly creates and queues transformation job contracts in SQLite.
Does NOT generate, simulate, or render deliverables directly (Rule 1 & Rule 2).
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ..contracts import BaseTool, ToolResult, PermissionType
from ..context import AgentContext
from ...services.transform_service import TransformService, transform_service
from ...models.enums import CommunicationObjective, OutputFormat
from ...models.job import GenerationConfig
from ...exceptions import BadRequestError, EntityNotFoundError


class TransformContractArgs(BaseModel):
    model_config = {"extra": "allow"}

    requested_formats: List[str] = Field(
        description="Target deliverable formats (e.g. 'document', 'presentation', 'spreadsheet', 'video', 'summary', 'docx', 'pptx', 'xlsx', 'markdown', 'html', 'pdf')"
    )
    source_ids: Optional[List[str]] = Field(default_factory=list, description="IDs of ingested sources to transform")
    canonical_id: Optional[str] = Field(default=None, description="ID of underlying D5 CanonicalContent")
    prompt: Optional[str] = Field(default=None, description="Direct user instructions or topic for the deliverable")
    inline_content: Optional[str] = Field(default=None, description="Optional raw inline content to transform")
    audience: Optional[str] = Field(default=None, description="Target audience demographic (e.g. 'Executive', 'Technical')")
    objective: Optional[str] = Field(default=None, description="Strategic communication intent (e.g. 'inform', 'persuade', 'alert')")
    configuration_json: Optional[str] = Field(default=None, description="Optional JSON-encoded string of generation configuration")
    project_id: Optional[str] = Field(default=None, description="Project ID (defaults to active context)")
    session_id: Optional[str] = Field(default=None, description="Chat session ID (defaults to active context)")


class TransformContractTool(BaseTool):
    """Creates a transformation job contract and queues it for background execution.
    
    Adheres strictly to Rule 1 & Rule 2: This tool NEVER renders or simulates deliverables.
    It queues the job in SQLite for subsequent execution by deterministic workflow engines.
    """

    name: str = "transform_contract"
    description: str = (
        "Create a transformation job contract and queue it for background execution. "
        "Does NOT generate or render artifacts directly."
    )
    permission_type: PermissionType = PermissionType.TRANSFORM

    def __init__(self, service: Optional[TransformService] = None) -> None:
        self.service = service or transform_service

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        schema = TransformContractArgs.model_json_schema()
        schema.pop("additionalProperties", None)
        return schema

    def _parse_formats(self, raw_formats: List[str]) -> List[OutputFormat]:
        """Map user/agent format strings to strongly typed OutputFormat enums."""
        aliases = {
            "slides": OutputFormat.PRESENTATION,
            "pptx": OutputFormat.PRESENTATION,
            "mp4": OutputFormat.VIDEO,
            "doc": OutputFormat.DOCUMENT,
            "docx": OutputFormat.DOCUMENT,
            "sheet": OutputFormat.SPREADSHEET,
            "sheets": OutputFormat.SPREADSHEET,
            "xlsx": OutputFormat.SPREADSHEET,
            "csv": OutputFormat.SPREADSHEET,
            "brief": OutputFormat.SUMMARY,
            "md": OutputFormat.MARKDOWN,
        }
        parsed: List[OutputFormat] = []
        for fmt in raw_formats:
            norm = fmt.lower().strip()
            if norm in aliases:
                parsed.append(aliases[norm])
            else:
                try:
                    parsed.append(OutputFormat(norm))
                except ValueError:
                    supported = [f.value for f in OutputFormat] + list(aliases.keys())
                    raise BadRequestError(
                        f"Unsupported output format '{fmt}'. Supported: {supported}"
                    )
        return list(dict.fromkeys(parsed))  # preserve order, deduplicate

    async def execute(self, args: Dict[str, Any], context: Optional[AgentContext] = None) -> ToolResult:
        try:
            parsed_args = TransformContractArgs(**args)
        except Exception as e:
            return ToolResult.fail(f"Invalid arguments for transform contract: {str(e)}")

        project_id = parsed_args.project_id or (context.project_id if context else None)
        session_id = parsed_args.session_id or (context.session_id if context else None)

        try:
            typed_formats = self._parse_formats(parsed_args.requested_formats)
        except BadRequestError as e:
            return ToolResult.fail(str(e))

        config_override = args.get("configuration")
        if not config_override and parsed_args.configuration_json:
            import json
            try:
                config_override = json.loads(parsed_args.configuration_json)
            except Exception:
                pass

        config_obj: Optional[GenerationConfig] = None
        if isinstance(config_override, GenerationConfig):
            config_obj = config_override
        elif isinstance(config_override, dict):
            try:
                config_obj = GenerationConfig.model_validate(config_override)
            except Exception as e:
                return ToolResult.fail(f"Invalid configuration parameters: {str(e)}")
        elif parsed_args.audience or parsed_args.objective:
            cfg_kwargs: Dict[str, Any] = {}
            if parsed_args.audience:
                cfg_kwargs["audience"] = parsed_args.audience
            if parsed_args.objective:
                try:
                    cfg_kwargs["objective"] = CommunicationObjective(parsed_args.objective.lower())
                except ValueError:
                    pass
            config_obj = GenerationConfig(**cfg_kwargs)

        try:
            job = self.service.create_transform_contract(
                requested_formats=typed_formats,
                source_ids=parsed_args.source_ids,
                prompt=parsed_args.prompt,
                inline_content=parsed_args.inline_content,
                configuration=config_obj,
                project_id=project_id,
                session_id=session_id,
                canonical_id=parsed_args.canonical_id,
            )
            return ToolResult.ok({
                "job_id": job.id,
                "status": job.state.value if hasattr(job.state, "value") else str(job.state),
                "requested_formats": [f.value for f in job.requested_formats],
                "source_count": len(job.source_ids),
                "has_prompt": bool(job.prompt),
                "queued": True,
                "message": f"Transformation contract successfully queued (job_id: {job.id}). Execution will be handled by background pipeline.",
            })
        except (BadRequestError, EntityNotFoundError) as e:
            return ToolResult.fail(str(e))
        except Exception as e:
            return ToolResult.fail(f"Failed to queue transformation contract: {str(e)}")
