"""GenOffice Native Office Adapter (Phase D7).

Bridges PlannedDeliverable -> GenOfficeAutomationClient -> JobArtifactHandoffService.
Generates verified .docx, .pptx, .xlsx, .pdf documents with thumbnail previews.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from ....models.artifact import Artifact
from ....models.content import CanonicalContent
from ....models.enums import OutputFormat
from ....models.generation_config import GenerationConfig
from ....models.transformation import PlannedDeliverable

if TYPE_CHECKING:
    from ....agent.context import UnifiedInputContext
from ..genoffice_client import GenOfficeAutomationClient, genoffice_client
from ..handoff import JobArtifactHandoffService, job_artifact_handoff_service

logger = logging.getLogger("limo.services.transformation.adapters.genoffice")


class GenOfficeAdapter:
    """Transformation adapter executing Office document generation via GenOffice automation client."""

    def __init__(
        self,
        client: Optional[GenOfficeAutomationClient] = None,
        handoff_svc: Optional[JobArtifactHandoffService] = None,
    ) -> None:
        self.client = client or genoffice_client
        self.handoff = handoff_svc or job_artifact_handoff_service

    def execute(
        self,
        canonical: Optional[CanonicalContent] = None,
        deliverable: Optional[PlannedDeliverable] = None,
        config: Optional[GenerationConfig] = None,
        project_id: Optional[str] = None,
        job_id: Optional[str] = None,
        unified_input: Optional[UnifiedInputContext] = None,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> Artifact:
        """Execute GenOffice document generation and return registered Artifact."""
        title = deliverable.title if deliverable else "Office Document"
        opts = (deliverable.options if deliverable else {}) or {}

        # Resolve format string
        fmt = deliverable.format if deliverable else OutputFormat.DOCUMENT
        if fmt == OutputFormat.PRESENTATION:
            format_str = "presentation"
        elif fmt == OutputFormat.SPREADSHEET:
            format_str = "spreadsheet"
        elif fmt == OutputFormat.PDF:
            format_str = "pdf"
        else:
            format_str = "document"

        # Build prompt
        user_directive = opts.get("user_directive") or (unified_input.user_instruction if unified_input else "")
        if not user_directive and canonical and canonical.intent:
            user_directive = canonical.intent.core_narrative

        prompt = user_directive or f"Create a comprehensive {format_str} on: {title}"

        # Ground in canonical content (facts)
        if canonical and canonical.facts:
            fact_snippets = [f.claim for f in canonical.facts[:5] if hasattr(f, "claim")]
            if fact_snippets:
                prompt = f"{prompt}\nKey facts to include: {'; '.join(fact_snippets)}"

        if progress_callback:
            progress_callback("genoffice_dispatch", f"Submitting {format_str} job to GenOffice...")

        artifact = self.client.generate_and_handoff(
            format=format_str,
            prompt=prompt,
            title=title,
            project_id=project_id,
            session_id=job_id,
        )

        if progress_callback:
            progress_callback("completed", f"GenOffice artifact generated: {artifact.title}")

        return artifact
