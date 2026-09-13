"""Deterministic native adapters for Markdown and HTML deliverables (Phase D6.3).

Synthesizes structured documentation strictly derived from CanonicalContent:
- NativeMarkdownAdapter: GitHub-Flavored Markdown document (.md)
- NativeHtmlAdapter: Standalone, responsive HTML5 document with embedded modern CSS (.html)
"""

import html
import re
from typing import List

from ....models.content import CanonicalContent
from ....models.enums import ArtifactType
from ....models.generation_config import GenerationConfig
from ....models.transformation import PlannedDeliverable
from .base import BaseNativeAdapter, GeneratedContent, make_slug


class NativeMarkdownAdapter(BaseNativeAdapter):
    """Deterministic native adapter rendering GitHub-Flavored Markdown documents."""

    def synthesize(
        self,
        canonical: CanonicalContent,
        deliverable: PlannedDeliverable,
        config: GenerationConfig,
    ) -> GeneratedContent:
        lines: List[str] = []

        # 1. Document Title & Header
        lines.append(f"# {deliverable.title}")
        lines.append("")
        lines.append(f"> **Executive Summary**: {canonical.intent.core_narrative}")
        lines.append(f"> **Primary Objective**: {canonical.intent.primary_purpose}  ")
        lines.append(f"> **Audience**: {config.audience} | **Tone**: {config.tone} | **Language**: {config.language.upper()}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # 2. Situational Context
        lines.append("## Situational Context")
        lines.append("")
        lines.append(canonical.context)
        lines.append("")

        # 3. Key Findings & Grounded Facts
        if canonical.facts:
            lines.append("## Key Findings & Grounded Facts")
            lines.append("")
            for fact in canonical.facts:
                ev_tag = f"`[{fact.evidence_status.upper()}]`" if fact.evidence_status else ""
                conf = f"(confidence: {fact.confidence:.2f})"
                ref = f" *(ref: {fact.source_reference})*" if fact.source_reference else ""
                lines.append(f"- {ev_tag} {fact.statement} {conf}{ref}")
            lines.append("")

        # 4. Qualitative Claims
        if canonical.claims:
            lines.append("## Analyzed Claims & Arguments")
            lines.append("")
            for cl in canonical.claims:
                claimant = f"**{cl.claimant}**: " if cl.claimant else ""
                evidence = f" — *Evidence: {cl.evidence}*" if cl.evidence else ""
                lines.append(f"- {claimant}{cl.claim}{evidence}")
            lines.append("")

        # 5. Quantitative Metrics & Data Points (Table)
        if canonical.data_points:
            lines.append("## Quantitative Metrics")
            lines.append("")
            lines.append("| Metric | Value | Unit | Context |")
            lines.append("|---|---|---|---|")
            for dp in canonical.data_points:
                unit = dp.unit or "-"
                ctx = dp.context or "-"
                lines.append(f"| {dp.metric} | {dp.value} | {unit} | {ctx} |")
            lines.append("")

        # 6. Chronological Events
        if canonical.events:
            lines.append("## Chronological Milestones")
            lines.append("")
            for ev in canonical.events:
                ts = f"**{ev.timestamp_desc}**: " if ev.timestamp_desc else ""
                sig = f" — *Impact: {ev.significance}*" if ev.significance else ""
                lines.append(f"- {ts}{ev.title}{sig}")
            lines.append("")

        # 7. Actionable Recommendations
        if canonical.recommendations:
            lines.append("## Actionable Recommendations")
            lines.append("")
            for idx, rec in enumerate(canonical.recommendations, 1):
                lines.append(f"{idx}. {rec}")
            lines.append("")

        # 8. Source References & Provenance
        lines.append("## References & Provenance")
        lines.append("")
        if canonical.references:
            for ref in canonical.references:
                loc = f" (`{ref.uri_or_location}`)" if ref.uri_or_location else ""
                lines.append(f"- **{ref.citation_key}**: {ref.title}{loc}")
        else:
            lines.append(f"- Source Content Hash: `{canonical.content_hash}`")
        lines.append("")
        lines.append("---")
        lines.append(f"*Synthesized by Limo Native Markdown Adapter • Provenance Digest: `{canonical.content_hash[:16]}...`*")

        raw_md = "\n".join(lines)
        raw_bytes = raw_md.encode("utf-8")
        clean_slug = make_slug(deliverable.title, fallback="document")
        filename = f"{clean_slug}.md"

        word_count = len(raw_md.split())
        stats = f"{word_count:,} words • Markdown (.md)"

        return GeneratedContent(
            content_bytes=raw_bytes,
            filename=filename,
            file_format=".md",
            artifact_type=ArtifactType.DOC,
            stats=stats,
            metadata={"word_count": word_count, "sections_count": len(re.findall(r"^##\s", raw_md, re.M))},
        )


class NativeHtmlAdapter(BaseNativeAdapter):
    """Deterministic native adapter rendering self-contained, responsive HTML5 documents."""

    def synthesize(
        self,
        canonical: CanonicalContent,
        deliverable: PlannedDeliverable,
        config: GenerationConfig,
    ) -> GeneratedContent:
        safe_title = html.escape(deliverable.title)
        safe_narrative = html.escape(canonical.intent.core_narrative)
        safe_context = html.escape(canonical.context)

        # Build Metrics HTML Cards
        metrics_html = ""
        if canonical.data_points:
            cards = []
            for dp in canonical.data_points:
                cards.append(
                    f'<div class="metric-card">'
                    f'  <div class="metric-value">{html.escape(dp.value)}</div>'
                    f'  <div class="metric-label">{html.escape(dp.metric)}</div>'
                    f'  <div class="metric-context">{html.escape(dp.context or dp.unit or "")}</div>'
                    f'</div>'
                )
            metrics_html = (
                f'<section class="section">'
                f'  <h2>Key Metrics</h2>'
                f'  <div class="metrics-grid">{"".join(cards)}</div>'
                f'</section>'
            )

        # Build Facts HTML Cards
        facts_html = ""
        if canonical.facts:
            items = []
            for f in canonical.facts:
                badge_class = "badge-verified" if f.evidence_status == "verified" else "badge-weak"
                badge = f'<span class="badge {badge_class}">{html.escape(f.evidence_status.upper())}</span>'
                ref = f'<span class="ref-meta">Ref: {html.escape(f.source_reference)}</span>' if f.source_reference else ""
                items.append(
                    f'<li class="fact-item">'
                    f'  <div>{badge} {html.escape(f.statement)}</div>'
                    f'  {ref}'
                    f'</li>'
                )
            facts_html = (
                f'<section class="section">'
                f'  <h2>Grounded Findings</h2>'
                f'  <ul class="facts-list">{"".join(items)}</ul>'
                f'</section>'
            )

        # Build Recommendations HTML
        recs_html = ""
        if canonical.recommendations:
            items = [f'<li>{html.escape(rec)}</li>' for rec in canonical.recommendations]
            recs_html = (
                f'<section class="section">'
                f'  <h2>Strategic Recommendations</h2>'
                f'  <ol class="recs-list">{"".join(items)}</ol>'
                f'</section>'
            )

        html_content = f"""<!DOCTYPE html>
<html lang="{html.escape(config.language)}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{safe_title}</title>
  <style>
    :root {{
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --verified: #10b981;
      --warning: #f59e0b;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 2rem 1rem;
    }}
    .container {{
      max-width: 900px;
      margin: 0 auto;
    }}
    header {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 2rem;
      margin-bottom: 2rem;
    }}
    h1 {{ font-size: 2rem; color: var(--primary); margin-bottom: 0.75rem; }}
    .narrative {{ font-size: 1.15rem; font-weight: 500; color: var(--text); margin-bottom: 1rem; }}
    .meta-bar {{ display: flex; gap: 1.5rem; color: var(--text-muted); font-size: 0.875rem; }}
    .section {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.75rem;
      margin-bottom: 1.5rem;
    }}
    h2 {{ font-size: 1.25rem; color: var(--text); margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; }}
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
    }}
    .metric-card {{
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1rem;
      text-align: center;
    }}
    .metric-value {{ font-size: 1.75rem; font-weight: 700; color: var(--primary); }}
    .metric-label {{ font-size: 0.9rem; font-weight: 600; margin-top: 0.25rem; }}
    .metric-context {{ font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem; }}
    .facts-list {{ list-style: none; }}
    .fact-item {{
      padding: 0.75rem 0;
      border-bottom: 1px solid rgba(51, 65, 85, 0.4);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .fact-item:last-child {{ border-bottom: none; }}
    .badge {{
      display: inline-block;
      font-size: 0.7rem;
      font-weight: 700;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      margin-right: 0.5rem;
      text-transform: uppercase;
    }}
    .badge-verified {{ background: rgba(16, 185, 129, 0.2); color: var(--verified); border: 1px solid var(--verified); }}
    .badge-weak {{ background: rgba(245, 158, 11, 0.2); color: var(--warning); border: 1px solid var(--warning); }}
    .ref-meta {{ font-size: 0.8rem; color: var(--text-muted); }}
    .recs-list {{ padding-left: 1.5rem; }}
    .recs-list li {{ margin-bottom: 0.5rem; }}
    footer {{
      text-align: center;
      color: var(--text-muted);
      font-size: 0.8rem;
      margin-top: 2rem;
      padding-top: 1rem;
      border-top: 1px solid var(--border);
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>{safe_title}</h1>
      <div class="narrative">{safe_narrative}</div>
      <div class="meta-bar">
        <span>Audience: {html.escape(config.audience)}</span>
        <span>Tone: {html.escape(config.tone)}</span>
        <span>Provenance: {canonical.content_hash[:12]}...</span>
      </div>
    </header>

    <section class="section">
      <h2>Context & Overview</h2>
      <p>{safe_context}</p>
    </section>

    {metrics_html}
    {facts_html}
    {recs_html}

    <footer>
      Synthesized by Limo Native HTML Adapter • Provenance SHA-256: <code>{canonical.content_hash}</code>
    </footer>
  </div>
</body>
</html>"""

        raw_bytes = html_content.encode("utf-8")
        clean_slug = make_slug(deliverable.title, fallback="deliverable")
        filename = f"{clean_slug}.html"

        stats = f"{len(raw_bytes):,} bytes • Standalone HTML5"

        return GeneratedContent(
            content_bytes=raw_bytes,
            filename=filename,
            file_format=".html",
            artifact_type=ArtifactType.DOC,
            stats=stats,
            metadata={"format": "html5", "has_css": True, "size_bytes": len(raw_bytes)},
        )
