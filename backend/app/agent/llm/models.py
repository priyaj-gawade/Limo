"""Data models for LLM credentials, routes, quotas, and responses."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class RouteKey:
    """Routing identity combining Google project, credential ID, and model (MUST-FIX #1)."""
    project_id: str
    credential_id: str
    model_name: str

    def to_string(self) -> str:
        return f"{self.project_id}:{self.credential_id}:{self.model_name}"

    def __str__(self) -> str:
        return self.to_string()


class ProviderCredential(BaseModel):
    """Container for an authorized provider credential."""
    id: str
    project_id: str
    api_key: str
    is_active: bool = True

    @property
    def masked_key(self) -> str:
        """Safe non-secret key representation for logs and CLI."""
        if len(self.api_key) <= 10:
            return "***"
        return f"{self.api_key[:6]}...{self.api_key[-4:]}"


class ModelQuota(BaseModel):
    """Configurable rate and volume quotas per model (MUST-FIX #2 & #3)."""
    rpm: int = Field(default=15, description="Requests per minute ceiling")
    tpm: int = Field(default=250000, description="Tokens per minute ceiling")
    rpd: int = Field(default=500, description="Requests per day ceiling")
    safety_margin: float = Field(default=0.9, ge=0.5, le=1.0, description="Preflight safety factor")

    @property
    def safe_rpm(self) -> int:
        return int(self.rpm * self.safety_margin)

    @property
    def safe_tpm(self) -> int:
        return int(self.tpm * self.safety_margin)

    @property
    def safe_rpd(self) -> int:
        return int(self.rpd * self.safety_margin)


class UsageRecord(BaseModel):
    """Timestamped record distinguishing input, output, and total tokens (MUST-FIX #5)."""
    timestamp: float
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class FunctionCallPayload(BaseModel):
    """Standardized tool invocation payload returned by an LLM adapter."""
    name: str
    args: Dict[str, Any] = Field(default_factory=dict)
    id: Optional[str] = None


class LLMResponse(BaseModel):
    """Structured response returned by an LLM adapter with usage metrics."""
    text: Optional[str] = None
    function_calls: List[FunctionCallPayload] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    latency_sec: float = 0.0
    route_key: str = ""
    retries_used: int = 0
