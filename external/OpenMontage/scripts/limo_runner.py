#!/usr/bin/env python3
"""OpenMontage Isolated Runner for Limo Video Generation (Phase D8.1).

Executes OpenMontage tools in an isolated process to consume a Limo
VideoGenerationContract and produce a validated final.mp4 artifact.

Usage:
    python limo_runner.py --contract /path/to/contract.json [--output-json /path/to/result.json]
    python limo_runner.py --contract '{"job_id": "...", "title": "..."}'
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure OpenMontage root is in sys.path
OPENMONTAGE_ROOT = Path(__file__).resolve().parent.parent
if str(OPENMONTAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(OPENMONTAGE_ROOT))

# Safe environment loading
def safe_init_env() -> None:
    """Load .env files safely and map Limo keys to OpenMontage expected variable names.

    Never logs or prints secret values.
    """
    search_paths = [
        OPENMONTAGE_ROOT / ".env",
        OPENMONTAGE_ROOT.parent.parent / ".env",  # Limo root
    ]
    for env_file in search_paths:
        if env_file.is_file():
            try:
                with open(env_file, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = value
            except Exception:
                pass

    # Map Limo credential aliases if standard keys are not already set
    if not os.environ.get("GEMINI_API_KEY"):
        gemini_key = os.environ.get("GEMINI_KEY_1") or os.environ.get("GOOGLE_API_KEY")
        if gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key
            os.environ.setdefault("GOOGLE_API_KEY", gemini_key)

    if not os.environ.get("PEXELS_API_KEY"):
        pexels_key = os.environ.get("PEXELS_KEY_1")
        if pexels_key:
            os.environ["PEXELS_API_KEY"] = pexels_key

    if not os.environ.get("PIXABAY_API_KEY"):
        pixabay_key = os.environ.get("PIXABAY_KEY_1")
        if pixabay_key:
            os.environ["PIXABAY_API_KEY"] = pixabay_key


# Stage tracking
@dataclass
class StageRecord:
    name: str
    status: str  # "completed", "failed", "skipped"
    duration_seconds: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "duration_seconds": round(self.duration_seconds, 3),
        }
        if self.error:
            d["error"] = self.error
        return d


class StageTracker:
    def __init__(self) -> None:
        self.stages: List[StageRecord] = []

    def run_stage(self, name: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
        start = time.time()
        try:
            res = fn(*args, **kwargs)
            duration = time.time() - start
            self.stages.append(StageRecord(name=name, status="completed", duration_seconds=duration))
            return res
        except Exception as e:
            duration = time.time() - start
            self.stages.append(StageRecord(name=name, status="failed", duration_seconds=duration, error=str(e)))
            raise


# Contract validation models
@dataclass
class VoiceConfig:
    provider: str = "edge_tts"
    voice_id: str = "en-US-AndrewMultilingualNeural"
    speed: float = 1.0
    pitch: float = 0.0


@dataclass
class ScriptSection:
    section_id: str
    heading: str = ""
    content: str = ""
    visual_hint: str = ""
    duration_seconds: Optional[float] = None


@dataclass
class VideoBrief:
    topic: str
    target_duration_seconds: float = 30.0
    aspect_ratio: str = "16:9"
    audience: str = "general audience"
    tone: str = "inspirational, educational"
    language: str = "en"
    key_points: List[str] = field(default_factory=list)


@dataclass
class VideoGenerationContract:
    job_id: str
    title: str
    conversation_id: Optional[str] = None
    topic: Optional[str] = None
    target_duration_seconds: float = 15.0
    aspect_ratio: str = "16:9"
    style_playbook: str = "clean-professional"
    voice_config: VoiceConfig = field(default_factory=VoiceConfig)
    subtitles: bool = True
    script_sections: List[ScriptSection] = field(default_factory=list)
    brief: Optional[VideoBrief] = None
    user_directive: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)


def validate_contract_dict(raw: Dict[str, Any]) -> VideoGenerationContract:
    """Validate and sanitize raw contract dictionary. Defends against path traversal."""
    if not isinstance(raw, dict):
        raise ValueError("Contract must be a JSON object")

    job_id = str(raw.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("Missing required field: 'job_id'")
    # Sanitize job_id to prevent directory traversal
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", job_id) or ".." in job_id:
        raise ValueError(f"Invalid job_id: {job_id}. Must contain only alphanumeric, dash, or underscore.")

    title = str(raw.get("title") or "").strip()
    if not title:
        raise ValueError("Missing required field: 'title'")

    topic = raw.get("topic")
    if topic:
        topic = str(topic).strip()
    else:
        topic = title

    conv_id = raw.get("conversation_id")
    if conv_id:
        conv_id = str(conv_id).strip()

    try:
        target_dur = float(raw.get("target_duration_seconds", 15.0))
        if target_dur < 3.0:
            target_dur = 3.0
        elif target_dur > 300.0:
            target_dur = 300.0
    except (ValueError, TypeError):
        target_dur = 15.0

    aspect_ratio = str(raw.get("aspect_ratio", "16:9")).strip()
    if aspect_ratio not in ("16:9", "9:16", "1:1"):
        aspect_ratio = "16:9"

    style_playbook = str(raw.get("style_playbook", "clean-professional")).strip()

    # Parse voice_config
    vc_raw = raw.get("voice_config") or {}
    if not isinstance(vc_raw, dict):
        vc_raw = {}
    voice_config = VoiceConfig(
        provider=str(vc_raw.get("provider") or "edge_tts").strip(),
        voice_id=str(vc_raw.get("voice_id") or vc_raw.get("voice") or "en-US-AndrewMultilingualNeural").strip(),
        speed=float(vc_raw.get("speed", 1.0)),
        pitch=float(vc_raw.get("pitch", 0.0)),
    )

    # Parse script_sections if provided
    raw_sections = raw.get("script_sections") or []
    sections: List[ScriptSection] = []
    if isinstance(raw_sections, list):
        for idx, s in enumerate(raw_sections):
            if isinstance(s, dict):
                sid = str(s.get("section_id") or f"sec_{idx + 1}")
                content = str(s.get("content") or s.get("text") or "").strip()
                heading = str(s.get("heading") or "").strip()
                hint = str(s.get("visual_hint") or s.get("visual_query") or "").strip()
                dur = s.get("duration_seconds")
                if dur is not None:
                    try:
                        dur = float(dur)
                    except (ValueError, TypeError):
                        dur = None
                if content:
                    sections.append(
                        ScriptSection(
                            section_id=sid,
                            heading=heading,
                            content=content,
                            visual_hint=hint,
                            duration_seconds=dur,
                        )
                    )

    # Parse VideoBrief if provided
    raw_brief = raw.get("brief")
    brief = None
    if isinstance(raw_brief, dict):
        brief = VideoBrief(
            topic=str(raw_brief.get("topic") or topic).strip(),
            target_duration_seconds=float(raw_brief.get("target_duration_seconds", target_dur)),
            aspect_ratio=str(raw_brief.get("aspect_ratio", aspect_ratio)).strip(),
            audience=str(raw_brief.get("audience", "general audience")).strip(),
            tone=str(raw_brief.get("tone", "inspirational, educational")).strip(),
            language=str(raw_brief.get("language", "en")).strip(),
            key_points=[str(kp).strip() for kp in raw_brief.get("key_points", []) if str(kp).strip()],
        )

    user_directive = raw.get("user_directive")
    if user_directive:
        user_directive = str(user_directive).strip()

    options = raw.get("options") or {}
    if not isinstance(options, dict):
        options = {}

    subtitles = raw.get("subtitles")
    if subtitles is None:
        subtitles = options.get("burn_subtitles", True)
    subtitles = bool(subtitles)

    return VideoGenerationContract(
        job_id=job_id,
        title=title,
        conversation_id=conv_id,
        topic=topic,
        target_duration_seconds=target_dur,
        aspect_ratio=aspect_ratio,
        style_playbook=style_playbook,
        voice_config=voice_config,
        subtitles=subtitles,
        script_sections=sections,
        brief=brief,
        user_directive=user_directive,
        options=options,
    )


@dataclass
class Scene:
    scene_index: int
    narration_text: str
    visual_query: str
    target_duration: float
    video_path: Optional[Path] = None
    audio_path: Optional[Path] = None
    actual_audio_duration: float = 0.0
    word_timestamps: Optional[List[Dict[str, Any]]] = None


class LimoRunner:
    """Orchestrates an isolated OpenMontage run for a single Limo video job."""

    def __init__(self, contract: VideoGenerationContract, work_dir: Optional[Path] = None) -> None:
        self.contract = contract
        self.tracker = StageTracker()

        # Initialize workspace paths
        if work_dir:
            self.project_dir = work_dir.resolve()
        else:
            self.project_dir = (OPENMONTAGE_ROOT / "projects" / contract.job_id).resolve()

        # Defend against path traversal
        projects_root = (OPENMONTAGE_ROOT / "projects").resolve()
        if not str(self.project_dir).startswith(str(projects_root)) and work_dir is None:
            raise ValueError("Resolved workspace path escapes allowed projects directory.")

        self.artifacts_dir = self.project_dir / "artifacts"
        self.audio_dir = self.project_dir / "assets" / "audio"
        self.video_dir = self.project_dir / "assets" / "video"
        self.renders_dir = self.project_dir / "renders"
        self.final_mp4 = self.renders_dir / "final.mp4"

        self.scenes: List[Scene] = []
        self.actual_visual_provider = "pexels"
        self.tools_discovered = False

    def log(self, message: str) -> None:
        """Stage-level logging format specified in D8.1 contract."""
        print(f"[runner] {message}", file=sys.stderr, flush=True)

    def init_workspace(self) -> None:
        """Create project directory layout."""
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.video_dir.mkdir(parents=True, exist_ok=True)
        self.renders_dir.mkdir(parents=True, exist_ok=True)

        # Save contract copy
        contract_save_path = self.project_dir / "contract.json"
        contract_data = {
            "job_id": self.contract.job_id,
            "conversation_id": self.contract.conversation_id,
            "title": self.contract.title,
            "topic": self.contract.topic,
            "target_duration_seconds": self.contract.target_duration_seconds,
            "aspect_ratio": self.contract.aspect_ratio,
            "style_playbook": self.contract.style_playbook,
            "voice_config": asdict(self.contract.voice_config),
            "script_sections": [asdict(s) for s in self.contract.script_sections],
            "options": self.contract.options,
        }
        with open(contract_save_path, "w", encoding="utf-8") as f:
            json.dump(contract_data, f, indent=2)

        self.log(f"project initialized: {self.project_dir.name}")

    def _ensure_tools(self) -> None:
        """Discover tools in OpenMontage registry."""
        if not self.tools_discovered:
            from tools.tool_registry import registry
            registry.discover("tools")
            self.tools_discovered = True

    def plan_script_and_scenes(self) -> List[Scene]:
        """Prepare script and scene definitions with strict duration & word budgeting."""
        brief = getattr(self.contract, "brief", None)
        topic = (brief.topic if brief and getattr(brief, "topic", None) else None) or self.contract.topic or self.contract.title
        target_dur = (brief.target_duration_seconds if brief and getattr(brief, "target_duration_seconds", None) else None) or self.contract.target_duration_seconds
        aspect_ratio = (brief.aspect_ratio if brief and getattr(brief, "aspect_ratio", None) else None) or self.contract.aspect_ratio
        tone = (brief.tone if brief and getattr(brief, "tone", None) else None) or "inspirational, educational"
        audience = (brief.audience if brief and getattr(brief, "audience", None) else None) or "general audience"
        key_points = (brief.key_points if brief and getattr(brief, "key_points", None) else []) or []
        key_points_text = ("\n- " + "\n- ".join(key_points)) if key_points else "Cover key facts and significant aspects of the topic."

        # Determine target scene count and max word budget based on target duration
        if target_dur <= 10.0:
            target_num_scenes = 2
            max_total_words = max(8, int(target_dur * 1.9))
        elif target_dur <= 25.0:
            target_num_scenes = min(3, max(2, int(target_dur / 6.0)))
            max_total_words = int(target_dur * 2.0)
        else:
            target_num_scenes = min(5, max(3, int(target_dur / 7.0)))
            max_total_words = int(target_dur * 2.1)

        words_per_scene = max(4, int(max_total_words / target_num_scenes))

        # If valid script sections with visual hints were provided in the contract, convert them directly
        if len(self.contract.script_sections) >= 2:
            scenes = []
            dur_per_scene = target_dur / len(self.contract.script_sections)
            for idx, sec in enumerate(self.contract.script_sections):
                hint = sec.visual_hint or f"{self.contract.title} {sec.heading}".strip()
                dur = sec.duration_seconds or dur_per_scene
                scenes.append(
                    Scene(
                        scene_index=idx + 1,
                        narration_text=sec.content,
                        visual_query=hint,
                        target_duration=round(dur, 2),
                    )
                )
            self.scenes = scenes
            self.log(f"script prepared from contract: {len(scenes)} scenes")
            return scenes

        # Use Gemini 3.1 Flash Lite for structured scene planning from sanitized VideoBrief
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if not gemini_key:
            raise RuntimeError("GEMINI_API_KEY is not set for script/scene planning.")

        from google import genai

        client = genai.Client(api_key=gemini_key)

        prompt = f"""You are an expert video director. Plan an engaging, educational video script and visual plan for:
