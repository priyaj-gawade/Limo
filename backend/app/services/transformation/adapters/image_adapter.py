"""Prismo Graphic Poster & Infographic Adapter (Phase D8.8).

Integrates the headless Prismo design engine into Limo's transformation and delivery pipeline:
- Consumes UnifiedInputContext preserving structured canonical facts, metrics, and native media.
- Enforces canonical aspect ratios (3:4, 9:16, 16:9, 1:1, 4:3) with zero silent coercion.
- Dispatches execution to the isolated Prismo subprocess client.
- Ingests verified, cryptographically hashed PNG deliverables into sandboxed storage.
- Hands off registered Artifact entities to Limo chat.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from ....exceptions import BadRequestError, StorageError
from ....models.artifact import Artifact
from ....models.content import CanonicalContent
from ....models.enums import OutputFormat
from ....models.generation_config import GenerationConfig
from ....models.transformation import PlannedDeliverable

if TYPE_CHECKING:
    from ....agent.context import UnifiedInputContext
from ..handoff import JobArtifactHandoffService, job_artifact_handoff_service
from ..prismo_client import (
    PrismoClient,
    PrismoExecutionError,
    PrismoTimeoutError,
    prismo_client,
)

logger = logging.getLogger("limo.services.transformation.adapters.image")

SUPPORTED_PRISMO_RATIOS = {"3:4", "9:16", "16:9", "1:1", "4:3"}


class PrismoImageAdapter:
    """Transformation adapter executing poster & infographic generation via Prismo isolated runner."""

    def __init__(
        self,
        client: Optional[PrismoClient] = None,
        handoff_svc: Optional[JobArtifactHandoffService] = None,
    ) -> None:
        self.client = client or prismo_client
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
        """Execute poster/infographic design generation and return registered Artifact."""
        deliv_id = deliverable.deliverable_id if deliverable else "deliv_prismo"
        title = deliverable.title if deliverable else "Infographic Poster"
        resolved_job_id = job_id or f"job_prismo_{deliv_id}"

        # 1. Authoritative Aspect Ratio Resolution
        opts = (deliverable.options if deliverable else {}) or {}
        raw_ratio = opts.get("aspect_ratio")
        if not raw_ratio and config and hasattr(config, "format_overrides"):
            raw_ratio = config.format_overrides.get("aspect_ratio")

        target_ratio = "3:4"
        if raw_ratio:
            ratio_clean = str(raw_ratio).strip()
            if ratio_clean not in SUPPORTED_PRISMO_RATIOS:
                raise BadRequestError(
                    f"Unsupported aspect ratio '{ratio_clean}'. Prismo supports: 3:4, 9:16, 16:9, 1:1, and 4:3."
                )
            target_ratio = ratio_clean

        # 2. UnifiedInputContext Mapping
        prompt_parts: List[str] = []
        user_directive = opts.get("user_directive") or (unified_input.user_instruction if unified_input else "")
        if user_directive:
            prompt_parts.append(f"Goal / Directive: {user_directive}")
        else:
            prompt_parts.append(f"Title: {title}")

        # Ground in canonical content (facts + metrics) if available
        active_canonical = canonical
        if not active_canonical and unified_input and unified_input.canonical_contents:
            active_canonical = unified_input.canonical_contents[0]

        if active_canonical:
            if active_canonical.intent and active_canonical.intent.core_narrative:
                prompt_parts.append(f"Core Narrative: {active_canonical.intent.core_narrative}")
            if active_canonical.facts:
                facts_text = "; ".join(f.statement for f in active_canonical.facts[:4] if f.statement)
                if facts_text:
                    prompt_parts.append(f"Key Findings: {facts_text}")
            if active_canonical.data_points:
                metrics_text = "; ".join(
                    f"{dp.metric} = {dp.value} {dp.unit or ''}".strip()
                    for dp in active_canonical.data_points[:5]
                )
                if metrics_text:
                    prompt_parts.append(f"Metrics & Data: {metrics_text}")
        elif unified_input and unified_input.extracted_documents:
            # Fallback to token-budgeted text snippet from extracted document
            doc_text = unified_input.extracted_documents[0].text_content[:1500].strip()
            if doc_text:
                prompt_parts.append(f"Source Context: {doc_text}")

        if unified_input and unified_input.sources and unified_input.sources[0].name:
            prompt_parts.append(f"Attribution Source: {unified_input.sources[0].name}")

        # ── Visual Design Quality Directives ──────────────────────────
        # A1a. Anti-hallucination (Constraint C2)
        has_grounded_data = bool(
            (active_canonical and active_canonical.data_points)
            or (unified_input and unified_input.extracted_documents)
        )

        if has_grounded_data:
            prompt_parts.append(
                "CONTENT INTEGRITY RULE: Use ONLY the specific metrics and data points "
                "provided above. Do NOT invent additional statistics, percentages, or "
                "numeric claims beyond what is supplied in the source context."
            )
        else:
            prompt_parts.append(
                "CONTENT INTEGRITY RULE: This is a generic topic with NO source data. "
                "Use ONLY qualitative, descriptive language. Do NOT include ANY specific "
                "numbers, percentages, statistics, benchmarks, or quantitative claims. "
                "Replace numeric metrics with conceptual descriptions "
                "(e.g., 'Large-scale models' instead of '175B parameters')."
            )

        # A1b. Adaptive Palette — bright ≠ white
        prompt_parts.append(
            "COLOR PALETTE DIRECTIVE: Do NOT default to dark/cyberpunk aesthetics. "
            "For generic topics, prefer bright or visually balanced palettes with strong color "
            "hierarchy. White is optional, not mandatory — bright means luminous, colorful, "
            "high-energy compositions. Consider colorful gradients, pastel color fields, "
            "vivid accents, warm editorial palettes, cool modern palettes, tinted surfaces, "
            "saturated-but-luminous gradients, or other luminous compositions appropriate to "
            "the topic. Gradients (linear, radial, multi-stop) are encouraged when they "
            "improve the composition. Avoid automatically defaulting to dark/cyberpunk "
            "aesthetics or to plain white/grey-on-white layouts."
        )

        # A1c. Adaptive Text Color
        prompt_parts.append(
            "TEXT COLOR DIRECTIVE: Choose text colors dynamically according to the selected "
            "background. For each text element, select color based on the effective background "
            "behind THAT element — not a global rule. Dark text on bright backgrounds, light "
            "text on dark backgrounds, adaptive treatment on gradients/images. Never allow "
            "text to become visually lost against any solid color, gradient, image, translucent "
            "panel, or decorative layer. Use scrims or text surfaces when needed for "
            "image-backed or gradient regions."
        )

        # A1d. Card Alignment & Layout Grid
        prompt_parts.append(
            "LAYOUT GRID DIRECTIVE: All cards, panels, containers, and metric blocks MUST follow "
            "a coherent alignment grid. Parallel cards must share: top edge, bottom edge, widths, "
            "internal padding, corner radius, and spacing. Central/hero elements must align to the "
            "same underlying composition grid. Use CSS Grid or Flexbox with explicit gap values — "
            "do NOT rely on approximate manual positioning."
        )

        # A1e. Text-Fit / Container Safety
        prompt_parts.append(
            "TEXT-FIT RULE: Every text block MUST fit within its parent container boundary. "
            "No text overflow, no clipping, no text extending beyond rounded cards, "
            "no overlap with adjacent components or badges. "
            "If content does not fit: reduce copy, adjust line wrapping, reduce spacing, "
            "or adjust typography. Use CSS overflow: hidden on card containers as a safety net."
        )

        # A1f. Semantic Palette Coherence
        prompt_parts.append(
            "PALETTE COHERENCE RULE: Define a coherent design palette using semantic roles: "
            "background, primary text, secondary text, accent 1, accent 2 (optional), "
            "surface/card, border/divider. Each role may use solid colors, gradients, tints, "
            "or shades. Reuse these palette roles consistently across all components. "
            "The requirement is coherence — not monochrome simplicity."
        )

        composed_prompt = "\n\n".join(prompt_parts)

        # 3. Native Media Reference & Attachment Extraction
        valid_attachments: List[str] = []
        if unified_input:
            # Images from media_references
            for media in unified_input.media_references:
                if media.media_type == "image" and media.file_path:
                    p = Path(media.file_path)
                    if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
                        valid_attachments.append(str(p.resolve()))

            # Local files from attachments
            for att in unified_input.attachments:
                att_path_str = getattr(att, "file_path", None) or getattr(att, "path", None)
                if att_path_str:
                    p = Path(att_path_str)
                    if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
                        p_resolved = str(p.resolve())
                        if p_resolved not in valid_attachments:
                            valid_attachments.append(p_resolved)

        # 4. Compile Runner Contract
        contract = {
            "action": "generate_and_export",
            "projectName": title,
            "prompt": composed_prompt,
            "ratio": target_ratio,
            "attachments": valid_attachments,
            "mockProvider": opts.get("mock_provider", False),
        }

        logger.info(
            "Dispatching Prismo image deliverable '%s' (ratio: %s, attachments: %d, job: %s)",
            title,
            target_ratio,
            len(valid_attachments),
            resolved_job_id,
        )

        # 5. Execute Subprocess
        try:
            result = self.client.run_contract(
                contract=contract,
                timeout_seconds=240.0,
                progress_callback=progress_callback,
            )
        except PrismoTimeoutError as exc:
            logger.error("Prismo execution timed out: %s", exc)
            raise BadRequestError(f"Infographic design generation timed out after 240 seconds") from exc
        except PrismoExecutionError as exc:
            logger.error("Prismo execution error: %s (code: %s)", exc, exc.code)
            if exc.code == "UNSUPPORTED_ASPECT_RATIO":
                raise BadRequestError(str(exc)) from exc
            raise BadRequestError(f"Prismo design engine failed: {exc}") from exc
        except Exception as exc:
            logger.exception("Unexpected error during Prismo generation dispatch: %s", exc)
            raise BadRequestError("Prismo design subprocess encountered an unexpected error") from exc

        # 5b. Post-Export Visual Validation Gate (bounded repair loop)
        MAX_REPAIR_ATTEMPTS = 2
        workspace_project_id = result.get("projectId")
        repair_attempted = 0

        if workspace_project_id and self.client.workspace_dir:
            project_dir = self.client.workspace_dir / workspace_project_id
            html_path = project_dir / "index.html"
            css_path = project_dir / "styles.css"

            while repair_attempted < MAX_REPAIR_ATTEMPTS:
                html_content = ""
                css_content = ""
                try:
                    if html_path.is_file():
                        html_content = html_path.read_text(encoding="utf-8", errors="replace")
                    if css_path.is_file():
                        css_content = css_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    break

                if not html_content:
                    break

                from ..visual_validator import prismo_visual_validator

                validation = prismo_visual_validator.validate(html_content, css_content)

                if validation.passed and not validation.warnings:
                    break

                issues = validation.failures + validation.warnings
                hints = validation.repair_hints
                if not issues:
                    break

                logger.warning(
                    "Visual validation found %d issues for '%s' (attempt %d/%d): %s",
                    len(issues),
                    title,
                    repair_attempted + 1,
                    MAX_REPAIR_ATTEMPTS,
                    "; ".join(issues[:3]),
                )

                repair_instruction = (
                    "Fix the following visual quality issues in the poster:\n"
                    + "\n".join(f"- {issue}" for issue in issues[:5])
                    + "\n\nRepair hints:\n"
                    + "\n".join(f"- {hint}" for hint in hints[:5])
                    + "\n\nIMPORTANT: Maintain the existing design direction and subject matter. "
                    + "Only fix the specific issues listed above."
                )

                refinement_contract = {
                    "action": "refine",
                    "projectId": workspace_project_id,
                    "instruction": repair_instruction,
                    "dataDir": str(self.client.workspace_dir),
                    "bridge": contract.get("bridge"),
                    "mockProvider": contract.get("mockProvider", False),
                }

                try:
                    self.client.run_contract(
                        contract=refinement_contract,
                        timeout_seconds=120.0,
                        progress_callback=progress_callback,
                    )
                except Exception as refine_err:
                    logger.warning(
                        "Repair attempt %d failed for '%s': %s",
                        repair_attempted + 1,
                        title,
                        refine_err,
                    )
                    break

                repair_attempted += 1

            # Re-export if repairs were applied
            if repair_attempted > 0:
                try:
                    re_export_contract = {
                        "action": "export",
                        "projectId": workspace_project_id,
                        "ratio": target_ratio,
                        "dataDir": str(self.client.workspace_dir),
                        "bridge": contract.get("bridge"),
                        "mockProvider": contract.get("mockProvider", False),
                    }
                    result = self.client.run_contract(
                        contract=re_export_contract,
                        timeout_seconds=120.0,
                        progress_callback=progress_callback,
                    )
                    logger.info(
                        "Re-exported after %d repair passes for '%s'",
                        repair_attempted,
                        title,
                    )
                except Exception as re_export_err:
                    logger.warning(
                        "Re-export after repair failed for '%s': %s (using original)",
                        title,
                        re_export_err,
                    )

        # 6. Handoff & Registration
        artifact = self.handoff.handoff_image_artifact(
            job_id=resolved_job_id,
            deliverable_id=deliv_id,
            prismo_result=result,
            title=title,
            canonical_id=active_canonical.id if active_canonical else None,
            canonical_hash=active_canonical.content_hash if active_canonical else None,
            project_id=project_id,
            allowed_workspace_root=self.client.workspace_dir,
        )

        logger.info(
            "Prismo poster deliverable completed: artifact_id=%s, storage_ref=%s, ratio=%s",
            artifact.id,
            artifact.storage_ref,
            target_ratio,
        )
        return artifact
