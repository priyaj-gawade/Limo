"""Deterministic native infographic adapter generating valid vector SVG diagrams (Phase D6.3).

Synthesizes standalone executive infographic cards strictly derived from CanonicalContent:
- ViewBox: 1200 x 800
- Valid SVG XML markup
- Formatted KPI stat counters, grounded findings, entity badges, and SHA-256 provenance footer
"""

import html
import re
from typing import List

from ....models.content import CanonicalContent
from ....models.enums import ArtifactType
from ....models.generation_config import GenerationConfig
from ....models.transformation import PlannedDeliverable
from .base import BaseNativeAdapter, GeneratedContent, make_slug


class NativeInfographicAdapter(BaseNativeAdapter):
    """Deterministic native adapter generating standalone vector SVG infographics."""

    def synthesize(
        self,
        canonical: CanonicalContent,
        deliverable: PlannedDeliverable,
        config: GenerationConfig,
    ) -> GeneratedContent:
        safe_title = html.escape(deliverable.title[:55])
        safe_narrative = html.escape(canonical.intent.core_narrative[:120])
        hash_preview = canonical.content_hash[:16] + "..."

        # Generate KPI Metric Cards (Up to 3 cards)
        metric_cards_svg: List[str] = []
        card_width = 340
        card_height = 140
        card_y = 170

        data_points = canonical.data_points[:3]
        if not data_points:
            # Fallback cards if no explicit metrics exist
            data_points_dummy = [
                ("Key Assertions", str(len(canonical.facts)), "Grounded Facts"),
                ("Domain Entities", str(len(canonical.entities)), "Classified Entities"),
                ("Recommendations", str(len(canonical.recommendations)), "Strategic Actions"),
            ]
            for idx, (label, val, ctx) in enumerate(data_points_dummy):
                card_x = 60 + idx * (card_width + 30)
                metric_cards_svg.append(self._render_kpi_card(card_x, card_y, card_width, card_height, val, label, ctx))
        else:
            for idx, dp in enumerate(data_points):
                card_x = 60 + idx * (card_width + 30)
                val_str = f"{dp.value} {dp.unit or ''}".strip()
                metric_cards_svg.append(
                    self._render_kpi_card(card_x, card_y, card_width, card_height, val_str, dp.metric, dp.context or "")
                )

        # Generate Grounded Findings Section (Left Column)
        facts_svg: List[str] = []
        fact_y = 360
        for f in canonical.facts[:4]:
            safe_stmt = html.escape(f.statement[:75] + ("..." if len(f.statement) > 75 else ""))
            facts_svg.append(
                f'<circle cx="80" cy="{fact_y}" r="5" fill="#38bdf8"/>'
                f'<text x="95" y="{fact_y + 4}" fill="#f8fafc" font-size="14" font-family="system-ui, sans-serif">{safe_stmt}</text>'
            )
            fact_y += 36

        # Generate Recommendations Section (Right Column)
        recs_svg: List[str] = []
        rec_y = 360
        for r in canonical.recommendations[:4]:
            safe_rec = html.escape(r[:70] + ("..." if len(r) > 70 else ""))
            recs_svg.append(
                f'<circle cx="620" cy="{rec_y}" r="5" fill="#10b981"/>'
                f'<text x="635" y="{rec_y + 4}" fill="#f8fafc" font-size="14" font-family="system-ui, sans-serif">{safe_rec}</text>'
            )
            rec_y += 36

        # Generate Entity Badges
        entity_badges_svg: List[str] = []
        badge_x = 60
        badge_y = 570
        for ent in canonical.entities[:6]:
            safe_name = html.escape(ent.name[:20])
            badge_width = max(80, len(safe_name) * 9 + 20)
            entity_badges_svg.append(
                f'<rect x="{badge_x}" y="{badge_y}" width="{badge_width}" height="28" rx="14" fill="#334155"/>'
                f'<text x="{badge_x + badge_width // 2}" y="{badge_y + 18}" fill="#94a3b8" font-size="12" font-family="system-ui, sans-serif" text-anchor="middle">{safe_name}</text>'
            )
            badge_x += badge_width + 12

        svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 800" width="1200" height="800">
  <defs>
    <linearGradient id="bg-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#1e293b"/>
    </linearGradient>
    <linearGradient id="primary-grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#818cf8"/>
    </linearGradient>
  </defs>

  <!-- Background -->
  <rect width="1200" height="800" fill="url(#bg-grad)"/>

  <!-- Top Header Card -->
  <rect x="40" y="30" width="1120" height="110" rx="16" fill="#1e293b" stroke="#334155" stroke-width="1.5"/>
  <text x="70" y="75" fill="url(#primary-grad)" font-size="28" font-weight="bold" font-family="system-ui, sans-serif">{safe_title}</text>
  <text x="70" y="110" fill="#94a3b8" font-size="15" font-family="system-ui, sans-serif">{safe_narrative}</text>

  <!-- KPI Metric Cards -->
  {"".join(metric_cards_svg)}

  <!-- Findings Container Card (Left) -->
  <rect x="40" y="330" width="540" height="200" rx="12" fill="#1e293b" stroke="#334155" stroke-width="1"/>
  <text x="70" y="360" fill="#38bdf8" font-size="16" font-weight="bold" font-family="system-ui, sans-serif">CRITICAL FINDINGS</text>
  {"".join(facts_svg)}

  <!-- Recommendations Container Card (Right) -->
  <rect x="600" y="330" width="560" height="200" rx="12" fill="#1e293b" stroke="#334155" stroke-width="1"/>
  <text x="630" y="360" fill="#10b981" font-size="16" font-weight="bold" font-family="system-ui, sans-serif">STRATEGIC ACTIONS</text>
  {"".join(recs_svg)}

  <!-- Entity Badges Section -->
  <text x="60" y="560" fill="#94a3b8" font-size="13" font-weight="bold" font-family="system-ui, sans-serif">IDENTIFIED ENTITIES</text>
  {"".join(entity_badges_svg)}

  <!-- Footer Banner / Provenance Digest -->
  <rect x="40" y="660" width="1120" height="90" rx="12" fill="#0f172a" stroke="#334155" stroke-width="1"/>
  <text x="70" y="700" fill="#94a3b8" font-size="13" font-family="system-ui, sans-serif">PROVENANCE VERIFICATION</text>
  <text x="70" y="725" fill="#38bdf8" font-size="12" font-family="monospace, sans-serif">SHA-256: {canonical.content_hash}</text>
  <text x="1000" y="715" fill="#10b981" font-size="13" font-weight="bold" font-family="system-ui, sans-serif" text-anchor="end">GROUNDED IN CANONICAL CONTENT</text>