Topic: "{topic}"
Key Narrative Points:
{key_points_text}
Tone: "{tone}"
Target Audience: "{audience}"
Target Duration: {target_dur} seconds
Aspect Ratio: {aspect_ratio}

CRITICAL RULES FOR NARRATION:
1. Write original, compelling voiceover narration about the topic.
2. STRICTLY FORBIDDEN: Do NOT repeat user instructions, commands (e.g. 'create a video', 'summarize this', 'make a 30 second video'), or meta-commentary in the narration. The voiceover must sound like a professional documentary or explainer narration.
3. Keep each narration sentence crisp, natural, educational, and engaging.

STRICT DURATION & WORD BUDGET CONSTRAINTS:
1. Target duration is {target_dur} seconds.
2. You MUST plan exactly {target_num_scenes} scenes.
3. CRITICAL: The total spoken narration across ALL {target_num_scenes} scenes COMBINED must NOT exceed {max_total_words} words total (approx {words_per_scene} words per scene).
4. Human speech pace is ~2 words per second. Writing more words will cause an unacceptable duration overrun.
5. Keep each sentence short, punchy, natural, and direct.

Each scene must have:
- scene_index: integer (1-indexed, exactly 1 to {target_num_scenes})
- narration_text: 1 crisp, natural narration sentence for voiceover (at most {words_per_scene + 2} words)
- visual_query: 2-4 simple search terms suitable for stock footage on Pexels/Pixabay (e.g. 'deep space galaxy', 'james webb telescope')
- target_duration: number of seconds (sum of all target_durations must equal {target_dur})

