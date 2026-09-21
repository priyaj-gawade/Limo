from pathlib import Path
from typing import Any, List, Optional, Union
import dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ensure .env is loaded into os.environ regardless of working directory
dotenv.load_dotenv()
dotenv.load_dotenv("../.env")


class Settings(BaseSettings):
    """Centralized configuration for Limo backend."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

    # Core Application
    app_name: str = "Limo Backend Engine"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True
    host: str = "127.0.0.1"
    port: int = 8000

    # LLM Provider Configuration (Phase D4.7)
    gemini_key_1: Optional[str] = None
    gemini_key_2: Optional[str] = None
    gemini_key_3: Optional[str] = None
    gemini_api_key: Optional[str] = None
    gemini_api_keys: Optional[str] = None
    primary_model: str = "gemini-3.5-flash-lite"
    fallback_models: List[str] = ["gemini-3.1-flash-lite"]
    llm_max_retries: int = 3
    llm_cooldown_duration_sec: float = 60.0
    llm_timeout_sec: float = 30.0
    llm_safety_margin: float = 1.0
    default_retrieval_token_budget: int = 2000

    # Web & Internet Reach Configuration (Phase D8.9)
    web_search_provider: str = "ddgs"
    google_search_api_key: Optional[str] = None
    google_csx_id: Optional[str] = None
    youtube_api_key: Optional[str] = None
    # Direct Content Extraction (Trafilatura + Crawl4AI fallback)
    web_crawl_timeout_sec: int = 15

    # TTS & Voice Layer Configuration (Phase D8.3)
    default_tts_provider: str = "azure"
    default_tts_voice: str = "en-US-AndrewMultilingualNeural"

    # Logging
    log_level: str = "INFO"

    # Storage & Surface Boundaries
    limo_surface: str = "desktop"  # "desktop" or "web"
    database_url: Optional[str] = None
    data_dir: str = "data"
    db_name: str = "limo.db"

    @property
    def db_path(self) -> Path:
        """Resolve full filesystem path to primary SQLite database."""
        return Path(self.data_dir) / self.db_name

    @property
    def database_engine(self) -> str:
        """Resolve database engine type ('sqlite' or 'postgres')."""
        if self.limo_surface.lower() == "web" or (self.database_url and "postgres" in self.database_url.lower()):
            return "postgres"
        return "sqlite"

    # Web Authentication & OAuth
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_redirect_uri: Optional[str] = None
    frontend_url: str = "http://localhost:5190"
    session_secret: str = "limo-insecure-session-secret-change-in-prod"
    auth_cookie_name: str = "limo_session"
    session_ttl_days: int = 30

    # Turbo Worker Offload Architecture
    worker_token: Optional[str] = None
    turbo_worker_url: Optional[str] = None
    heavy_worker_timeout_sec: int = 300

    # CORS origins for local desktop/Electron environment
    cors_origins: Union[List[str], str] = [
        "http://localhost:5190",
        "http://127.0.0.1:5190",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            clean = v.strip()
            if clean == "*":
                return ["*"]
            if clean.startswith("[") and clean.endswith("]"):
                import json
                try:
                    return json.loads(clean)
                except Exception:
                    pass
            return [x.strip() for x in clean.split(",") if x.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"


# Global singleton settings instance
settings = Settings()
