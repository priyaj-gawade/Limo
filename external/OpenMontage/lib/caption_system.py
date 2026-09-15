"""Caption Subsystem for OpenMontage & Limo (Phase D8.4).

Implements the strict caption doctrine:
1. CAPTION MODEL:
   - DROP: Filler words ("um", "uh", "you know"), obvious stutters, self-corrections.
   - RAIL: Default treatment for ordinary spoken content. Verbatim spoken wording,
     lower-third overlay, clean and unobtrusive.
   - EMBED: Rare emphasis/climax (sparse, max 1 per scene/beat, never adjacent).
   - STANDARD explainer mode: rail-first, embed-scarce.
   - CINEMATIC mode: embed-heavy allowed ONLY when explicitly requested.

2. OVERLAY DOCTRINE:
   - Captions are composited ON TOP of video footage.
   - True frame center is preserved (no upward shift, no reserved bottom band).
   - Content extends underneath captions.
   - No keep-out / safe band.

3. HARD LENGTH RULE:
   - A visible caption unit MUST contain AT MOST 3 WORDS.
   - Prefer 1-3 words. Never exceed 3 words.
   - Never display 7-10 words as one caption for several seconds.
   - Preserves exact spoken wording for rail captions.

4. TIMING HIERARCHY:
   - Tier 1: Real word-level timestamps (ASR / TTS)
   - Tier 2: Real phrase/scene-level timestamps (actual synthesized audio duration)
   - Tier 3: Deterministic duration allocation based on speech rate (clearly marked estimated)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


FILLER_WORDS = {
    "um", "uh", "uhh", "umm", "erm", "ah", "ahh",
    "like", "you know", "basically", "actually", "literally",
}

MAX_WORDS_PER_CAPTION = 3


@dataclass
class CaptionUnit:
    """Discrete, timed caption display unit adhering to the <=3-word hard rule."""
    text: str
    start_time: float
    end_time: float
    treatment: str = "rail"  # "drop" | "rail" | "embed"
    emphasis: List[str] = field(default_factory=list)
    scene_id: Optional[str] = None
    timing_source: str = "phrase_proportional"  # "word_timestamps" | "phrase_proportional" | "estimated"

    def word_count(self) -> int:
        return len(self.text.strip().split())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "start_time": round(self.start_time, 3),
            "end_time": round(self.end_time, 3),
            "treatment": self.treatment,
            "emphasis": self.emphasis,
            "scene_id": self.scene_id,
            "word_count": self.word_count(),
            "timing_source": self.timing_source,
        }


def validate_caption_word_limit(captions: List[CaptionUnit]) -> None:
    """Validate that every visible caption unit contains AT MOST 3 words.

    Raises ValueError loudly if any non-drop caption unit exceeds 3 words or has invalid timing.
    """
    if not captions:
        return

    for idx, cue in enumerate(captions):
        if cue.treatment == "drop":
            continue

        raw_words = cue.text.strip().split()
        if len(raw_words) > MAX_WORDS_PER_CAPTION:
            raise ValueError(
                f"Caption word limit violation at caption {idx} "
                f"({cue.start_time:.2f}s - {cue.end_time:.2f}s): "
                f"expected at most {MAX_WORDS_PER_CAPTION} words, got {len(raw_words)} words: '{cue.text}'"
            )
        if len(raw_words) == 0:
            raise ValueError(f"Caption {idx} has empty text.")
        if cue.end_time < cue.start_time:
            raise ValueError(
                f"Caption {idx} has invalid duration: start={cue.start_time:.3f}s, end={cue.end_time:.3f}s"
            )
        if idx > 0 and captions[idx - 1].treatment != "drop":
            prev = captions[idx - 1]
            if cue.start_time < prev.start_time:
                raise ValueError(
                    f"Non-monotonic timestamps at caption {idx}: starts at {cue.start_time:.3f}s before previous {prev.start_time:.3f}s"
                )


def filter_fillers_and_stutters(tokens: List[str]) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Filter out filler words and repeated stutters, returning (cleaned_tokens, dropped_records)."""
    cleaned: List[str] = []
    dropped: List[Dict[str, Any]] = []

    i = 0
    while i < len(tokens):
        token = tokens[i]
        norm = token.lower().strip(".,!?;:\"'")

        # 1. Check for filler words ("um", "uh", etc.)
        if norm in FILLER_WORDS:
            dropped.append({"token": token, "reason": "filler"})
            i += 1
            continue

        # 2. Check for two-word filler ("you know")
        if norm == "you" and i + 1 < len(tokens) and tokens[i + 1].lower().strip(".,!?;:\"'") == "know":
            dropped.append({"token": f"{token} {tokens[i + 1]}", "reason": "filler"})
            i += 2
            continue

        # 3. Check for obvious stutter ("the the", "we we")
        if i + 1 < len(tokens):
            next_norm = tokens[i + 1].lower().strip(".,!?;:\"'")
            if norm == next_norm and len(norm) > 1:
                dropped.append({"token": token, "reason": "stutter"})
                i += 1
                continue

        # 4. Check for hyphenated stutter ("th- the")
        if norm.endswith("-") and i + 1 < len(tokens):
            dropped.append({"token": token, "reason": "stutter"})
            i += 1
            continue

        cleaned.append(token)
        i += 1

    return cleaned, dropped


