"""TTS Provider Registry and Deterministic Voice Resolution Engine (Phase D8.3)."""

import logging
from typing import Any, Dict, List, Optional, Tuple

from ...config import settings
from .adapters import AzureTTSAdapter, EdgeTTSAdapter, OpenAITTSAdapter, PiperTTSAdapter
from .base import BaseTTSProvider
from .models import (
    InvalidVoiceError,
    TTSProviderUnavailableError,
    VoiceMetadata,
)

logger = logging.getLogger("limo.services.tts.registry")


class TTSProviderRegistry:
    """Central registry for TTS providers and deterministic voice resolution."""

    def __init__(self) -> None:
        self._providers: Dict[str, BaseTTSProvider] = {}
        # Register primary providers
        self.register_provider(AzureTTSAdapter())
        self.register_provider(OpenAITTSAdapter())
        self.register_provider(PiperTTSAdapter())
        # Register fallback provider
        self.register_provider(EdgeTTSAdapter())

    def register_provider(self, provider: BaseTTSProvider) -> None:
        """Register a TTS provider adapter."""
        self._providers[provider.id.lower()] = provider

    def get_provider(self, provider_id: str) -> Optional[BaseTTSProvider]:
        """Fetch provider adapter by ID."""
        return self._providers.get(provider_id.lower())

    def list_providers(self) -> List[BaseTTSProvider]:
        """List all registered providers in priority order (primary first, then fallback)."""
        return sorted(list(self._providers.values()), key=lambda p: (not p.is_primary, p.id))

    def list_all_voices(self) -> List[VoiceMetadata]:
        """Aggregate voices across all registered providers with live availability status."""
        catalog: List[VoiceMetadata] = []
        for provider in self.list_providers():
            catalog.extend(provider.list_voices())
        return catalog

    def get_cached_catalog(self) -> List[Dict[str, Any]]:
        """Return cached voice catalog representation for fast API consumption."""
        default_prov = (getattr(settings, "default_tts_provider", None) or "azure").lower()
        default_vc = (getattr(settings, "default_tts_voice", None) or "en-US-AndrewMultilingualNeural").lower()

        voices = self.list_all_voices()
        result = []
        for v in voices:
            v_dict = v.model_dump()
            # Mark default according to runtime settings
            v_dict["is_configured_default"] = (
                v.provider.lower() == default_prov and (
                    v.voice_id.lower() == default_vc or v.display_name.lower() == default_vc
                )
            )
            result.append(v_dict)
        return result

    def resolve_voice(
        self,
        voice_id: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Tuple[BaseTTSProvider, VoiceMetadata]:
        """Deterministically resolve provider adapter and voice metadata.
        
        Guarantees:
        1. Explicit provider + voice wins. If invalid for that provider -> raises InvalidVoiceError.
        2. Explicit voice without provider -> resolves provider hosting that voice.
        3. Configured default provider/voice if none specified.
        4. If configured provider unavailable -> falls back deterministically to available fallback provider.
        5. NEVER silently swaps an explicit voice to an unrelated voice.
        """
        # Case 1: Explicit provider requested
        if provider:
            prov_key = provider.strip().lower()
            p_adapter = self.get_provider(prov_key)
            if not p_adapter:
                raise TTSProviderUnavailableError(f"TTS provider '{provider}' is not registered.")

            if not p_adapter.get_status():
                raise TTSProviderUnavailableError(
                    f"Requested TTS provider '{p_adapter.name}' ({p_adapter.id}) is unavailable. "
                    f"Check required environment variables or binary installation."
                )

            voices = p_adapter.list_voices()
            if voice_id:
                clean_v = voice_id.strip().lower()
                target_meta = next(
                    (v for v in voices if v.voice_id.lower() == clean_v or v.display_name.lower() == clean_v),
                    None,
                )
                if not target_meta:
                    raise InvalidVoiceError(
                        f"Voice '{voice_id}' is not valid for provider '{p_adapter.name}'. "
                        f"Available voices: {', '.join(v.display_name for v in voices)}"
                    )
                return p_adapter, target_meta
            else:
                # Use provider's default voice
                target_meta = next((v for v in voices if v.is_default), voices[0])
                return p_adapter, target_meta

        # Case 2: Voice specified without provider
        if voice_id:
            clean_v = voice_id.strip().lower()
            candidates: List[Tuple[BaseTTSProvider, VoiceMetadata]] = []
            for p in self.list_providers():
                for v in p.list_voices():
                    if v.voice_id.lower() == clean_v or v.display_name.lower() == clean_v:
                        candidates.append((p, v))

            if not candidates:
                raise InvalidVoiceError(
                    f"Unknown voice '{voice_id}'. Voice does not exist in any registered provider."
                )

            # Prioritize available provider among candidates
            available_candidate = next((c for c in candidates if c[0].get_status()), None)
            if available_candidate:
                return available_candidate
            else:
                # Provider exists for voice but is unconfigured
                cand_prov = candidates[0][0]
                raise TTSProviderUnavailableError(
                    f"Voice '{voice_id}' belongs to provider '{cand_prov.name}', which is currently unavailable. "
                    f"Set credentials or install binary to activate."
                )

        # Case 3: Neither provider nor voice specified -> Use configured defaults
        default_prov_name = getattr(settings, "default_tts_provider", "azure").lower()
        default_voice_name = getattr(settings, "default_tts_voice", "en-US-AndrewMultilingualNeural").lower()

        default_adapter = self.get_provider(default_prov_name)
        if default_adapter and default_adapter.get_status():
            voices = default_adapter.list_voices()
            meta = next(
                (v for v in voices if v.voice_id.lower() == default_voice_name or v.display_name.lower() == default_voice_name),
                None,
            ) or next((v for v in voices if v.is_default), voices[0])
            return default_adapter, meta

        # Configured primary unavailable -> Fallback to available provider (Edge TTS)
        for p in self.list_providers():
            if p.get_status():
                voices = p.list_voices()
                meta = next((v for v in voices if v.is_default), voices[0])
                logger.info(
                    "Configured TTS provider '%s' unavailable. Deterministically using fallback provider '%s' (%s)",
                    default_prov_name,
                    p.id,
                    meta.voice_id,
                )
                return p, meta

        raise TTSProviderUnavailableError(
            "No TTS provider is currently available on the system. "
            "Please configure AZURE_SPEECH_KEY, OPENAI_API_KEY, install piper, or install edge-tts."
        )


tts_registry = TTSProviderRegistry()
