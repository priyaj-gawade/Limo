"""OpenMontage Video Deliverable Adapter (Phase D8.2).

Integrates the frozen OpenMontage isolated runner into Limo's D6 engine routing
and transformation workflow:
- Maps CanonicalContent + PlannedDeliverable + VideoOptions into VideoGenerationContract.
- Invokes OpenMontageSubprocessClient across the isolated process boundary.
- Streams safe stage progress events ("Preparing video", "Planning scenes", etc.).
- Hands off verified output to JobArtifactHandoffService for storage ingestion and job linkage.
- Zero direct Python imports of OpenMontage modules in Limo backend.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ....exceptions import BadRequestError, StorageError
from ....models.artifact import Artifact
from ....models.content import CanonicalContent
from ....models.enums import OutputFormat
from ....models.generation_config import GenerationConfig
from ....models.transformation import PlannedDeliverable
from ..contracts import GenerationContractBuilder, generation_contract_builder
from ..event_broker import TransformationEventBroker, event_broker
from ..handoff import JobArtifactHandoffService, job_artifact_handoff_service
from ..openmontage_client import (
    OpenMontageClient,
    OpenMontageExecutionError,
    OpenMontageTimeoutError,
    openmontage_client,
)

logger = logging.getLogger("limo.services.transformation.adapters.video")

# Safe user-facing stage summaries (no private CoT, no internal paths)
STAGE_DISPLAY_MAP: Dict[str, str] = {
    "workspace_init": "Preparing video",
    "script_planning": "Planning scenes",
    "narration_generation": "Generating narration",
    "caption_generation": "Aligning captions",
    "asset_acquisition": "Collecting visuals",
    "video_composition": "Rendering video",
    "output_validation": "Finalizing video",
}


class OpenMontageVideoAdapter:
    """Transformation adapter executing video generation via OpenMontage isolated subprocess."""

    def __init__(
        self,
        client: Optional[OpenMontageClient] = None,
        handoff_svc: Optional[JobArtifactHandoffService] = None,
        contract_bld: Optional[GenerationContractBuilder] = None,
        broker: Optional[TransformationEventBroker] = None,
    ) -> None:
        self.client = client or openmontage_client
        self.handoff = handoff_svc or job_artifact_handoff_service
        self.contract_builder = contract_bld or generation_contract_builder
        self.event_broker = broker or event_broker

    def execute(
        self,
        canonical: CanonicalContent,
        deliverable: PlannedDeliverable,
        config: GenerationConfig,
        project_id: Optional[str] = None,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> Artifact:
        """Execute video generation workflow and return registered Artifact.

        Flow:
        1. Compile strongly-typed VideoGenerationContract.
        2. Execute via isolated OpenMontage runner subprocess.
        3. Stream sanitized stage progress events.
        4. Ingest and persist real MP4 via JobArtifactHandoffService.
        5. Return registered Artifact entity linked to job.
        """
        resolved_job_id = job_id or f"job_video_{deliverable.deliverable_id}"

        # 1. Build authoritative contract
        contract_model = self.contract_builder.build_video_generation_contract(
            canonical=canonical,
            deliverable=deliverable,
            config=config,
            job_id=resolved_job_id,
            conversation_id=project_id,
        )
        contract_dict = contract_model.model_dump(mode="json")

        logger.info(
            "Dispatching video deliverable '%s' (job: %s, duration: %.1fs, format: %s)",
            deliverable.title,
            resolved_job_id,
            contract_model.target_duration_seconds,
            contract_model.aspect_ratio,
        )

        # 2. Run cheap in-memory preflight quality gate check (<3s)
        logger.info("Running preflight script planning & quality check for '%s'...", deliverable.title)
        preflight_res = self.client.run_preflight(contract=contract_dict, timeout_seconds=30.0)
        if preflight_res.get("status") != "READY":
            err_msg = preflight_res.get("error", "Script quality gate blocked video generation")
            logger.error("Preflight quality check blocked generation for job %s: %s", resolved_job_id, err_msg)
            if job_id:
                try:
                    self.handoff.on_task_failed(
                        job_id=job_id,
                        deliverable_id=deliverable.deliverable_id,
                        format_val=OutputFormat.VIDEO.value,
                        error_msg=f"Video script validation failed: {err_msg}",
                    )
                except Exception as ex:
                    logger.warning("Failed to emit task.failed event: %s", ex)
            raise BadRequestError(f"Video script generation rejected by quality gate: {err_msg}")

        # 3. Stage progress callback wrapper
        def _on_stage_progress(stage_name: str, message: str) -> None:
            display_label = STAGE_DISPLAY_MAP.get(stage_name, message)
            if job_id:
                try:
                    self.handoff.on_task_progress(
                        job_id=job_id,
                        deliverable_id=deliverable.deliverable_id,
                        format_val=OutputFormat.VIDEO.value,
                        stage=stage_name,
                        message=display_label,
                    )
                except Exception as ex:
                    logger.warning("Failed to emit task.progress event: %s", ex)
            if progress_callback:
                try:
                    progress_callback(stage_name, display_label)
                except Exception:
                    pass

        # 3. Invoke OpenMontage isolated runner subprocess
        timeout_sec = 360.0
        try:
            result = self.client.run_contract(
                contract=contract_dict,
                timeout_seconds=timeout_sec,
                progress_callback=_on_stage_progress,
            )
        except OpenMontageTimeoutError as exc:
            logger.error("OpenMontage execution timed out: %s", exc)
            raise BadRequestError(f"Video generation timed out after {timeout_sec} seconds") from exc
        except OpenMontageExecutionError as exc:
            logger.error("OpenMontage execution error: %s (code: %s)", exc, exc.code)
            safe_msg = self._sanitize_runner_error(exc)
            raise BadRequestError(safe_msg) from exc
        except Exception as exc:
            logger.exception("Unexpected error during video generation dispatch: %s", exc)
            raise BadRequestError("Video generation subprocess encountered an unexpected error") from exc

        if not result or not result.get("success"):
            err_info = (result or {}).get("error", {})
            err_msg = err_info.get("message", "Video runner returned unsuccessful status")
            raise BadRequestError(f"Video generation failed: {err_msg}")

        # 4. Handoff output MP4 to D7 storage & artifact pipeline
        artifact = self.handoff.handoff_video_artifact(
            job_id=resolved_job_id,
            deliverable_id=deliverable.deliverable_id,
            openmontage_result=result,
            title=deliverable.title,
            canonical_id=canonical.id,
            canonical_hash=canonical.content_hash,
            project_id=project_id,
        )

        logger.info(
            "Video generation completed for deliverable '%s': artifact_id=%s, storage_ref=%s",
            deliverable.title,
            artifact.id,
            artifact.storage_ref,
        )
        return artifact

    @staticmethod
    def _sanitize_runner_error(exc: OpenMontageExecutionError) -> str:
        """Map runner failures to sanitized user-facing error strings without secret leakage."""
        err_msg = str(exc)
        code = getattr(exc, "code", "")

        if code == "RUNNER_NOT_FOUND":
            return "Video generation runner component is not installed or available"
        elif code == "RUNNER_TIMEOUT":
            return "Video generation exceeded maximum allowed execution time"
        elif code == "CONFIGURATION_ERROR" or "key" in err_msg.lower():
            return "Video generation engine configuration or provider credentials unavailable"
        elif code == "MEDIA_NOT_FOUND":
            return "Visual asset acquisition could not find matching media for prompt"
        elif "tts" in err_msg.lower() or "voice" in err_msg.lower():
            return "Narration generation failed with selected voice profile"
        elif "ffmpeg" in err_msg.lower() or "composition" in err_msg.lower():
            return "Video composition engine encountered a rendering failure"
        else:
            return "Video generation pipeline failed to produce a valid MP4 deliverable"