def segment_text_into_cues(text: str, max_words: int = MAX_WORDS_PER_CAPTION) -> List[str]:
    """Segment spoken narration text into natural phrasing chunks of 1 to 3 words.

    HARD RULE:
    - Maximum 3 words per visible caption unit.
    - Prefer 1 to 3 words (typically 2 words, or 1-2 words for punchy delivery).
    - Never exceed 3 words.
    - Preserves natural phrasing and avoids splitting across obvious syntactic boundaries.
    """
    cleaned_text = re.sub(r"\s+", " ", text).strip()
    if not cleaned_text:
        return []

    # Split by strong punctuation boundaries first
    clauses = re.split(r"([,;:\.!\?]+|\s*—\s*|\s*--\s*)", cleaned_text)
    raw_segments: List[str] = []

    current_clause = ""
    for part in clauses:
        if not part:
            continue
        if re.match(r"^[,;:\.!\?]+|\s*—\s*|\s*--\s*$", part):
            if current_clause:
                current_clause += part.strip()
                raw_segments.append(current_clause.strip())
                current_clause = ""
        else:
            if current_clause:
                raw_segments.append(current_clause.strip())
            current_clause = part.strip()
    if current_clause:
        raw_segments.append(current_clause.strip())

    cues: List[str] = []

    # Preposition and auxiliary verb markers for natural phrase breaking
    BREAK_MARKERS = {
        "is", "are", "was", "were", "will", "can", "could", "should", "would",
        "in", "on", "at", "to", "for", "with", "from", "by", "of", "and", "but", "or", "as",
    }

    for seg in raw_segments:
        words = seg.split()
        if not words:
            continue

        # Filter out filler words from segmentation
        clean_words, _ = filter_fillers_and_stutters(words)
        if not clean_words:
            continue

        n = len(clean_words)
        if n <= max_words:
            cues.append(" ".join(clean_words))
            continue

        # Natural partitioning ensuring every chunk is 1 <= count <= 3
        idx = 0
        while idx < n:
            rem = n - idx
            if rem <= max_words:
                cues.append(" ".join(clean_words[idx:idx + rem]))
                break

            if rem == 4:
                # Group 4 as 2 and 2 for natural cadence
                cues.append(" ".join(clean_words[idx:idx + 2]))
                cues.append(" ".join(clean_words[idx + 2:idx + 4]))
                break

            if rem == 5:
                # "Artificial intelligence is changing healthcare"
                # If clean_words[idx+2] is a verb marker like "is", break as 2, 2, 1
                if clean_words[idx + 2].lower() in BREAK_MARKERS:
                    cues.append(" ".join(clean_words[idx:idx + 2]))
                    cues.append(" ".join(clean_words[idx + 2:idx + 4]))
                    cues.append(clean_words[idx + 4])
                    break
                else:
                    # Otherwise group as 2 and 3
                    cues.append(" ".join(clean_words[idx:idx + 2]))
                    idx += 2
                    continue

            if rem == 6:
                # Group 6 as 2, 2, 2 for readable visual cadence
                cues.append(" ".join(clean_words[idx:idx + 2]))
                idx += 2
                continue

            # For rem >= 7: take 2 or 3 depending on break markers
            take = 2
            if idx + 2 < n and clean_words[idx + 2].lower() in BREAK_MARKERS:
                take = 2
            elif idx + 3 < n and clean_words[idx + 3].lower() in BREAK_MARKERS:
                take = 3
            else:
                take = 2 if rem % 2 == 0 else 3

            take = min(take, max_words, rem)
            cues.append(" ".join(clean_words[idx:idx + take]))
            idx += take

    # Deterministic assertion to guarantee hard word-limit rule
    for c in cues:
        w_cnt = len(c.split())
        assert 1 <= w_cnt <= max_words, f"Hard rule violated: '{c}' contains {w_cnt} words (max {max_words})"

    return cues


