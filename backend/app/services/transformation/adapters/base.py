"""Base abstraction for deterministic native output adapters (Phase D6.3).

All native adapters inherit from BaseNativeAdapter:
- Output is strictly derived from CanonicalContent (no new factual claims).
- Preserves source and evidence references.
- Persists physical file atomically via StorageService.
- Registers real Artifact record via ArtifactService.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging
from typing import Any, Dict, Optional

from ....core.ids import generate_artifact_id
from ....models.artifact import Artifact
from ....models.content import CanonicalContent
from ....models.enums import ArtifactType
from ....models.generation_config import GenerationConfig
from ....models.transformation import PlannedDeliverable
from ....services.artifact_service import ArtifactService, artifact_service
from ....storage.service import StorageService, storage_service

import re

logger = logging.getLogger("limo.services.transformation.adapters.base")


def make_slug(title: str, fallback: str = "deliverable") -> str:
    """Sanitize deliverable title into a safe filename slug."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", title).strip("_") or fallback


@dataclass
class GeneratedContent:
    """In-memory synthesized deliverable content produced by a native adapter."""
    content_bytes: bytes
    filename: str
    file_format: str
    artifact_type: ArtifactType
    stats: str
    metadata: Dict[str, Any]


class BaseNativeAdapter(ABC):
    """Abstract base class for in-process deterministic deliverable generation."""

    def __init__(
        self,
        storage: Optional[StorageService] = None,
        artifact_svc: Optional[ArtifactService] = None,
    ):
        self.storage = storage or storage_service
        self.artifact_svc = artifact_svc or artifact_service

    @abstractmethod
    def synthesize(
        self,
        canonical: CanonicalContent,
        deliverable: PlannedDeliverable,
        config: GenerationConfig,
    ) -> GeneratedContent:
        """Synthesize deliverable bytes deterministically from CanonicalContent.

        Guarantees:
        - Strictly derived from CanonicalContent.
        - Introduces no new ungrounded factual claims.
        - Retains citations and evidence references.
        """
        raise NotImplementedError

    def execute(
        self,
        canonical: CanonicalContent,
        deliverable: PlannedDeliverable,
        config: GenerationConfig,
        project_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> Artifact:
        """Synthesize content, write physical file to storage, and register Artifact record."""
        # 1. Synthesize deliverable content
        gen = self.synthesize(canonical, deliverable, config)

        # 2. Generate artifact ID and write physical file
        art_id = generate_artifact_id()
        storage_ref, size_bytes, file_hash = self.storage.save_artifact_file(
            artifact_id=art_id,
            filename=gen.filename,
            content=gen.content_bytes,
        )

        # 3. Merge provenance and deliverable metadata
        meta = dict(gen.metadata)
        meta["canonical_id"] = canonical.id
        meta["canonical_hash"] = canonical.content_hash
        meta["deliverable_id"] = deliverable.deliverable_id
        meta["format"] = deliverable.format.value
        meta["generator"] = self.__class__.__name__

        # 3.5 Generate and persist thumbnail preview for native deliverables
        try:
            from PIL import Image, ImageDraw
            import io
            thumb_img = Image.new("RGB", (600, 800), color=(15, 23, 42))
            draw = ImageDraw.Draw(thumb_img)
            draw.rectangle([(20, 20), (580, 780)], outline=(51, 65, 85), width=2)
            draw.text((40, 40), "LIMO NATIVE DELIVERABLE", fill=(56, 189, 248))
            draw.text((40, 70), deliverable.title[:35], fill=(248, 250, 252))
            draw.text((40, 105), f"Format: {gen.file_format.upper()} | {size_bytes:,} bytes", fill=(148, 163, 184))
            draw.line([(40, 130), (560, 130)], fill=(51, 65, 85), width=1)

            preview_lines = gen.content_bytes.decode("utf-8", errors="ignore").split("\n")[:18]
            y = 150
            for line in preview_lines:
                if y > 740:
                    break
                clean_l = line.strip()[:50]
                if clean_l.startswith("#"):
                    draw.text((40, y), clean_l, fill=(56, 189, 248))
                elif clean_l.startswith("|"):
                    draw.text((40, y), clean_l, fill=(16, 185, 129))
                elif clean_l.startswith(">"):
                    draw.text((40, y), clean_l, fill=(245, 158, 11))
                else:
                    draw.text((40, y), clean_l, fill=(203, 213, 225))
                y += 28

            buf = io.BytesIO()
            thumb_img.save(buf, format="PNG")
            thumb_bytes = buf.getvalue()
            thumb_ref, _, _ = self.storage.save_artifact_file(
                artifact_id=art_id,
                filename="thumbnail.png",
                content=thumb_bytes,
            )
            meta["thumbnail_storage_ref"] = thumb_ref
        except Exception as e:
            logger.warning("Could not generate thumbnail for native artifact: %s", e)

        # 4. Register real Artifact in SQLite repository
        artifact = self.artifact_svc.register_artifact(
            title=deliverable.title,
            artifact_type=gen.artifact_type,
            file_format=gen.file_format,
            storage_ref=storage_ref,
            project_id=project_id,
            job_id=job_id,
            description=f"Generated {deliverable.format.value} deliverable from '{canonical.title}'",
            stats=gen.stats,
            metadata=meta,
            artifact_id=art_id,
        )

        logger.info(
            "Native adapter '%s' created artifact '%s' (format: %s, bytes: %d, sha: %s)",
            self.__class__.__name__,
            artifact.id,
            gen.file_format,
            size_bytes,
            file_hash[:8],
        )
        return artifact
