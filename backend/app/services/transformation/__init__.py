"""Transformation Planning & Engine Routing services package (Phase D6).

Architectural Roles:
- D6: Transformation Planning & Engine Routing (Deterministic Contract Layer & Native Adapters)
- D7: GenOffice Execution Engines (Docs / Slides / Sheets)
- D8: Video Execution Engine (OpenMontage + MPT)
"""

from .config_resolver import TransformationConfigResolver, transformation_config_resolver
from .contracts import GenerationContractBuilder, generation_contract_builder
from .engine_router import EngineRouter, engine_router
from .output_planner import OutputPlanner, output_planner
from .workflow_orchestrator import TransformationWorkflowOrchestrator, workflow_orchestrator
from .event_broker import TransformationEventBroker, event_broker
from .handoff import JobArtifactHandoffService, job_artifact_handoff_service

__all__ = [
    "TransformationConfigResolver",
    "transformation_config_resolver",
    "GenerationContractBuilder",
    "generation_contract_builder",
    "EngineRouter",
    "engine_router",
    "OutputPlanner",
    "output_planner",
    "TransformationWorkflowOrchestrator",
    "workflow_orchestrator",
    "TransformationEventBroker",
    "event_broker",
    "JobArtifactHandoffService",
    "job_artifact_handoff_service",
]

