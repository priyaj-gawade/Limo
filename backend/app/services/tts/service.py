"""Standalone Text-to-Speech Generation Service (Phase D8.3)."""

import logging
from pathlib import Path
import re
import time
from typing import Any, Dict, Optional

from ...core.ids import generate_artifact_id
from ...exceptions import StorageError
from ...models.artifact import Artifact
from ...models.enums import ArtifactType, ValidationStatus
from ...storage.service import storage_service
from ..artifact_service import artifact_service
from .models import TTSRequest, TTSResult
from .registry import TTSProviderRegistry, tts_registry

logger = logging.getLogger("limo.services.tts.service")


class TTSService:
    """Service managing standalone audio narration synthesis and artifact registration."""

    def __init__(
        self,
        registry: Optional[TTSProviderRegistry] = None,
    ) -> None:
        self.registry = registry or tts_registry

    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        provider: Optional[str] = None,
        speed: float = 1.0,
        output_format: str = "mp3",
        title: Optional[str] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        job_id: Optional[str] = None,
        provider_options: Optional[Dict[str, Any]] = None,
    ) -> Artifact:
        """Synthesize narration text into a real audio deliverable artifact.
        
        Guarantees:
        1. Resolves provider and voice deterministically (no silent fallback to wrong voice).
        2. Generates real audio file inside sandboxed Limo storage boundaries.
        3. Probes real duration and computes SHA-256 digest.
        4. Registers and returns an official Artifact entity (ArtifactType.AUDIO).
        """
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Narration text cannot be empty.")

        # 1. Deterministic voice resolution
        provider_adapter, voice_meta = self.registry.resolve_voice(voice_id=voice, provider=provider)

        # 2. Derive clean title and artifact container
        container = (output_format or "mp3").lower().lstrip(".")
        if container not in ("mp3", "wav"):
            container = "mp3"

        art_id = generate_artifact_id()
        raw_title = title or f"Narration_{voice_meta.display_name}"
        clean_title = re.sub(r"[^\w\s-]", "", raw_title).strip()
        clean_title = "_".join(w.capitalize() for w in clean_title.split())[:45]
        if not clean_title:
            clean_title = f"Narration_{int(time.time())}"

        filename = f"{clean_title}.{container}"
        storage_ref = f"artifacts/{art_id}/{filename}"
        disk_path = storage_service.safe_resolve(storage_ref)
        disk_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            "Executing standalone TTS synthesis for '%s' via %s (voice: %s, speed: %.2f)",
            clean_title,
            provider_adapter.id,
            voice_meta.voice_id,
            speed,
        )

        # 3. Real synthesis via resolved provider
        req = TTSRequest(
            text=clean_text,
            voice=voice_meta.voice_id,
            provider=provider_adapter.id,
            speed=speed,
            output_format=container,
            output_path=disk_path,
            provider_options=provider_options or {},
        )
        res: TTSResult = provider_adapter.synthesize(req)

        # 4. Format audio stats string (e.g. 'MP3 • 00:14 • 48 kHz')
        dur_str = "00:00"
        if res.duration_seconds is not None:
            mins = int(res.duration_seconds // 60)
            secs = int(res.duration_seconds % 60)
            dur_str = f"{mins:02d}:{secs:02d}"

        stats = f"{container.upper()} • {dur_str}"
        description = f"Generated speech narration with voice '{voice_meta.display_name}' via {provider_adapter.name}"

        # 5. Ingest into Limo artifact repository
        effective_project_id = None
        if project_id:
            try:
                from ...db.connection import get_connection
                from ...db.repositories.project_repo import ProjectRepository
                with get_connection(artifact_service.db_path) as conn:
                    if ProjectRepository.get_project(conn, project_id):
                        effective_project_id = project_id
            except Exception:
                effective_project_id = None

        registered = artifact_service.register_artifact(
            title=clean_title,
            artifact_type=ArtifactType.AUDIO,
            file_format=f".{container}",
            storage_ref=storage_ref,
            project_id=effective_project_id,
            job_id=job_id,
            description=description,
            stats=stats,
            metadata={
                "provider": provider_adapter.id,
                "voice_id": voice_meta.voice_id,
                "voice_name": voice_meta.display_name,
                "duration_seconds": res.duration_seconds,
                "speed": speed,
                "engine": "limo_tts",
                "session_id": session_id,
                "sha256": res.sha256,
            },
            artifact_id=art_id,
        )
        logger.info("Registered standalone audio artifact '%s' (ID: %s, duration: %s)", clean_title, art_id, dur_str)
        return registered


tts_service = TTSService()