Output MUST be a JSON object with:
{{
  "title": "{topic}",
  "total_duration": {target_dur},
  "scenes": [ ... ]
}}
"""
        resp = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )

        try:
            data = json.loads(resp.text)
        except Exception as e:
            raise ValueError(f"Failed to parse Gemini scene plan output: {e}\nRaw: {resp.text}")

        raw_scenes = data.get("scenes", [])
        if not raw_scenes:
            raise ValueError("Gemini returned empty scenes array.")

        scenes = []
        for idx, sc in enumerate(raw_scenes):
            scenes.append(
                Scene(
                    scene_index=int(sc.get("scene_index", idx + 1)),
                    narration_text=str(sc.get("narration_text", "")).strip(),
                    visual_query=str(sc.get("visual_query", topic)).strip(),
                    target_duration=float(sc.get("target_duration", target_dur / len(raw_scenes))),
                )
            )

        self.scenes = scenes

        # Save artifacts adhering to OpenMontage schema format if artifacts directory exists
        if hasattr(self, "artifacts_dir") and self.artifacts_dir.exists():
            script_artifact = {
                "version": "1.0",
                "title": topic,
                "total_duration_seconds": target_dur,
                "sections": [
                    {
                        "id": f"sec_{s.scene_index}",
                        "text": s.narration_text,
                        "start_seconds": sum(x.target_duration for x in self.scenes[:idx]),
                        "end_seconds": sum(x.target_duration for x in self.scenes[:idx + 1]),
                    }
                    for idx, s in enumerate(self.scenes)
                ],
            }
            with open(self.artifacts_dir / "script.json", "w", encoding="utf-8") as f:
                json.dump(script_artifact, f, indent=2)

        self.log(f"script prepared: {len(scenes)} scenes planned with Gemini 3.1 Flash Lite (budget: {max_total_words} words)")
        return scenes

    def validate_script_quality(self, scenes: Optional[List[Scene]] = None) -> None:
        """Validate script quality and reject prompt leakage before TTS, downloads, or composition."""
        target_scenes = scenes if scenes is not None else self.scenes
        if not target_scenes:
            raise ValueError("Script quality gate failed: scene plan is empty.")

        raw_directive = (getattr(self.contract, "user_directive", "") or "").strip().lower()
        command_phrases = [
            "create a video", "create video", "make a video", "generate a video",
            "produce a video", "30 second video", "8 second video", "summarize this",
            "create 30 second", "create an 8-second", "create an 8 second",
            "make a 30-second", "make a 30 second", "write a video",
        ]

        total_duration = 0.0
        for s in target_scenes:
            narration = (s.narration_text or "").strip()
            if not narration or len(narration.split()) < 3:
                raise ValueError(f"Script quality gate failed: scene {s.scene_index} has empty or trivial narration: '{narration}'.")

            narration_lower = narration.lower()
            for phrase in command_phrases:
                if phrase in narration_lower:
                    raise ValueError(
                        f"Script quality gate failed: prompt leakage detected in scene {s.scene_index}. "
                        f"Narration contains command phrase '{phrase}': '{narration}'"
                    )

            if raw_directive and any(cmd in raw_directive for cmd in ("create", "make", "generate", "produce", "video", "second", "clip", "summariz")):
                if narration_lower == raw_directive or narration_lower.rstrip(".!?") == raw_directive.rstrip(".!?"):
                    raise ValueError(
                        f"Script quality gate failed: prompt leakage detected in scene {s.scene_index}. "
                        f"Narration matches user directive: '{narration}'"
                    )

            if not s.visual_query or len(s.visual_query.strip()) < 2:
                raise ValueError(f"Script quality gate failed: scene {s.scene_index} has invalid visual_query.")

            total_duration += s.target_duration

        target_dur = self.contract.target_duration_seconds
        if abs(total_duration - target_dur) > (target_dur * 0.15 + 1.0):
            raise ValueError(
                f"Script quality gate failed: total planned duration ({total_duration:.1f}s) deviates "
                f"from target duration ({target_dur:.1f}s)."
            )

    def preflight(self) -> Dict[str, Any]:
        """Perform cheap in-memory script planning and quality gate check without creating workspace or disk artifacts."""
        try:
            scenes = self.plan_script_and_scenes()
            self.validate_script_quality(scenes)
            topic = (
                getattr(self.contract.brief, "topic", None)
                if hasattr(self.contract, "brief") and self.contract.brief
                else None
            ) or self.contract.topic or self.contract.title
            return {
                "status": "READY",
                "job_id": self.contract.job_id,
                "title": self.contract.title,
                "topic": topic,
                "target_duration_seconds": self.contract.target_duration_seconds,
                "scene_count": len(scenes),
                "scenes": [
                    {
                        "scene_index": s.scene_index,
                        "narration_text": s.narration_text,
                        "visual_query": s.visual_query,
                        "target_duration": s.target_duration,
                    }
                    for s in scenes
                ],
                "voice": self.contract.voice_config.voice_id,
                "aspect_ratio": self.contract.aspect_ratio,
            }
        except Exception as exc:
            return {
                "status": "BLOCKED",
                "job_id": self.contract.job_id,
                "error": str(exc),
            }

    def generate_narration(self) -> Path:
        """Synthesize per-scene narration audio with rate convergence to enforce target duration."""
        self._ensure_tools()
        from tools.tool_registry import registry

        tts_selector = registry.get("tts_selector")
        if not tts_selector:
            raise RuntimeError("tts_selector tool not found in OpenMontage registry.")

        full_audio_path = self.audio_dir / "narration_full.mp3"

        def _synthesize_scenes(rate_str: Optional[str] = None) -> float:
            clips = []
            for scene in self.scenes:
                scene_audio_path = self.audio_dir / f"narration_scene_{scene.scene_index}.mp3"
                tts_inputs: Dict[str, Any] = {
                    "text": scene.narration_text,
                    "preferred_provider": self.contract.voice_config.provider or "edge_tts",
                    "voice": self.contract.voice_config.voice_id,
                    "voice_id": self.contract.voice_config.voice_id,
                    "pitch": self.contract.voice_config.pitch,
                    "output_path": str(scene_audio_path),
                }
                if rate_str:
                    tts_inputs["rate"] = rate_str
                else:
                    tts_inputs["speaking_rate"] = self.contract.voice_config.speed

                result = tts_selector.execute(tts_inputs)
                if not result.success:
                    raise RuntimeError(f"TTS failed for scene {scene.scene_index}: {result.error}")

                if not scene_audio_path.is_file() or scene_audio_path.stat().st_size == 0:
                    raise RuntimeError(f"TTS output missing or empty for scene {scene.scene_index}: {scene_audio_path}")

                scene.actual_audio_duration = self._probe_audio_duration(scene_audio_path)
                scene.audio_path = scene_audio_path
                clips.append(scene_audio_path)
            return sum(s.actual_audio_duration for s in self.scenes)

        # Initial pass
        total_audio = _synthesize_scenes()

        # Check against target tolerance (target_duration + 10%)
        max_allowed = self.contract.target_duration_seconds * 1.10
        if total_audio > max_allowed:
            # Calculate speech rate acceleration required to meet constraint
            ratio = total_audio / (self.contract.target_duration_seconds * 0.96)
            speed_pct = min(35, max(5, round((ratio - 1.0) * 100)))
            self.log(
                f"narration overrun detected ({total_audio:.2f}s > {max_allowed:.2f}s). "
                f"Converging with speaking rate +{speed_pct}% to fit constraint."
            )
            total_audio = _synthesize_scenes(rate_str=f"+{speed_pct}%")

        # Assemble full narration track
        audio_clips = [s.audio_path for s in self.scenes if s.audio_path]
        if len(audio_clips) == 1:
            shutil.copyfile(audio_clips[0], full_audio_path)
        else:
            concat_list = self.audio_dir / "concat_audio.txt"
            with open(concat_list, "w", encoding="utf-8") as f:
                for clip in audio_clips:
                    safe = str(clip.resolve()).replace("\\", "/")
                    f.write(f"file '{safe}'\n")

            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c", "copy",
                str(full_audio_path),
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        final_duration = self._probe_audio_duration(full_audio_path)
        self.log(f"narration generated: {len(audio_clips)} scene clips, total {final_duration:.2f}s")
        return full_audio_path

    def generate_captions(self) -> Optional[Path]:
        """Generate synchronized 1-3 word captions complying with D8.4 caption doctrine."""
        if not getattr(self.contract, "subtitles", True):
            self.log("captions skipped (subtitles disabled in contract)")
            return None

        from lib.caption_system import CaptionPipeline, validate_caption_word_limit

        pipeline = CaptionPipeline(mode="explainer")
        key_terms = self.contract.brief.key_points if self.contract.brief else []

        caption_res = pipeline.process_scenes(
            scenes=self.scenes,
            key_terms=key_terms,
        )

        # Enforce deterministic word limit validator (<= 3 words)
        validate_caption_word_limit(caption_res["raw_captions"])

        # Write artifacts
        ass_path = self.artifacts_dir / "subtitles.ass"
        srt_path = self.artifacts_dir / "subtitles.srt"
        json_path = self.artifacts_dir / "subtitles.json"

        ass_path.write_text(caption_res["ass"], encoding="utf-8")
        srt_path.write_text(caption_res["srt"], encoding="utf-8")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(caption_res["captions"], f, indent=2)

        self.subtitles_path = ass_path
        self.subtitles_srt_path = srt_path
        self.subtitles_data = caption_res
        self.log(f"captions generated: {caption_res['cue_count']} cues (all <=3 words) -> {ass_path.name}")
        return ass_path

    def acquire_visual_assets(self) -> List[Path]:
        """Download real stock video clips for each scene with Pexels/Pixabay provider routing."""
        self._ensure_tools()
        from tools.tool_registry import registry

        stock_pref = str(self.contract.options.get("stock_provider", "auto")).lower()
        pexels_tool = registry.get("pexels_video")
        pixabay_tool = registry.get("pixabay_video")

        orientation = "landscape" if self.contract.aspect_ratio == "16:9" else "portrait"
        video_paths: List[Path] = []
        providers_used = []

        for scene in self.scenes:
            scene_video_path = self.video_dir / f"scene_{scene.scene_index}.mp4"
            acquired = False

            # Provider routing logic:
            # If stock_provider == "pixabay": try pixabay_video first, then pexels_video
            # If stock_provider in ("pexels", "auto"): try pexels_video first, then pixabay_video
            provider_chain = []
            if stock_pref == "pixabay":
                if pixabay_tool and pixabay_tool.get_status().value == "available":
                    provider_chain.append(("pixabay", pixabay_tool))
                if pexels_tool and pexels_tool.get_status().value == "available":
                    provider_chain.append(("pexels", pexels_tool))
            else:
                if pexels_tool and pexels_tool.get_status().value == "available":
                    provider_chain.append(("pexels", pexels_tool))
                if pixabay_tool and pixabay_tool.get_status().value == "available":
                    provider_chain.append(("pixabay", pixabay_tool))

            if not provider_chain:
                raise RuntimeError("No stock video provider available (neither Pexels nor Pixabay). Check API keys.")

            last_error = ""
            for prov_name, tool in provider_chain:
                if prov_name == "pexels":
                    inputs = {
                        "query": scene.visual_query,
                        "orientation": orientation,
                        "per_page": 5,
                        "preferred_quality": "hd",
                        "output_path": str(scene_video_path),
                    }
                else:  # pixabay
                    inputs = {
                        "query": scene.visual_query,
                        "per_page": 5,
                        "safesearch": True,
                        "preferred_quality": "large",
                        "output_path": str(scene_video_path),
                    }

                res = tool.execute(inputs)
                if not res.success or not scene_video_path.is_file():
                    # Fallback query with contract title
                    inputs["query"] = self.contract.title
                    res = tool.execute(inputs)

                if res.success and scene_video_path.is_file() and scene_video_path.stat().st_size > 0:
                    acquired = True
                    providers_used.append(prov_name)
                    break
                else:
                    last_error = res.error or "Unknown error"

            if not acquired:
                raise RuntimeError(
                    f"Asset acquisition failed for scene {scene.scene_index} (query: '{scene.visual_query}'): {last_error}"
                )

            scene.video_path = scene_video_path
            video_paths.append(scene_video_path)

        # Record primary provider used
        self.actual_visual_provider = providers_used[0] if providers_used else "pexels"
        self.log(f"assets prepared: {len(video_paths)} clips downloaded via {self.actual_visual_provider}")
        return video_paths

    def compose_video(self, full_audio_path: Path) -> Path:
        """Compose video cuts and audio track using VideoCompose tool."""
        self._ensure_tools()
        from tools.tool_registry import registry

        video_compose = registry.get("video_compose")
        if not video_compose:
            raise RuntimeError("video_compose tool not found in OpenMontage registry.")

        # Determine target resolution
        if self.contract.aspect_ratio == "9:16":
            target_w, target_h = 1080, 1920
        elif self.contract.aspect_ratio == "1:1":
            target_w, target_h = 1080, 1080
        else:
            target_w, target_h = 1920, 1080

        # Build cuts aligned with scene narration durations
        cuts = []
        for scene in self.scenes:
            cut_duration = scene.actual_audio_duration if scene.actual_audio_duration > 0 else scene.target_duration
            cuts.append({
                "id": f"cut_{scene.scene_index}",
                "source": str(scene.video_path.resolve()),
                "in_seconds": 0.0,
                "out_seconds": round(cut_duration, 3),
            })

        edit_decisions = {
            "version": "1.0",
            "render_runtime": "ffmpeg",
            "cuts": cuts,
            "metadata": {
                "compose_target": {
                    "width": target_w,
                    "height": target_h,
                    "fit": "pad",
                }
            },
        }

        # Save edit_decisions artifact
        with open(self.artifacts_dir / "edit_decisions.json", "w", encoding="utf-8") as f:
            json.dump(edit_decisions, f, indent=2)

        self.log("composition started")
        inputs = {
            "operation": "compose",
            "edit_decisions": edit_decisions,
            "audio_path": str(full_audio_path.resolve()),
            "output_path": str(self.final_mp4.resolve()),
        }

        # Check for generated subtitles
        subtitle_path = getattr(self, "subtitles_path", None)
        if subtitle_path and subtitle_path.is_file():
            inputs["subtitle_path"] = str(subtitle_path.resolve())
            edit_decisions["subtitles"] = {
                "source": str(subtitle_path.resolve()),
                "format": "ass",
                "style": {
                    "font": "Roboto",
                    "font_size": 36,
                    "margin_v": 48,
                    "alignment": 2,
                },
            }

        result = video_compose.execute(inputs)
        if not result.success or not self.final_mp4.is_file():
            raise RuntimeError(f"Video composition failed: {result.error}")

        self.log(f"composition completed: {self.final_mp4.name}")
        return self.final_mp4

    def validate_output(self) -> Dict[str, Any]:
        """Strictly validate final MP4 using ffprobe and compute SHA-256."""
        if not self.final_mp4.is_file():
            raise FileNotFoundError(f"Final MP4 file does not exist: {self.final_mp4}")

        size_bytes = self.final_mp4.stat().st_size
        if size_bytes == 0:
            raise ValueError("Final MP4 file is empty (0 bytes).")

        # Compute SHA-256
        sha256_hash = hashlib.sha256()
        with open(self.final_mp4, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256_hash.update(chunk)
        digest = sha256_hash.hexdigest()

        # Run ffprobe media inspection
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(self.final_mp4),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        probe_data = json.loads(proc.stdout)

        fmt = probe_data.get("format", {})
        streams = probe_data.get("streams", [])

        # Verify container
        format_name = fmt.get("format_name", "")
        if not any(ext in format_name for ext in ("mp4", "mov", "quicktime")):
            raise ValueError(f"Invalid video container format: {format_name}")

        duration_sec = float(fmt.get("duration", 0.0))
        if duration_sec <= 0:
            raise ValueError(f"Invalid video duration: {duration_sec}")

        # Strict duration constraint enforcement (target_duration + 10%)
        max_allowed_dur = self.contract.target_duration_seconds * 1.10
        if duration_sec > max_allowed_dur:
            raise ValueError(
                f"Final video duration ({duration_sec:.2f}s) exceeded constraint "
                f"(target={self.contract.target_duration_seconds}s + 10% = {max_allowed_dur:.2f}s)."
            )

        # Verify video stream
        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        if not video_streams:
            raise ValueError("Final output does not contain any video stream.")

        v_stream = video_streams[0]
        width = int(v_stream.get("width", 0))
        height = int(v_stream.get("height", 0))
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid video dimensions: {width}x{height}")

        # Check audio stream if present
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        has_audio = len(audio_streams) > 0

        self.log(
            f"output validated: size={size_bytes}B, duration={duration_sec:.2f}s, "
            f"res={width}x{height}, sha256={digest[:16]}..."
        )

        return {
            "path": str(self.final_mp4.resolve()),
            "filename": self.final_mp4.name,
            "mime_type": "video/mp4",
            "size_bytes": size_bytes,
            "duration_seconds": round(duration_sec, 2),
            "sha256": digest,
            "width": width,
            "height": height,
            "video_codec": v_stream.get("codec_name"),
            "audio_codec": audio_streams[0].get("codec_name") if has_audio else None,
            "has_audio": has_audio,
        }

    def _probe_audio_duration(self, audio_path: Path) -> float:
        """Helper to get exact duration in seconds from an audio file."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        out = subprocess.check_output(cmd, text=True).strip()
        try:
            return float(out)
        except ValueError:
            return 0.0

    def execute(self) -> Dict[str, Any]:
        """Run all pipeline stages and return machine-readable result schema."""
        try:
            self.tracker.run_stage("workspace_init", self.init_workspace)
            self.tracker.run_stage("script_planning", self.plan_script_and_scenes)
            self.tracker.run_stage("quality_gate", lambda: self.validate_script_quality(self.scenes))
            full_audio = self.tracker.run_stage("narration_generation", self.generate_narration)
            self.tracker.run_stage("caption_generation", self.generate_captions)
            self.tracker.run_stage("asset_acquisition", self.acquire_visual_assets)
            self.tracker.run_stage("video_composition", self.compose_video, full_audio)
            output_info = self.tracker.run_stage("output_validation", self.validate_output)

            result = {
                "success": True,
                "job_id": self.contract.job_id,
                "project_id": self.project_dir.name,
                "status": "completed",
                "output": output_info,
                "stages": [s.to_dict() for s in self.tracker.stages],
                "metadata": {
                    "title": self.contract.title,
                    "tts_provider": self.contract.voice_config.provider,
                    "voice": self.contract.voice_config.voice_id,
                    "visual_provider": self.actual_visual_provider,
                    "requested_duration_seconds": self.contract.target_duration_seconds,
                    "actual_duration_seconds": output_info["duration_seconds"],
                    "has_subtitles": hasattr(self, "subtitles_path") and self.subtitles_path is not None,
                    "caption_cues": getattr(self, "subtitles_data", {}).get("cue_count", 0),
                    "duration_overrun_pct": round(
                        ((output_info["duration_seconds"] - self.contract.target_duration_seconds) / self.contract.target_duration_seconds) * 100,
                        1,
                    ),
                    "scene_count": len(self.scenes),
                    "aspect_ratio": self.contract.aspect_ratio,
                    "render_runtime": "ffmpeg",
                },
            }

            # Save result to workspace
            with open(self.project_dir / "result.json", "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)

            return result

        except Exception as exc:
            err_code = "PIPELINE_ERROR"
            safe_msg = str(exc)
            # Sanitize safe user-facing message
            if "not set" in safe_msg.lower() or "key" in safe_msg.lower():
                err_code = "CONFIGURATION_ERROR"
            elif "not found" in safe_msg.lower() or "empty" in safe_msg.lower():
                err_code = "MEDIA_NOT_FOUND"

            result = {
                "success": False,
                "job_id": self.contract.job_id,
                "status": "failed",
                "error": {
                    "code": err_code,
                    "message": safe_msg,
                },
                "stages": [s.to_dict() for s in self.tracker.stages],
            }
            return result


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenMontage Isolated Runner for Limo")
    parser.add_argument(
        "--contract",
        required=True,
        help="Path to JSON contract file OR inline JSON string",
    )
    parser.add_argument(
        "--output-json",
        help="Optional path to write machine-readable result JSON",
    )
    parser.add_argument(
        "--work-dir",
        help="Optional workspace directory override",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Run cheap in-memory script planning and quality gate check without creating workspace or disk artifacts",
    )

    args = parser.parse_args()

    # Load environment safely
    safe_init_env()

    # Parse contract
    contract_arg = args.contract.strip()
    try:
        if contract_arg.startswith("{") and contract_arg.endswith("}"):
            raw_contract = json.loads(contract_arg)
        else:
            contract_path = Path(contract_arg).resolve()
            if not contract_path.is_file():
                err_res = {
                    "success": False,
                    "status": "failed",
                    "error": {
                        "code": "CONTRACT_NOT_FOUND",
                        "message": f"Contract file not found: {contract_path}",
                    },
                }
                print(json.dumps(err_res, indent=2))
                return 1
            with open(contract_path, "r", encoding="utf-8") as f:
                raw_contract = json.load(f)

        contract = validate_contract_dict(raw_contract)
    except Exception as e:
        err_res = {
            "success": False,
            "status": "failed",
            "error": {
                "code": "INVALID_CONTRACT",
                "message": f"Contract validation failed: {e}",
            },
        }
        print(json.dumps(err_res, indent=2))
        return 1

    work_dir = Path(args.work_dir).resolve() if args.work_dir else None

    # Run execution or preflight
    runner = LimoRunner(contract=contract, work_dir=work_dir)
    if args.preflight:
        result = runner.preflight()
        if args.output_json:
            out_p = Path(args.output_json).resolve()
            out_p.parent.mkdir(parents=True, exist_ok=True)
            with open(out_p, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") == "READY" else 1

    result = runner.execute()

    # Write output JSON if requested
    if args.output_json:
        out_p = Path(args.output_json).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

    # Print machine-readable JSON to stdout
    print(json.dumps(result, indent=2))

    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
