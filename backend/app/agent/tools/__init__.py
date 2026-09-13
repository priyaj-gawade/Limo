"""Limo Agent Tools framework and default registry factory."""

from .registry import ToolRegistry
from .source_tool import SourceReadTool, SourceRegisterTool
from .project_tool import ProjectTool
from .chat_tool import ChatTool
from .transform_tool import TransformContractTool
from .job_tool import JobTool
from .artifact_tool import ArtifactTool
from .storage_tool import StorageTool


def create_default_tool_registry() -> ToolRegistry:
    """Instantiate and populate the standard tool registry with all default service-backed tools."""
    registry = ToolRegistry()
    registry.register(SourceReadTool())
    registry.register(SourceRegisterTool())
    registry.register(ProjectTool())
    registry.register(ChatTool())
    registry.register(TransformContractTool())
    registry.register(JobTool())
    registry.register(ArtifactTool())
    registry.register(StorageTool())
    return registry


__all__ = [
    "ToolRegistry",
    "SourceReadTool",
    "SourceRegisterTool",
    "ProjectTool",
    "ChatTool",
    "TransformContractTool",
    "JobTool",
    "ArtifactTool",
    "StorageTool",
    "create_default_tool_registry",
]
