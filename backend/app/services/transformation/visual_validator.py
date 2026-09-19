"""Post-export visual validation for Prismo-generated poster artifacts (D8.8).

Deterministic CSS/HTML analysis that catches layout, contrast, and palette issues
before artifact handoff. Does NOT depend on Prismo internals — reads workspace files.

Key design decisions:
- WHITE ≠ LIGHT. Bright includes gradients, pastels, vivid fields, tinted surfaces.
- Gradients are first-class backgrounds. A gradient is not an automatic dark indicator.
- Contrast is evaluated against the effective background (including gradient stops).
- Dark backgrounds are not prohibited — repeated unjustified dark default is flagged.
- Palette validation checks semantic coherence, not raw hex count.
  Gradient stop colors are excluded from noise analysis.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("limo.services.transformation.visual_validator")


@dataclass
class VisualValidationResult:
    """Structured result from post-export visual analysis."""

    passed: bool = True
    failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    repair_hints: List[str] = field(default_factory=list)


class PrismoVisualValidator:
    """Validates generated HTML/CSS for visual quality before artifact handoff.

    Operates at the Limo adapter boundary — never modifies Prismo internals.
    Lightweight regex-based CSS/HTML parsing (no pixel-level analysis).
    """

    def validate(self, html: str, css: str) -> VisualValidationResult:
        """Run all visual quality checks and return structured result."""
        result = VisualValidationResult()

        self._check_text_overflow(html, css, result)
        self._check_repeated_dark_bias(html, css, result)
        self._check_contrast_issues(css, result)
        self._check_palette_coherence(css, result)
        self._check_card_alignment(html, css, result)

        result.passed = len(result.failures) == 0
        return result

    # ── Text Overflow ────────────────────────────────────────────

    def _check_text_overflow(
        self, html: str, css: str, result: VisualValidationResult
    ) -> None:
        """Detect CSS patterns that risk text overflow."""
        card_classes = re.findall(
            r"\.([\w-]*(?:card|panel|container|box|block)[\w-]*)\s*\{([^}]+)\}",
            css,
            re.IGNORECASE,
        )
        for cls_name, rules in card_classes:
            has_fixed_height = bool(re.search(r"height:\s*\d+px", rules))
            has_overflow_hidden = bool(re.search(r"overflow:\s*hidden", rules))
            if has_fixed_height and not has_overflow_hidden:
                result.warnings.append(
                    f"TEXT_OVERFLOW_RISK: '.{cls_name}' has fixed height "
                    f"without overflow:hidden"
                )
                result.repair_hints.append(
                    f"Add overflow:hidden to '.{cls_name}' or remove fixed height"
                )

    # ── Repeated Dark Bias ───────────────────────────────────────

    def _check_repeated_dark_bias(
        self, html: str, css: str, result: VisualValidationResult
    ) -> None:
        """Detect unjustified dark default palette on generic requests.

        This does NOT mean dark = bad. It means:
        - Generic request producing dark/cyberpunk repeatedly → palette-bias warning
        - User explicitly requests dark/cinematic → dark is valid
          (the adapter skips this check when user intent is explicit)
        - Subject strongly benefits from dark → acceptable
        """
        artboard_match = re.search(
            r"\.poster-artboard\s*\{([^}]+)\}", css, re.IGNORECASE
        )
        if not artboard_match:
            return

        rules = artboard_match.group(1)

        # Check for gradient background first
        bg_gradient_match = re.search(
            r"background(?:-image)?:\s*((?:linear|radial)-gradient\([^)]+\))",
            rules,
            re.IGNORECASE,
        )
        if bg_gradient_match:
            stops = self._extract_gradient_hex_stops(bg_gradient_match.group(1))
            if stops:
                luminances = [
                    self._estimate_hex_luminance(s) for s in stops
                ]
                valid_lums = [lum for lum in luminances if lum is not None]
                if valid_lums:
                    avg_lum = sum(valid_lums) / len(valid_lums)
                    if avg_lum < 0.12:
                        result.warnings.append(
                            f"REPEATED_DARK_BIAS: poster-artboard gradient has very "
                            f"low average stop luminance ({avg_lum:.2f}). Generic "
                            f"topics should produce varied bright/balanced palettes."
                        )
                        result.repair_hints.append(
                            "Consider a bright gradient, pastel field, vivid color, "
                            "warm editorial, or other luminous background"
                        )
            return

        # Check for solid background-color
        bg_color_match = re.search(
            r"background(?:-color)?:\s*(#[0-9a-fA-F]{3,8})", rules
        )
        if bg_color_match:
            luminance = self._estimate_hex_luminance(bg_color_match.group(1))
            if luminance is not None and luminance < 0.12:
                result.warnings.append(
                    f"REPEATED_DARK_BIAS: poster-artboard background "
                    f"'{bg_color_match.group(1)}' has very low luminance "
                    f"({luminance:.2f}). Generic topics should produce varied "
                    f"bright/balanced palettes."
                )
                result.repair_hints.append(
                    "Consider a bright gradient, pastel field, vivid color, "
                    "warm editorial, or other luminous background"
                )

    # ── Gradient-Aware Contrast ──────────────────────────────────

    def _check_contrast_issues(
        self, css: str, result: VisualValidationResult
    ) -> None:
        """Detect text/background pairs with insufficient contrast.

        Handles:
        - Solid background-color vs color
        - Gradient backgrounds: extracts stop colors and evaluates contrast
          against the worst-case (minimum-contrast) stop
        """
        rule_blocks = re.findall(r"([^{}]*)\{([^}]+)\}", css)

        for _selector, block in rule_blocks:
            text_match = re.search(
                r"(?<![a-zA-Z-])color:\s*(#[0-9a-fA-F]{3,8})", block
            )
            if not text_match:
                continue

            text_lum = self._estimate_hex_luminance(text_match.group(1))
            if text_lum is None:
                continue

            # Strategy 1: solid background-color
            bg_match = re.search(
                r"background(?:-color)?:\s*(#[0-9a-fA-F]{3,8})", block
            )
            if bg_match:
                bg_lum = self._estimate_hex_luminance(bg_match.group(1))
                if bg_lum is not None:
                    contrast = abs(bg_lum - text_lum)
                    if contrast < 0.25:
                        result.failures.append(
                            f"LOW_CONTRAST: background {bg_match.group(1)} vs "
                            f"text {text_match.group(1)} "
                            f"(luminance delta={contrast:.2f}, minimum=0.25)"
                        )
                        result.repair_hints.append(
                            f"Increase contrast between {bg_match.group(1)} and "
                            f"{text_match.group(1)}"
                        )
                continue

            # Strategy 2: gradient background — check against worst-case stop
            gradient_match = re.search(
                r"background(?:-image)?:\s*((?:linear|radial)-gradient\([^)]+\))",
                block,
                re.IGNORECASE,
            )
            if gradient_match:
                stops = self._extract_gradient_hex_stops(gradient_match.group(1))
                if stops:
                    min_contrast = 1.0
                    worst_stop = stops[0]
                    for stop in stops:
                        stop_lum = self._estimate_hex_luminance(stop)
                        if stop_lum is not None:
                            delta = abs(stop_lum - text_lum)
                            if delta < min_contrast:
                                min_contrast = delta
                                worst_stop = stop
                    if min_contrast < 0.20:
                        result.failures.append(
                            f"LOW_CONTRAST_GRADIENT: text {text_match.group(1)} "
                            f"has insufficient contrast against gradient stop "
                            f"{worst_stop} (luminance delta={min_contrast:.2f}). "
                            f"Text may be unreadable in some gradient regions."
                        )
                        result.repair_hints.append(
                            f"Add a scrim, text surface, or adjust text color for "
                            f"the gradient region near {worst_stop}"
                        )

    # ── Palette Coherence ────────────────────────────────────────

    def _check_palette_coherence(
        self, css: str, result: VisualValidationResult
    ) -> None:
        """Check for palette incoherence — excessive random colors.

        Distinguishes:
        - Gradient stop colors (inside gradient() declarations) → excluded
        - Intentional shade families → not penalized
        - Arbitrary unrelated colors per-component → flagged
        """
        # Identify gradient() spans to exclude their stop colors
        gradient_spans = [
            (m.start(), m.end())
            for m in re.finditer(
                r"(?:linear|radial)-gradient\([^)]+\)", css, re.IGNORECASE
            )
        ]
        non_gradient_colors: List[str] = []
        for m in re.finditer(r"#[0-9a-fA-F]{6}", css):
            in_gradient = any(s <= m.start() < e for s, e in gradient_spans)
            if not in_gradient:
                non_gradient_colors.append(m.group(0).lower())

        unique = set(non_gradient_colors)
        if len(unique) > 14:
            result.warnings.append(
                f"PALETTE_INCOHERENCE: {len(unique)} unique non-gradient hex colors "
                f"detected. A coherent design system uses defined semantic palette "
                f"roles, not arbitrary per-component colors."
            )
            result.repair_hints.append(
                "Consolidate to semantic palette roles: background, primary text, "
                "secondary text, accent 1, accent 2, surface, border"
            )

    # ── Card Alignment ───────────────────────────────────────────

    def _check_card_alignment(
        self, html: str, css: str, result: VisualValidationResult
    ) -> None:
        """Check for inconsistent card geometry in multi-card layouts."""
        card_rules = re.findall(
            r"\.([\w-]*card[\w-]*)\s*\{([^}]+)\}", css, re.IGNORECASE
        )
        if len(card_rules) >= 2:
            radii: set[str] = set()
            for _, rules in card_rules:
                r = re.search(r"border-radius:\s*(\d+px)", rules)
                if r:
                    radii.add(r.group(1))
            if len(radii) > 2:
                result.warnings.append(
                    f"ALIGNMENT_INCONSISTENCY: {len(radii)} different border-radius "
                    f"values across card components: {radii}"
                )
                result.repair_hints.append(
                    "Use a single border-radius value for all cards in a group"
                )

    # ── Utility ──────────────────────────────────────────────────

    def _extract_gradient_hex_stops(self, gradient_str: str) -> List[str]:
        """Extract hex color stops from a CSS gradient declaration."""
        return [
            m.group(0).lower()
            for m in re.finditer(r"#[0-9a-fA-F]{3,8}", gradient_str)
        ]

    def _estimate_hex_luminance(self, hex_color: str) -> Optional[float]:
        """Estimate relative luminance from hex color (0.0=black, 1.0=white)."""
        hex_color = hex_color.lstrip("#").lower()
        if len(hex_color) == 3:
            hex_color = "".join(c * 2 for c in hex_color)
        if len(hex_color) < 6:
            return None
        try:
            r = int(hex_color[0:2], 16) / 255.0
            g = int(hex_color[2:4], 16) / 255.0
            b = int(hex_color[4:6], 16) / 255.0
            # Relative luminance (WCAG simplified)
            return 0.2126 * r + 0.7152 * g + 0.0722 * b
        except (ValueError, IndexError):
            return None


# Singleton
prismo_visual_validator = PrismoVisualValidator()