def assign_timestamps(
    cues: List[str],
    start_time: float,
    total_duration: float,
    word_timestamps: Optional[List[Dict[str, Any]]] = None,
    scene_id: Optional[str] = None,
) -> List[CaptionUnit]:
    """Assign monotonic, non-overlapping timestamps to segmented cues.

    Preferred Timing Hierarchy:
    1. Real word-level timestamps (word_timestamps from TTS/ASR)
    2. Real phrase/scene-level timestamps (proportional duration from synthesized audio)
    3. Deterministic estimated duration allocation based on speech rate (clearly marked estimated)
    """
    if not cues:
        return []

    units: List[CaptionUnit] = []

    if word_timestamps and len(word_timestamps) > 0:
        # Tier 1: Real word timestamps
        w_idx = 0
        for cue_text in cues:
            cue_words = cue_text.split()
            cue_w_count = len(cue_words)
            if w_idx < len(word_timestamps):
                first_w = word_timestamps[w_idx]
                last_w_idx = min(w_idx + cue_w_count - 1, len(word_timestamps) - 1)
                last_w = word_timestamps[last_w_idx]
                c_start = float(first_w.get("start", start_time))
                c_end = float(last_w.get("end", c_start + 0.3))
                w_idx += cue_w_count
            else:
                c_start = units[-1].end_time if units else start_time
                c_end = c_start + 0.3

            # Ensure strictly non-overlapping & positive duration
            if units and c_start < units[-1].end_time:
                c_start = units[-1].end_time
            if c_end <= c_start:
                c_end = c_start + 0.2

            units.append(
                CaptionUnit(
                    text=cue_text,
                    start_time=round(max(0.0, c_start), 3),
                    end_time=round(max(c_start + 0.1, c_end), 3),
                    treatment="rail",
                    scene_id=scene_id,
                    timing_source="word_timestamps",
                )
            )
    elif total_duration > 0.0:
        # Tier 2: Real phrase/scene-level timing distributed proportionally
        weights = [max(1, len(re.sub(r"[^a-zA-Z0-9]", "", c))) for c in cues]
        total_weight = sum(weights) or 1

        curr = start_time
        for i, cue_text in enumerate(cues):
            chunk_dur = (weights[i] / total_weight) * total_duration
            chunk_dur = max(0.2, chunk_dur)
            end = curr + chunk_dur
            units.append(
                CaptionUnit(
                    text=cue_text,
                    start_time=round(curr, 3),
                    end_time=round(end, 3),
                    treatment="rail",
                    scene_id=scene_id,
                    timing_source="phrase_proportional",
                )
            )
            curr = end
    else:
        # Tier 3: Deterministic estimated duration fallback (clearly documented)
        curr = start_time
        for cue_text in cues:
            cue_w_count = len(cue_text.split())
            # Assume 2.5 words per second (standard explainer speaking cadence)
            est_dur = max(0.3, round(cue_w_count / 2.5, 3))
            end = curr + est_dur
            units.append(
                CaptionUnit(
                    text=cue_text,
                    start_time=round(curr, 3),
                    end_time=round(end, 3),
                    treatment="rail",
                    scene_id=scene_id,
                    timing_source="estimated",
                )
            )
            curr = end

    return units


