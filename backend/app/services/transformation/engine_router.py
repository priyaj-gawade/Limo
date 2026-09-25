"""Authoritative Engine Router for deliverable formats (Phase D6.3).

Maintains the authoritative product routing directory between OutputFormat and EngineRoute:
- Native Adapters (Phase D6.3: Markdown, HTML, LinkedIn, Twitter, SVG):
  is_implemented=True -> Executes in-process deterministic generation producing real Artifacts.
- External Engines (Phase D7: GenOffice Docs/Slides/Sheets; Phase D8: Video Engine):
  is_implemented=False -> Physical dispatch strictly blocked with UnimplementedEngineError.
  Zero mock, synthetic, or fake office/video deliverables are generated.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Union

from ...exceptions import UnimplementedEngineError, UnsupportedFormatError
from ...models.artifact import Artifact
from ...models.content import CanonicalContent
from ...models.enums import ArtifactType, OutputFormat, ValidationStatus
from ...models.generation_config import GenerationConfig
from ...models.generation_contracts import GenOfficePayload, VideoEnginePayload
from ...models.transformation import EngineRoute, EngineType, PlannedDeliverable
from .adapters.base import BaseNativeAdapter
from .adapters.image_adapter import PrismoImageAdapter
from .adapters.infographic_adapter import NativeInfographicAdapter
from .adapters.markdown_adapter import NativeHtmlAdapter, NativeMarkdownAdapter
from .adapters.social_adapter import NativeSocialAdapter
from .adapters.video_adapter import OpenMontageVideoAdapter
from .adapters.genoffice_adapter import GenOfficeAdapter
from .contracts import generation_contract_builder

logger = logging.getLogger("limo.services.transformation.engine_router")


class EngineRouter:
    """Authoritative routing directory and dispatcher for transformation deliverable engines."""

    ROUTING_TABLE: Dict[OutputFormat, EngineRoute] = {
        OutputFormat.DOCUMENT: EngineRoute(
            format=OutputFormat.DOCUMENT,
            engine_type=EngineType.GENOFFICE_DOCS,
            target_extension=".docx",
            is_implemented=True,
            target_phase="D7 (GenOffice)",
            dispatch_endpoint="/api/v1/genoffice/docs",
        ),
        OutputFormat.PRESENTATION: EngineRoute(
            format=OutputFormat.PRESENTATION,
            engine_type=EngineType.GENOFFICE_SLIDES,
            target_extension=".pptx",
            is_implemented=True,
            target_phase="D7 (GenOffice)",
            dispatch_endpoint="/api/v1/genoffice/slides",
        ),
        OutputFormat.SPREADSHEET: EngineRoute(
            format=OutputFormat.SPREADSHEET,
            engine_type=EngineType.GENOFFICE_SHEETS,
            target_extension=".xlsx",
            is_implemented=True,
            target_phase="D7 (GenOffice)",
            dispatch_endpoint="/api/v1/genoffice/sheets",
        ),
        OutputFormat.ADVISORY: EngineRoute(
            format=OutputFormat.ADVISORY,
            engine_type=EngineType.GENOFFICE_DOCS,
            target_extension=".docx",
            is_implemented=True,
            target_phase="D7 (GenOffice)",
            dispatch_endpoint="/api/v1/genoffice/docs",
        ),
        OutputFormat.SUMMARY: EngineRoute(
            format=OutputFormat.SUMMARY,
            engine_type=EngineType.GENOFFICE_DOCS,
            target_extension=".docx",
            is_implemented=True,
            target_phase="D7 (GenOffice)",
            dispatch_endpoint="/api/v1/genoffice/docs",
        ),
        OutputFormat.PDF: EngineRoute(
            format=OutputFormat.PDF,
            engine_type=EngineType.GENOFFICE_DOCS,
            target_extension=".pdf",
            is_implemented=True,
            target_phase="D7 (GenOffice)",
            dispatch_endpoint="/api/v1/genoffice/docs",
        ),
        OutputFormat.VIDEO: EngineRoute(
            format=OutputFormat.VIDEO,
            engine_type=EngineType.VIDEO_ENGINE,
            target_extension=".mp4",
            is_implemented=True,
            target_phase="D8.2 (Video Engine)",
            dispatch_endpoint=None,
        ),
        OutputFormat.LINKEDIN: EngineRoute(
            format=OutputFormat.LINKEDIN,
            engine_type=EngineType.NATIVE_SOCIAL,
            target_extension=".md",
            is_implemented=True,
            target_phase="D6.3 (Native Adapters)",
            dispatch_endpoint=None,
        ),
        OutputFormat.TWITTER: EngineRoute(
            format=OutputFormat.TWITTER,
            engine_type=EngineType.NATIVE_SOCIAL,
            target_extension=".json",
            is_implemented=True,
            target_phase="D6.3 (Native Adapters)",
            dispatch_endpoint=None,
        ),
        OutputFormat.INFOGRAPHIC: EngineRoute(
            format=OutputFormat.INFOGRAPHIC,
            engine_type=EngineType.PRISMO_ENGINE,
            target_extension=".png",
            is_implemented=True,
            target_phase="D8.8 (Prismo Integration)",
            dispatch_endpoint=None,
        ),
        OutputFormat.MARKDOWN: EngineRoute(
            format=OutputFormat.MARKDOWN,
            engine_type=EngineType.NATIVE_MARKDOWN,
            target_extension=".md",
            is_implemented=True,
            target_phase="D6.3 (Native Adapters)",
            dispatch_endpoint=None,
        ),
        OutputFormat.HTML: EngineRoute(
            format=OutputFormat.HTML,
            engine_type=EngineType.NATIVE_MARKDOWN,
            target_extension=".html",
            is_implemented=True,
            target_phase="D6.3 (Native Adapters)",
            dispatch_endpoint=None,
        ),
        OutputFormat.AUDIO: EngineRoute(
            format=OutputFormat.AUDIO,
            engine_type=EngineType.TTS_ENGINE,
            target_extension=".mp3",
            is_implemented=True,
            target_phase="D8.3 (TTS & Voice Layer)",
            dispatch_endpoint=None,
        ),
    }

    def __init__(self):
        # Instantiate singleton adapters for native formats, video, prismo, and GenOffice
        self._markdown_adapter = NativeMarkdownAdapter()
        self._html_adapter = NativeHtmlAdapter()
        self._social_adapter = NativeSocialAdapter()
        self._infographic_adapter = NativeInfographicAdapter()  # Preserved for backward reference
        self._prismo_adapter = PrismoImageAdapter()             # Authoritative D8.8 poster engine
        self._video_adapter = OpenMontageVideoAdapter()
        self._genoffice_adapter = GenOfficeAdapter()            # Authoritative D7 office engine
        self._native_adapters: Dict[OutputFormat, Any] = {
            OutputFormat.MARKDOWN: self._markdown_adapter,
            OutputFormat.HTML: self._html_adapter,
            OutputFormat.LINKEDIN: self._social_adapter,
            OutputFormat.TWITTER: self._social_adapter,
            OutputFormat.INFOGRAPHIC: self._prismo_adapter,
            OutputFormat.VIDEO: self._video_adapter,
            OutputFormat.DOCUMENT: self._genoffice_adapter,
            OutputFormat.PRESENTATION: self._genoffice_adapter,
            OutputFormat.SPREADSHEET: self._genoffice_adapter,
            OutputFormat.ADVISORY: self._genoffice_adapter,
            OutputFormat.SUMMARY: self._genoffice_adapter,
            OutputFormat.PDF: self._genoffice_adapter,
        }

    def get_route(self, fmt: OutputFormat) -> EngineRoute:
        """Resolve the designated EngineRoute for a deliverable format."""
        if not isinstance(fmt, OutputFormat):
            try:
                fmt = OutputFormat(str(fmt).lower().strip())
            except ValueError:
                raise UnsupportedFormatError(
                    raw_format=str(fmt),
                    supported_formats=[f.value for f in OutputFormat],
                )
        return self.ROUTING_TABLE[fmt].model_copy()

    def get_native_adapter(self, fmt: OutputFormat) -> Any:
        """Return the concrete native adapter instance for a supported native format."""
        adapter = self._native_adapters.get(fmt)
        if not adapter:
            raise UnsupportedFormatError(
                raw_format=fmt.value,
                supported_formats=[f.value for f in OutputFormat],
            )
        return adapter

    def dispatch(
        self,
        route: EngineRoute,
        deliverable: Optional[PlannedDeliverable] = None,
        canonical: Optional[CanonicalContent] = None,
        config: Optional[GenerationConfig] = None,
        project_id: Optional[str] = None,
        job_id: Optional[str] = None,
        unified_input: Optional[Any] = None,
        progress_callback: Optional[Any] = None,
    ) -> Optional[Artifact]:
        """Dispatch execution. Executes native adapters or blocks unimplemented external engines."""
        if not route.is_implemented:
            logger.warning(
                "Execution dispatch blocked for engine '%s' (format: %s, target: %s).",
                route.engine_type.value,
                route.format.value,
                route.target_phase,
            )
            raise UnimplementedEngineError(
                engine_type=route.engine_type.value,
                target_phase=route.target_phase,
            )

        # Direct native engine execution on EC2 host
        if deliverable and (canonical or unified_input):
            adapter = self.get_native_adapter(deliverable.format)
            effective_config = config or GenerationConfig()

            if deliverable.format == OutputFormat.INFOGRAPHIC:
                artifact = adapter.execute(
                    canonical=canonical,
                    deliverable=deliverable,
                    config=effective_config,
                    project_id=project_id,
                    job_id=job_id,
                    unified_input=unified_input,
                    progress_callback=progress_callback,
                )
            elif deliverable.format == OutputFormat.VIDEO:
                artifact = adapter.execute(
                    canonical=canonical,
                    deliverable=deliverable,
                    config=effective_config,
                    project_id=project_id,
                    job_id=job_id,
                    progress_callback=progress_callback,
                )
            else:
                artifact = adapter.execute(
                    canonical=canonical,
                    deliverable=deliverable,
                    config=effective_config,
                    project_id=project_id,
                    job_id=job_id,
                )
            return artifact

        return None

    def build_contract(
        self,
        deliverable: PlannedDeliverable,
        canonical: CanonicalContent,
        config: GenerationConfig,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Union[GenOfficePayload, VideoEnginePayload, Dict[str, Any]]:
        """Construct the execution payload or contract for a deliverable."""
        route = deliverable.route
        if route.engine_type in (
            EngineType.GENOFFICE_DOCS,
            EngineType.GENOFFICE_SLIDES,
            EngineType.GENOFFICE_SHEETS,
        ):
            return generation_contract_builder.build_genoffice_payload(
                canonical=canonical,
                deliverable=deliverable,
                config=config,
                project_id=project_id,
                session_id=session_id,
            )
        elif route.engine_type == EngineType.VIDEO_ENGINE:
            return generation_contract_builder.build_video_generation_contract(
                canonical=canonical,
                deliverable=deliverable,
                config=config,
                job_id=session_id or deliverable.deliverable_id,
            )
        else:
            # Native deliverable preview/contract
            adapter = self.get_native_adapter(deliverable.format)
            gen = adapter.synthesize(canonical=canonical, deliverable=deliverable, config=config)
            return {
                "format": deliverable.format.value,
                "engine_type": route.engine_type.value,
                "filename": gen.filename,
                "stats": gen.stats,
                "metadata": gen.metadata,
                "canonical_id": canonical.id,
                "canonical_hash": canonical.content_hash,
            }

    def list_supported_formats(self) -> List[OutputFormat]:
        """Return the authoritative list of supported output formats."""
        return list(self.ROUTING_TABLE.keys())


engine_router = EngineRouter()
