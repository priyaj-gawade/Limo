"""Voice catalog and standalone TTS synthesis API endpoints (Phase D8.3)."""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ...config import settings
from ...models.artifact import Artifact
from ...services.tts.models import (
    InvalidVoiceError,
    TTSProviderUnavailableError,
    TTSSynthesisError,
)
from ...services.tts.registry import tts_registry
from ...services.tts.service import tts_service

logger = logging.getLogger("limo.api.v1.voices")
router = APIRouter(prefix="/voices", tags=["voices"])


class VoiceCatalogResponse(BaseModel):
    default_provider: str = Field(description="Currently configured default provider ID")
    default_voice: str = Field(description="Currently configured default voice ID")
    voices: List[Dict[str, Any]] = Field(description="Curated voice catalog across primary and fallback providers")


class SynthesizeVoiceRequest(BaseModel):
    text: str = Field(min_length=1, description="Narration text to synthesize")
    voice: Optional[str] = Field(default=None, description="Voice ID or display name")
    provider: Optional[str] = Field(default=None, description="TTS provider ID ('azure', 'openai', 'piper', 'edge_tts')")
    speed: float = Field(default=1.0, ge=0.25, le=4.0, description="Speech rate multiplier")
    title: Optional[str] = Field(default=None, description="Optional custom title for the audio deliverable")
    project_id: Optional[str] = Field(default=None, description="Project ID for provenance")
    session_id: Optional[str] = Field(default=None, description="Chat session ID for provenance")


@router.get("", response_model=VoiceCatalogResponse)
async def get_voice_catalog() -> VoiceCatalogResponse:
    """Retrieve pre-resolved voice catalog with availability status.
    
    Fast in-memory resolution with zero credential leakage.
    """
    default_prov = getattr(settings, "default_tts_provider", "azure")
    default_vc = getattr(settings, "default_tts_voice", "en-US-AndrewMultilingualNeural")
    catalog = tts_registry.get_cached_catalog()

    return VoiceCatalogResponse(
        default_provider=default_prov,
        default_voice=default_vc,
        voices=catalog,
    )


@router.post("/synthesize", response_model=Artifact, status_code=status.HTTP_201_CREATED)
async def synthesize_speech(req: SynthesizeVoiceRequest) -> Artifact:
    """Standalone TTS endpoint generating real audio artifact with duration, SHA-256, and metadata."""
    try:
        artifact = tts_service.synthesize(
            text=req.text,
            voice=req.voice,
            provider=req.provider,
            speed=req.speed,
            title=req.title,
            project_id=req.project_id,
            session_id=req.session_id,
        )
        return artifact
    except InvalidVoiceError as e:
        logger.warning("Invalid voice request: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except TTSProviderUnavailableError as e:
        logger.warning("TTS provider unavailable: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except TTSSynthesisError as e:
        logger.error("TTS synthesis error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Speech synthesis failed: {str(e)}",
        )
    except Exception as e:
        logger.error("Unexpected error in speech synthesis endpoint: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to synthesize audio: {str(e)}",
        )
