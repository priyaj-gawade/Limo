"""Domain contracts and data models for Transformation Planning & Routing (Phase D6).

Architectural Roles:
- D6: Transformation Planning & Engine Routing (Deterministic Contract Layer)
- D7: GenOffice Execution Engines (Docs / Slides / Sheets)
- D8: Video Execution Engine (OpenMontage + MPT)
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator

from .base import LimoBaseModel
from .enums import OutputFormat
from .generation_config import GenerationConfig
from ..core.ids import (
    generate_deliverable_id,
    generate_plan_id,
    generate_request_id,
)


class EngineType(StrEnum):
    """Authoritative execution engines across Limo."""
    GENOFFICE_DOCS = "genoffice_docs"          # Phase D7: GenOffice Electron Main -> Docs
    GENOFFICE_SLIDES = "genoffice_slides"      # Phase D7: GenOffice Electron Main -> Slides
    GENOFFICE_SHEETS = "genoffice_sheets"      # Phase D7: GenOffice Electron Main -> Sheets
    VIDEO_ENGINE = "video_engine"              # Phase D8: OpenMontage + MoneyPrinterTurbo
    NATIVE_SOCIAL = "native_social"            # Phase D6.3: Native LinkedIn/Twitter adapters
    NATIVE_INFOGRAPHIC = "native_infographic"  # Phase D6.3: Native SVG/diagram adapter
    NATIVE_MARKDOWN = "native_markdown"        # Phase D6.3: Native Markdown/HTML adapter
    TTS_ENGINE = "tts_engine"                  # Phase D8.3: Standalone TTS & Voice Layer
    PRISMO_ENGINE = "prismo_engine"            # Phase D8.8: Prismo Poster & Infographic Engine


class TransformationRequest(LimoBaseModel):
    """Validated input specification for deliverable transformation (Phase D6.1)."""
    id: str = Field(default_factory=generate_request_id, description="Request ID with 'req_' prefix")
    project_id: Optional[str] = Field(default=None, description="Associated project ID")
    session_id: Optional[str] = Field(default=None, description="Active chat session ID")
    canonical_id: str = Field(description="ID of the underlying D5 CanonicalContent")
    canonical_hash: str = Field(min_length=64, max_length=64, description="Cryptographic SHA-256 hash of CanonicalContent")
    requested_formats: List[OutputFormat] = Field(min_length=1, description="Target transformation deliverables")
    config: GenerationConfig = Field(default_factory=GenerationConfig, description="Reconciled generation configuration")
    user_prompt: Optional[str] = Field(default=None, description="Raw user prompt or direct guidance")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("id")
    @classmethod
    def validate_request_id(cls, v: str) -> str:
        if not v.startswith("req_"):
            raise ValueError("TransformationRequest ID must start with 'req_'")
        return v


class EngineRoute(LimoBaseModel):
    """Designated execution route for a specific deliverable format."""
    format: OutputFormat = Field(description="Target output deliverable format")
    engine_type: EngineType = Field(description="Selected execution engine")
    target_extension: str = Field(description="Standard file extension, e.g., '.docx', '.pptx', '.xlsx'")
    is_implemented: bool = Field(default=False, description="True if engine is active in current phase")
    target_phase: str = Field(description="Roadmap phase responsible for execution, e.g., 'D7 (GenOffice)'")
    dispatch_endpoint: Optional[str] = Field(default=None, description="IPC or HTTP endpoint for the engine")


class PlannedDeliverable(LimoBaseModel):
    """Individual deliverable planned within a transformation workflow."""
    deliverable_id: str = Field(default_factory=generate_deliverable_id, description="Stable deliverable ID, e.g., 'del_...'")
    format: OutputFormat = Field(description="Deliverable format")
    title: str = Field(description="Working title of the deliverable")
    route: EngineRoute = Field(description="Assigned engine route")
    options: Dict[str, Any] = Field(default_factory=dict, description="Resolved deliverable-specific options")
    estimated_complexity: str = Field(default="standard", description="Complexity tier")

    @field_validator("deliverable_id")
    @classmethod
    def validate_deliverable_id(cls, v: str) -> str:
        if not v.startswith("del_"):
            raise ValueError("PlannedDeliverable ID must start with 'del_'")
        return v


class OutputPlan(LimoBaseModel):
    """Consolidated execution plan produced by D6.2 Output Planning."""
    id: str = Field(default_factory=generate_plan_id, description="Unique plan ID, e.g., 'plan_...'")
    request_id: str = Field(description="Referenced TransformationRequest ID")
    canonical_id: str = Field(description="Referenced CanonicalContent ID")
    canonical_hash: str = Field(description="Provenanced canonical content hash")
    deliverables: List[PlannedDeliverable] = Field(min_length=1, description="Planned deliverables")
    routes: Dict[OutputFormat, EngineRoute] = Field(description="Mapping of format to assigned route")
    all_engines_available: bool = Field(description="True if all planned deliverables have implemented engines")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("id")
    @classmethod
    def validate_plan_id(cls, v: str) -> str:
        if not v.startswith("plan_"):
            raise ValueError("OutputPlan ID must start with 'plan_'")
        return v