def assign_treatments(
    captions: List[CaptionUnit],
    mode: str = "explainer",
    key_terms: Optional[List[str]] = None,
) -> List[CaptionUnit]:
    """Assign DROP / RAIL / EMBED treatments adhering to the doctrine:

    - Standard explainer mode: rail-first, embed-scarce.
      - At most 1 embed per scene/beat.
      - Embeds must never be adjacent or co-visible.
      - Promotes only genuine numerical or conceptual climax words.
    - Cinematic mode: embed-heavy allowed only if mode == "cinematic".
    - Inline emphasis: keywords receive highlight within the rail.
    """
    key_terms_lower = {k.lower() for k in (key_terms or [])}

    embed_count_in_scene: Dict[str, int] = {}
    last_embed_idx = -99

    for idx, cue in enumerate(captions):
        scene_key = cue.scene_id or "default"
        words = cue.text.split()

        # Check for inline emphasis words
        matched_emphasis = []
        for w in words:
            clean_w = w.lower().strip(".,!?;:\"'")
            if clean_w in key_terms_lower or re.match(r"^\$?\d+[\d,\.]*[%BKMbkm]?$", clean_w):
                matched_emphasis.append(w)

        if matched_emphasis:
            cue.emphasis = matched_emphasis

        # Evaluate EMBED eligibility
        is_cinematic = (mode == "cinematic")
        has_climax_word = bool(
            re.search(r"\b(\$?\d+[\d,\.]*[%BKMbkm]?|breakthrough|revolution|unprecedented|crucial)\b", cue.text, re.IGNORECASE)
        )

        can_embed = False
        if is_cinematic:
            can_embed = (idx - last_embed_idx) >= 2
        else:
            # Standard explainer mode: embed-scarce! Max 1 per scene, at least 3 cues apart
            scene_embeds = embed_count_in_scene.get(scene_key, 0)
            if scene_embeds == 0 and has_climax_word and (idx - last_embed_idx) >= 3:
                can_embed = True

        if can_embed:
            cue.treatment = "embed"
            embed_count_in_scene[scene_key] = embed_count_in_scene.get(scene_key, 0) + 1
            last_embed_idx = idx
        else:
            cue.treatment = "rail"

    return captions