</svg>"""

        raw_bytes = svg_content.encode("utf-8")
        clean_slug = make_slug(deliverable.title, fallback="infographic")
        filename = f"{clean_slug}.svg"

        stats = "1200x800 • Vector SVG Infographic"

        return GeneratedContent(
            content_bytes=raw_bytes,
            filename=filename,
            file_format=".svg",
            artifact_type=ArtifactType.INFOGRAPHIC,
            stats=stats,
            metadata={"format": "svg", "viewBox": "0 0 1200 800", "size_bytes": len(raw_bytes)},
        )

    @staticmethod
    def _render_kpi_card(x: int, y: int, w: int, h: int, value: str, label: str, context: str) -> str:
        safe_val = html.escape(value[:15])
        safe_lbl = html.escape(label[:28])
        safe_ctx = html.escape(context[:35])
        return (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="#1e293b" stroke="#334155" stroke-width="1"/>'
            f'<text x="{x + 20}" y="{y + 45}" fill="#38bdf8" font-size="28" font-weight="bold" font-family="system-ui, sans-serif">{safe_val}</text>'
            f'<text x="{x + 20}" y="{y + 80}" fill="#f8fafc" font-size="14" font-weight="600" font-family="system-ui, sans-serif">{safe_lbl}</text>'
            f'<text x="{x + 20}" y="{y + 110}" fill="#94a3b8" font-size="12" font-family="system-ui, sans-serif">{safe_ctx}</text>'
        )
