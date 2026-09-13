"""Output Planner for deliverable generation workflows (Phase D6.2).

Decomposes a validated TransformationRequest into discrete PlannedDeliverables,
assigns designated engine routes, extracts format-specific options, and
assembles the execution OutputPlan manifest.

Preserves the boundary: D6.2 is 100% deterministic planning.
Zero fake artifacts are generated.
"""

import logging
from typing import Dict, List, Optional

from ...models.enums import OutputFormat
from ...models.transformation import (
    EngineRoute,
    OutputPlan,
    PlannedDeliverable,
    TransformationRequest,
)
from .engine_router import EngineRouter, engine_router

logger = logging.getLogger("limo.services.transformation.output_planner")


class OutputPlanner:
    """Deterministic output planner assembling the multi-deliverable OutputPlan manifest."""

    def __init__(self, router: Optional[EngineRouter] = None) -> None:
        self.router = router or engine_router

    def plan(
        self,
        request: TransformationRequest,
        canonical_title: Optional[str] = None,
    ) -> OutputPlan:
        """Decompose request into planned deliverables and compile OutputPlan."""
        deliverables: List[PlannedDeliverable] = []
        routes_map: Dict[OutputFormat, EngineRoute] = {}

        for fmt in request.requested_formats:
            route = self.router.get_route(fmt)
            routes_map[fmt] = route

            clean_title = self._derive_deliverable_title(
                fmt=fmt,
                canonical_title=canonical_title,
                user_prompt=request.user_prompt,
            )

            typed_options = request.config.get_options_for_format(fmt)
            options_dict = typed_options.model_dump()

            # Merge any specific format_overrides if present
            if request.config.format_overrides and fmt.value in request.config.format_overrides:
                override_dict = request.config.format_overrides[fmt.value]
                if isinstance(override_dict, dict):
                    options_dict.update(override_dict)

            deliverable = PlannedDeliverable(
                format=fmt,
                title=clean_title,
                route=route,
                options=options_dict,
            )
            deliverables.append(deliverable)

        all_engines_available = all(d.route.is_implemented for d in deliverables)

        plan = OutputPlan(
            request_id=request.id,
            canonical_id=request.canonical_id,
            canonical_hash=request.canonical_hash,
            deliverables=deliverables,
            routes=routes_map,
            all_engines_available=all_engines_available,
        )

        logger.info(
            "Created OutputPlan '%s' for request '%s' with %d deliverables (all_engines_available: %s)",
            plan.id,
            request.id,
            len(deliverables),
            all_engines_available,
        )
        return plan

    @staticmethod
    def _derive_deliverable_title(
        fmt: OutputFormat,
        canonical_title: Optional[str],
        user_prompt: Optional[str],
    ) -> str:
        """Construct a clean, human-readable deliverable title."""
        format_label = fmt.value.capitalize()
        if canonical_title and canonical_title.strip():
            return f"{canonical_title.strip()} - {format_label}"
        if user_prompt and user_prompt.strip():
            prompt_snip = user_prompt.strip()[:40].rstrip()
            return f"{prompt_snip} ({format_label})"
        return f"{format_label} Deliverable"


output_planner = OutputPlanner()
