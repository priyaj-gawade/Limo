"""Abstract provider adapter decoupling LLMProviderManager from specific vendors."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..models import LLMResponse


class ProviderAPIError(Exception):
    """Base exception for provider API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, route_key: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.route_key = route_key


class RateLimitExceededError(ProviderAPIError):
    """Raised on HTTP 429 or quota exhaustion."""
    pass


class ProviderServerError(ProviderAPIError):
    """Raised on transient 5xx server errors."""
    pass


class AuthenticationError(ProviderAPIError):
    """Raised on 401 or 403 authorization failures."""
    pass


class ModelNotFoundError(ProviderAPIError):
    """Raised on 404 model not found or deprecated."""
    pass


class BaseProviderAdapter(ABC):
    """Vendor-neutral adapter contract for model inference and function calling."""

    provider_name: str

    @abstractmethod
    async def generate(
        self,
        model_name: str,
        api_key: str,
        prompt: str,
        system_instruction: Optional[str] = None,
        tools_declarations: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
        timeout_sec: float = 30.0,
        response_mime_type: Optional[str] = None,
        response_schema: Optional[Any] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Execute inference against real provider SDK or endpoint."""
        pass
