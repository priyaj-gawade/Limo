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
from ...models.enums import OutputFormat
from ...models.generation_config import GenerationConfig
from ...models.generation_contracts import GenOfficePayload, VideoEnginePayload
from ...models.transformation import EngineRoute, EngineType, PlannedDeliverable
from .adapters.base import BaseNativeAdapter
from .adapters.image_adapter import PrismoImageAdapter
from .adapters.infographic_adapter import NativeInfographicAdapter
from .adapters.markdown_adapter import NativeHtmlAdapter, NativeMarkdownAdapter
from .adapters.social_adapter import NativeSocialAdapter
from .adapters.video_adapter import OpenMontageVideoAdapter
from .contracts import generation_contract_builder

logger = logging.getLogger("limo.services.transformation.engine_router")


class EngineRouter:
    """Authoritative routing directory and dispatcher for transformation deliverable engines."""

    ROUTING_TABLE: Dict[OutputFormat, EngineRoute] = {
        OutputFormat.DOCUMENT: EngineRoute(
            format=OutputFormat.DOCUMENT,
            engine_type=EngineType.GENOFFICE_DOCS,
            target_extension=".docx",
            is_implemented=False,
            target_phase="D7 (GenOffice)",
            dispatch_endpoint="/api/v1/genoffice/docs",
        ),
        OutputFormat.PRESENTATION: EngineRoute(
            format=OutputFormat.PRESENTATION,
            engine_type=EngineType.GENOFFICE_SLIDES,
            target_extension=".pptx",
            is_implemented=False,
            target_phase="D7 (GenOffice)",
            dispatch_endpoint="/api/v1/genoffice/slides",
        ),
        OutputFormat.SPREADSHEET: EngineRoute(
            format=OutputFormat.SPREADSHEET,
            engine_type=EngineType.GENOFFICE_SHEETS,
            target_extension=".xlsx",
            is_implemented=False,
            target_phase="D7 (GenOffice)",
            dispatch_endpoint="/api/v1/genoffice/sheets",
        ),
        OutputFormat.ADVISORY: EngineRoute(
            format=OutputFormat.ADVISORY,
            engine_type=EngineType.GENOFFICE_DOCS,
            target_extension=".docx",
            is_implemented=False,
            target_phase="D7 (GenOffice)",
            dispatch_endpoint="/api/v1/genoffice/docs",
        ),
        OutputFormat.SUMMARY: EngineRoute(
            format=OutputFormat.SUMMARY,
            engine_type=EngineType.GENOFFICE_DOCS,
            target_extension=".docx",
            is_implemented=False,
            target_phase="D7 (GenOffice)",
            dispatch_endpoint="/api/v1/genoffice/docs",
        ),
        OutputFormat.PDF: EngineRoute(
            format=OutputFormat.PDF,
            engine_type=EngineType.GENOFFICE_DOCS,
            target_extension=".pdf",
            is_implemented=False,
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
        # Instantiate singleton adapters for native formats, video, and prismo
        self._markdown_adapter = NativeMarkdownAdapter()
        self._html_adapter = NativeHtmlAdapter()
        self._social_adapter = NativeSocialAdapter()
        self._infographic_adapter = NativeInfographicAdapter()  # Preserved for backward reference
        self._prismo_adapter = PrismoImageAdapter()             # Authoritative D8.8 poster engine
        self._video_adapter = OpenMontageVideoAdapter()
        self._native_adapters: Dict[OutputFormat, Any] = {
            OutputFormat.MARKDOWN: self._markdown_adapter,
            OutputFormat.HTML: self._html_adapter,
            OutputFormat.LINKEDIN: self._social_adapter,
            OutputFormat.TWITTER: self._social_adapter,
            OutputFormat.INFOGRAPHIC: self._prismo_adapter,
            OutputFormat.VIDEO: self._video_adapter,
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
                supported_formats=["markdown", "html", "linkedin", "twitter", "infographic", "video"],
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

        # Implemented native engine execution
        if deliverable and (canonical or unified_input):
            # Turbo Worker Offload for Web Surface or when TURBO_WORKER_URL is explicitly configured
            is_heavy = deliverable.format in (OutputFormat.VIDEO, OutputFormat.INFOGRAPHIC)
            from ...auth.config import auth_config
            import os
            worker_url = os.getenv("TURBO_WORKER_URL")

            if is_heavy and (auth_config.is_web_surface or worker_url):
                try:
                    return self._dispatch_turbo_worker(
                        deliverable=deliverable,
                        canonical=canonical,
                        config=config,
                        project_id=project_id,
                        job_id=job_id,
                        unified_input=unified_input,
                        progress_callback=progress_callback,
                    )
                except Exception as exc:
                    logger.warning("Turbo worker dispatch failed: %s. Checking for native adapter fallback.", exc)
                    adapter = self.get_native_adapter(deliverable.format)
                    is_avail = False
                    if hasattr(adapter, "client") and hasattr(adapter.client, "is_available"):
                        is_avail = adapter.client.is_available()

                    if is_avail:
                        logger.info("Falling back to native in-process adapter for format %s", deliverable.format)
                        effective_config = config or GenerationConfig()
                        return adapter.execute(
                            canonical=canonical,
                            deliverable=deliverable,
                            config=effective_config,
                            project_id=project_id,
                            job_id=job_id,
                            unified_input=unified_input,
                            progress_callback=progress_callback,
                        )
                    raise

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

    def _dispatch_turbo_worker(
        self,
        deliverable: PlannedDeliverable,
        canonical: Optional[CanonicalContent],
        config: Optional[GenerationConfig],
        project_id: Optional[str] = None,
        job_id: Optional[str] = None,
        unified_input: Optional[Any] = None,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> Artifact:
        """Offload heavy rendering (video / infographic) to Turbo Worker via HTTP API."""
        import os
        import uuid
        import httpx
        from ...models.enums import ArtifactType, ValidationStatus
        from ...db.connection import get_connection
        from ...db.repositories.artifact_repo import ArtifactRepository
        from ...exceptions import BadRequestError

        worker_url = os.getenv("TURBO_WORKER_URL", "http://localhost:8005").rstrip("/")
        worker_token = os.getenv("WORKER_AUTH_TOKEN", "limo-turbo-worker-secret-key-12345")

        resolved_job_id = job_id or f"job_{uuid.uuid4().hex[:12]}"
        artifact_id = f"art_{uuid.uuid4().hex[:16]}"
        is_video = deliverable.format == OutputFormat.VIDEO
        deliverable_type = "video" if is_video else "infographic"
        filename = f"{deliverable.deliverable_id}{'.mp4' if is_video else '.png'}"
        mime_type = "video/mp4" if is_video else "image/png"

        if progress_callback:
            progress_callback("worker_dispatch", f"Offloading {deliverable_type} to Turbo Worker")

        req_payload = {
            "job_id": resolved_job_id,
            "artifact_id": artifact_id,
            "deliverable_type": deliverable_type,
            "filename": filename,
            "mime_type": mime_type,
            "payload": {
                "title": deliverable.title,
                "canonical_id": canonical.id if canonical else None,
                "canonical_hash": canonical.content_hash if canonical else None,
            },
        }

        try:
            with httpx.Client(timeout=120.0) as client:
                res = client.post(
                    f"{worker_url}/execute",
                    headers={"X-Limo-Worker-Key": worker_token},
                    json=req_payload,
                )
        except httpx.RequestError as exc:
            logger.error("Turbo Worker unreachable at %s: %s", worker_url, exc)
            raise BadRequestError(f"Turbo Worker is offline or unreachable at {worker_url}") from exc

        if res.status_code != 200:
            logger.error("Turbo Worker execution failed (%d): %s", res.status_code, res.text)
            if res.status_code == 530:
                raise BadRequestError(
                    f"Turbo Worker Cloudflare Tunnel is offline (HTTP 530 at {worker_url}). "
                    "Please start the local Turbo Worker and Cloudflare Tunnel using .\\start-worker.ps1."
                )
            raise BadRequestError(f"Turbo Worker execution failed with status {res.status_code}: {res.text[:200]}")

        data = res.json()
        storage_ref = data.get("artifact_ref", f"worker://{artifact_id}")
        size_bytes = data.get("size_bytes", 0)
        sha256 = data.get("sha256", "")

        art = Artifact(
            id=artifact_id,
            title=deliverable.title,
            artifact_type=ArtifactType.VIDEO if is_video else ArtifactType.INFOGRAPHIC,
            file_format=".mp4" if is_video else ".png",
            storage_ref=storage_ref,
            size_bytes=size_bytes,
            content_hash=sha256,
            project_id=project_id,
            job_id=resolved_job_id,
            validation_status=ValidationStatus.VALID,
            metadata={
                "deliverable_id": deliverable.deliverable_id,
                "rendered_by": "turbo_worker",
                "format": deliverable.format.value,
                "worker_url": worker_url,
            },
        )

        with get_connection() as conn:
            ArtifactRepository.create_artifact(conn, art)

        logger.info(
            "Turbo Worker offload completed for %s: %s (%s, %d bytes)",
            deliverable_type,
            art.id,
            art.storage_ref,
            art.size_bytes,
        )
        return art

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
