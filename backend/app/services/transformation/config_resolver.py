"""Transformation Configuration Resolver (Phase D6.1).

Performs pure deterministic reconciliation between:
1. Structured user/agent overrides from D4 Agent tool calls (highest precedence)
2. Grounded intent and target audiences from D5 CanonicalContent (baseline)
3. Standard system defaults from GenerationConfig

Contains ZERO natural language processing or heuristics.
Consumes already-extracted CanonicalContent without touching raw files.
"""

import logging
from typing import List, Optional

from ...exceptions import BadRequestError
from ...models.content import CanonicalContent
from ...models.enums import CommunicationObjective, FeatureMode, OutputFormat
from ...models.generation_config import GenerationConfig
from ...models.transformation import TransformationRequest

logger = logging.getLogger("limo.services.transformation.config_resolver")


class TransformationConfigResolver:
    """Pure deterministic reconciler for deliverable transformation configuration."""

    def resolve(
        self,
        canonical: CanonicalContent,
        structured_overrides: Optional[GenerationConfig] = None,
        requested_formats: Optional[List[OutputFormat]] = None,
        active_mode: Optional[FeatureMode] = None,
        user_prompt: Optional[str] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> TransformationRequest:
        """Deterministically reconcile transformation configuration against CanonicalContent."""
        if not canonical:
            raise BadRequestError("CanonicalContent is required for transformation planning")

        # 1. Deterministic Format Resolution
        formats = self._resolve_formats(requested_formats, active_mode)

        # 2. Editorial Posture Reconciliation
        base_cfg = structured_overrides.model_copy() if structured_overrides else GenerationConfig()

        # Enforce language code validation
        if base_cfg.language:
            clean_lang = base_cfg.language.strip()
            if not (2 <= len(clean_lang) <= 8 and all(c.isalnum() or c in "-_" for c in clean_lang)):
                raise BadRequestError(f"Invalid ISO language code '{base_cfg.language}'")
            base_cfg.language = clean_lang

        # Reconcile Audience:
        # Precedence: Structured override (if non-default) > Canonical target_audiences > Default
        audience = base_cfg.audience
        if (structured_overrides is None or structured_overrides.audience == "Executive") and canonical.intent and canonical.intent.target_audiences:
            audience = canonical.intent.target_audiences[0]

        # Reconcile Objective:
        # Precedence: Structured override (if non-default) > Canonical purpose mapping > Default
        objective = base_cfg.objective
        if (structured_overrides is None or structured_overrides.objective == CommunicationObjective.INFORM) and canonical.intent and canonical.intent.primary_purpose:
            mapped_obj = self._map_purpose_to_objective(canonical.intent.primary_purpose)
            if mapped_obj:
                objective = mapped_obj

        reconciled_config = base_cfg.model_copy(
            update={
                "audience": audience,
                "objective": objective,
            }
        )

        logger.debug(
            "Resolved transformation request for canonical '%s' (formats: %s, audience: '%s', objective: '%s')",
            canonical.id,
            [f.value for f in formats],
            audience,
            objective.value,
        )

        return TransformationRequest(
            project_id=project_id,
            session_id=session_id,
            canonical_id=canonical.id,
            canonical_hash=canonical.content_hash,
            requested_formats=formats,
            config=reconciled_config,
            user_prompt=user_prompt.strip() if user_prompt else None,
        )

    def _resolve_formats(
        self,
        requested_formats: Optional[List[OutputFormat]],
        active_mode: Optional[FeatureMode],
    ) -> List[OutputFormat]:
        """Map explicit requested formats or conversational FeatureMode into OutputFormats."""
        if requested_formats:
            cleaned = list(dict.fromkeys(requested_formats))
            if cleaned:
                return cleaned

        if active_mode:
            mode_map = {
                FeatureMode.SLIDES: [OutputFormat.PRESENTATION],
                FeatureMode.SHEETS: [OutputFormat.SPREADSHEET],
                FeatureMode.DOCS: [OutputFormat.DOCUMENT],
                FeatureMode.VIDEO: [OutputFormat.VIDEO],
            }
            if active_mode in mode_map:
                return mode_map[active_mode]

        return [OutputFormat.DOCUMENT]

    @staticmethod
    def _map_purpose_to_objective(purpose: str) -> Optional[CommunicationObjective]:
        """Deterministically map canonical primary purpose text to CommunicationObjective."""
        p = purpose.lower()
        if any(w in p for w in ("alert", "warn", "threat", "breach", "incident", "vulnerability", "exploit", "ciso")):
            return CommunicationObjective.ALERT
        if any(w in p for w in ("persuade", "pitch", "convince", "proposal", "recommend")):
            return CommunicationObjective.PERSUADE
        if any(w in p for w in ("educate", "teach", "explain", "training", "guide")):
            return CommunicationObjective.EDUCATE
        if any(w in p for w in ("synthesize", "aggregate", "integrate", "reconcile")):
            return CommunicationObjective.SYNTHESIZE
        return CommunicationObjective.INFORM


transformation_config_resolver = TransformationConfigResolver()
