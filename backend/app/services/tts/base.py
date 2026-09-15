"""Base contract for Limo Text-to-Speech (TTS) Provider Adapters (Phase D8.3)."""

from abc import ABC, abstractmethod
import hashlib
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional

from .models import TTSRequest, TTSResult, VoiceMetadata


def compute_audio_sha256(file_path: Path) -> str:
    """Compute deterministic SHA-256 hash over an audio file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def probe_audio_duration(file_path: Path) -> Optional[float]:
    """Probe audio duration in seconds using ffprobe, with graceful fallback."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path.resolve()),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip():
            return round(float(res.stdout.strip()), 3)
    except Exception:
        pass
    return None


class BaseTTSProvider(ABC):
    """Abstract interface defining the universal contract for all TTS providers."""

    id: str
    name: str
    is_primary: bool = True

    @abstractmethod
    def get_status(self) -> bool:
        """Check whether provider credentials and binaries are available without crashing or leaking secrets."""
        pass

    @abstractmethod
    def list_voices(self) -> List[VoiceMetadata]:
        """Return static or cached list of supported voices for this provider."""
        pass

    def validate_voice(self, voice_id: str) -> bool:
        """Verify whether a given voice_id is supported by this provider."""
        voices = self.list_voices()
        v_clean = voice_id.strip().lower()
        return any(v.voice_id.lower() == v_clean or v.display_name.lower() == v_clean for v in voices)

    def resolve_voice_id(self, voice: str) -> str:
        """Resolve an alias or display name to canonical provider voice_id."""
        v_clean = voice.strip().lower()
        for v in self.list_voices():
            if v.voice_id.lower() == v_clean or v.display_name.lower() == v_clean:
                return v.voice_id
        return voice.strip()

    @abstractmethod
    def synthesize(self, request: TTSRequest) -> TTSResult:
        """Execute real audio synthesis and return standardized TTSResult."""
        pass