def format_srt_timestamp(seconds: float) -> str:
    """Format seconds into standard SRT timestamp: HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0.0
    hrs = int(seconds // 3600)
    rem = seconds % 3600
    mins = int(rem // 60)
    secs = int(rem % 60)
    millis = int(round((rem - int(rem)) * 1000))
    if millis >= 1000:
        millis = 999
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def format_ass_timestamp(seconds: float) -> str:
    """Format seconds into standard ASS timestamp: H:MM:SS.cc."""
    if seconds < 0:
        seconds = 0.0
    hrs = int(seconds // 3600)
    rem = seconds % 3600
    mins = int(rem // 60)
    secs = int(rem % 60)
    centis = int(round((rem - int(rem)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hrs}:{mins:02d}:{secs:02d}.{centis:02d}"


def render_srt(captions: List[CaptionUnit]) -> str:
    """Render CaptionUnits to compliant SubRip (.srt) format."""
    lines: List[str] = []
    cue_num = 1
    for cue in captions:
        if cue.treatment == "drop":
            continue
        lines.append(str(cue_num))
        lines.append(f"{format_srt_timestamp(cue.start_time)} --> {format_srt_timestamp(cue.end_time)}")
        lines.append(cue.text)
        lines.append("")
        cue_num += 1
    return "\n".join(lines)


def render_ass(
    captions: List[CaptionUnit],
    width: int = 1920,
    height: int = 1080,
    font_name: str = "Roboto",
) -> str:
    """Render CaptionUnits to Advanced SubStation Alpha (.ass) format.

    ENFORCES OVERLAY DOCTRINE:
    - Alignment=2 (bottom-center)
    - MarginV=48 (lower-third overlay)
    - Regular Roboto white with 1px black outline for standard rail
    - Roboto Bold white with 1.5px black outline for emphasis/climax embed
    - Composited strictly on top of video, true frame center preserved
    """
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CaptionRail,{font_name},36,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,1.0,0,2,40,40,48,1
Style: CaptionEmbed,{font_name},46,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,1.5,0,2,40,40,64,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: List[str] = []
    for cue in captions:
        if cue.treatment == "drop":
            continue

        start_str = format_ass_timestamp(cue.start_time)
        end_str = format_ass_timestamp(cue.end_time)
        style_name = "CaptionEmbed" if cue.treatment == "embed" else "CaptionRail"

        text = cue.text
        # Inline emphasis within rail
        if cue.treatment == "rail" and cue.emphasis:
            for emp in cue.emphasis:
                # Highlight in yellow/cyan in ASS: {\c&H00FFFF&}word{\c&HFFFFFF&}
                text = re.sub(
                    rf"\b({re.escape(emp)})\b",
                    r"{\\c&H00FFFF&}\1{\\c&HFFFFFF&}",
                    text,
                    flags=re.IGNORECASE,
                )

        events.append(f"Dialogue: 0,{start_str},{end_str},{style_name},,0,0,0,,{text}")

    return header + "\n".join(events) + "\n"


class CaptionPipeline:
    """Comprehensive caption coordinator producing validated 1-3 word captions."""

    def __init__(self, mode: str = "explainer", font_name: str = "Roboto") -> None:
        self.mode = mode
        self.font_name = font_name

    def process_scenes(
        self,
        scenes: List[Any],
        key_terms: Optional[List[str]] = None,
        word_timestamps: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Convert a list of planned scenes into synchronized, validated 1-3 word CaptionUnits."""
        all_cues: List[CaptionUnit] = []
        cumulative_time = 0.0

        for scene in scenes:
            scene_text = getattr(scene, "narration_text", "") or ""
            scene_dur = float(
                getattr(scene, "actual_audio_duration", 0.0)
                or getattr(scene, "target_duration", 0.0)
                or 3.0
            )
            scene_id = f"scene_{getattr(scene, 'scene_index', len(all_cues) + 1)}"

            # 1. Segment text into 1-3 word cues
            cues = segment_text_into_cues(scene_text)
            if not cues:
                cumulative_time += scene_dur
                continue

            # 2. Assign timestamps
            scene_word_ts = getattr(scene, "word_timestamps", None)
            if not scene_word_ts and word_timestamps:
                scene_word_ts = word_timestamps

            scene_units = assign_timestamps(
                cues=cues,
                start_time=cumulative_time,
                total_duration=scene_dur,
                word_timestamps=scene_word_ts,
                scene_id=scene_id,
            )

            all_cues.extend(scene_units)
            cumulative_time += scene_dur

        # 3. Assign treatments (DROP / RAIL / EMBED) and emphasis
        all_cues = assign_treatments(all_cues, mode=self.mode, key_terms=key_terms)

        # 4. Strict Word-Limit Validation
        validate_caption_word_limit(all_cues)

        # 5. Render outputs
        srt_content = render_srt(all_cues)
        ass_content = render_ass(all_cues, font_name=self.font_name)

        return {
            "captions": [c.to_dict() for c in all_cues],
            "raw_captions": all_cues,
            "cue_count": len([c for c in all_cues if c.treatment != "drop"]),
            "srt": srt_content,
            "ass": ass_content,
            "total_duration": cumulative_time,
        }
