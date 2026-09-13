"""Comprehensive automated verification suite for Phase D4.7: LLMProviderManager and resilient inference."""

import asyncio
import pytest
from typing import Any, Dict, List, Optional

from app.agent.actions import ActionType
from app.agent.brain import LLMReasoningEngine
from app.agent.context import AgentContext
from app.agent.contracts import AgentState
from app.agent.llm.adapters.base import (
    BaseProviderAdapter,
    ModelNotFoundError,
    ProviderServerError,
    RateLimitExceededError,
)
from app.agent.llm.manager import AllRoutesExhaustedError, LLMProviderManager
from app.agent.llm.models import FunctionCallPayload, LLMResponse, ModelQuota, ProviderCredential, RouteKey
from app.agent.llm.quota import QuotaTracker
from app.agent.runtime import LimoAgentRuntime
from app.agent.tools.source_tool import SourceReadTool
from app.config import settings
from app.services.chat_service import chat_service


class MockProviderAdapter(BaseProviderAdapter):
    """Isolated test adapter simulating various provider error responses."""

    provider_name = "test_mock"

    def __init__(self):
        self.call_history: List[Dict[str, Any]] = []
        self.error_sequence: Dict[str, List[Exception]] = {}
        self.mock_responses: Dict[str, LLMResponse] = {}

    def queue_error(self, model_name: str, error: Exception) -> None:
        if model_name not in self.error_sequence:
            self.error_sequence[model_name] = []
        self.error_sequence[model_name].append(error)

    def set_mock_response(self, model_name: str, response: LLMResponse) -> None:
        self.mock_responses[model_name] = response

    async def generate(
        self,
        model_name: str,
        api_key: str,
        prompt: str,
        system_instruction: Optional[str] = None,
        tools_declarations: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
        timeout_sec: float = 30.0,
        **kwargs: Any,
    ) -> LLMResponse:
        self.call_history.append({
            "model": model_name,
            "api_key": api_key,
            "prompt": prompt,
        })

        if model_name in self.error_sequence and self.error_sequence[model_name]:
            err = self.error_sequence[model_name].pop(0)
            raise err

        if model_name in self.mock_responses:
            return self.mock_responses[model_name]

        return LLMResponse(
            text="Mock successful response",
            input_tokens=20,
            output_tokens=10,
            total_tokens=30,
            latency_sec=0.05,
        )


# 1. Model selection
def test_model_selection_and_chain():
    mgr = LLMProviderManager(
        credentials=[ProviderCredential(id="c1", project_id="p1", api_key="k1")],
        primary_model="gemini-3.5-flash-lite",
        fallback_models=["gemini-3.1-flash-lite"],
    )
    chain = mgr.get_model_chain()
    assert chain == ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]

    route = mgr.select_route()
    assert route is not None
    assert route.model_name == "gemini-3.5-flash-lite"
    assert route.project_id == "p1"
    assert route.credential_id == "c1"


# 2. RPM/TPM/RPD Accounting (MUST-FIX #5)
def test_quota_tracker_rpm_tpm_rpd_accounting():
    tracker = QuotaTracker()
    route = RouteKey(project_id="p1", credential_id="c1", model_name="gemini-3.5-flash-lite")

    # Initial state
    assert tracker.has_capacity(route) is True

    # Record usage with input/output distinction
    tracker.record_usage(route, input_tokens=100, output_tokens=50)
    metrics = tracker.get_route_metrics(route)

    assert metrics["rpm_1m"] == 1
    assert metrics["input_tpm_1m"] == 100
    assert metrics["output_tpm_1m"] == 50
    assert metrics["total_tpm_1m"] == 150
    assert metrics["rpd_24h"] == 1


# 3. 429 Handling and Authoritative Cooldown Override (MUST-FIX #3)
@pytest.mark.asyncio
async def test_429_handling_and_cooldown_override():
    adapter = MockProviderAdapter()
    tracker = QuotaTracker()
    cred1 = ProviderCredential(id="c1", project_id="p1", api_key="k1")
    cred2 = ProviderCredential(id="c2", project_id="p2", api_key="k2")

    mgr = LLMProviderManager(
        credentials=[cred1, cred2],
        primary_model="gemini-3.5-flash-lite",
        adapter=adapter,
        quota_tracker=tracker,
        cooldown_duration_sec=30.0,
        max_retries=2,
    )

    # Queue a 429 error on first attempt
    adapter.queue_error("gemini-3.5-flash-lite", RateLimitExceededError("Rate limit exceeded", status_code=429))

    # Generate request should hit 429 on cred1, engage cooldown, and failover to cred2
    res = await mgr.generate(prompt="Hello")
    assert res.text == "Mock successful response"
    assert mgr._total_failovers == 1

    # Verify first route is in cooldown
    route1 = RouteKey(project_id="p1", credential_id="c1", model_name="gemini-3.5-flash-lite")
    assert tracker.is_in_cooldown(route1) is True


# 4. 5xx Transient Error Retry
@pytest.mark.asyncio
async def test_5xx_transient_error_retry():
    adapter = MockProviderAdapter()
    cred = ProviderCredential(id="c1", project_id="p1", api_key="k1")

    mgr = LLMProviderManager(
        credentials=[cred],
        primary_model="gemini-3.5-flash-lite",
        adapter=adapter,
        max_retries=2,
    )

    # Queue transient 503 error then succeed
    adapter.queue_error("gemini-3.5-flash-lite", ProviderServerError("Service Unavailable", status_code=503))

    res = await mgr.generate(prompt="Hello")
    assert res.text == "Mock successful response"
    assert mgr._total_retries >= 1


# 5. Timeout Handling
@pytest.mark.asyncio
async def test_timeout_handling():
    adapter = MockProviderAdapter()
    cred = ProviderCredential(id="c1", project_id="p1", api_key="k1")

    mgr = LLMProviderManager(
        credentials=[cred],
        primary_model="gemini-3.5-flash-lite",
        adapter=adapter,
        max_retries=1,
    )

    adapter.queue_error("gemini-3.5-flash-lite", TimeoutError("Request timed out"))
    res = await mgr.generate(prompt="Hello")
    assert res.text == "Mock successful response"
    assert mgr._total_retries >= 1


# 6. Model Fallback Chain
@pytest.mark.asyncio
async def test_model_fallback_chain():
    adapter = MockProviderAdapter()
    tracker = QuotaTracker()
    cred = ProviderCredential(id="c1", project_id="p1", api_key="k1")

    mgr = LLMProviderManager(
        credentials=[cred],
        primary_model="gemini-3.5-flash-lite",
        fallback_models=["gemini-3.1-flash-lite"],
        adapter=adapter,
        quota_tracker=tracker,
        cooldown_duration_sec=60.0,
        max_retries=2,
    )

    # Put primary model in cooldown
    primary_route = RouteKey(project_id="p1", credential_id="c1", model_name="gemini-3.5-flash-lite")
    tracker.record_rate_limit(primary_route, cooldown_sec=60.0)

    # Request should automatically select fallback model
    res = await mgr.generate(prompt="Hello fallback")
    assert "gemini-3.1-flash-lite" in res.route_key


# 7. No Infinite Retry Loops (Bounded Retries)
@pytest.mark.asyncio
async def test_no_infinite_retry_loops():
    adapter = MockProviderAdapter()
    cred = ProviderCredential(id="c1", project_id="p1", api_key="k1")

    mgr = LLMProviderManager(
        credentials=[cred],
        primary_model="gemini-3.5-flash-lite",
        fallback_models=[],
        adapter=adapter,
        max_retries=2,
    )

    # Queue infinite errors
    for _ in range(5):
        adapter.queue_error("gemini-3.5-flash-lite", ProviderServerError("Internal Error", status_code=500))

    with pytest.raises(Exception):
        await mgr.generate(prompt="Loop test")

    # Confirms attempts were bounded (1 initial + 2 retries = 3 attempts max)
    assert len(adapter.call_history) <= 3


# 8. Secret Redaction
def test_secret_redaction():
    fake_key = "FAKE_MOCK_API_KEY_FOR_TESTING_PURPOSES_ONLY_9999"
    cred = ProviderCredential(id="c_test", project_id="proj_secret", api_key=fake_key)
    masked = cred.masked_key

    # Secret is masked (first 6 and last 4 chars shown, center masked)
    assert "FAKE_M" in masked
    assert "9999" in masked
    assert "TESTING_PURPOSES" not in masked

    mgr = LLMProviderManager(credentials=[cred])
    diag = mgr.get_diagnostics()
    assert diag["credentials"][0]["masked_key"] == masked
    # Full key is never exposed in diagnostics dict
    assert fake_key not in str(diag)



# 9. Function Calling & Tool Execution via LLMReasoningEngine
@pytest.mark.asyncio
async def test_reasoning_engine_tool_call_mapping():
    adapter = MockProviderAdapter()
    adapter.set_mock_response(
        "gemini-3.5-flash-lite",
        LLMResponse(
            text=None,
            function_calls=[FunctionCallPayload(name="source_read", args={"source_id": "src_123"}, id="fc_1")],
            total_tokens=40,
        ),
    )
    mgr = LLMProviderManager(
        credentials=[ProviderCredential(id="c1", project_id="p1", api_key="k1")],
        primary_model="gemini-3.5-flash-lite",
        adapter=adapter,
    )
    engine = LLMReasoningEngine(provider_manager=mgr)
    ctx = AgentContext(session_id="sess_fc", user_request="Read source src_123")

    action = await engine.decide(ctx, [SourceReadTool()])
    assert action.action_type == ActionType.TOOL_CALL
    assert len(action.tool_calls) == 1
    assert action.tool_calls[0].tool_name == "source_read"
    assert action.tool_calls[0].arguments["source_id"] == "src_123"


# 10. Real generic Limo chat turn with Gemini model -> ChatService persistence
@pytest.mark.asyncio
async def test_real_gemini_generic_chat_turn():
    """Final real integration test: Limo Chat -> LLMReasoningEngine -> real Gemini model -> ChatService persistence."""
    if not settings.gemini_key_1:
        pytest.skip("GEMINI_KEY_1 not configured in environment")

    # Create real chat session
    session = chat_service.create_session(title="D4.7 Real Gemini Verification")
    runtime = LimoAgentRuntime()

    # Execute real conversational turn
    assistant_msg = await runtime.execute_turn(
        session_id=session.id,
        user_prompt="Say exactly: Antigravity verification confirmed.",
    )

    assert assistant_msg is not None
    assert assistant_msg.session_id == session.id
    assert assistant_msg.role.value == "assistant"
    assert len(assistant_msg.content.strip()) > 0
    assert assistant_msg.execution_summary is not None
    assert "gemini" in assistant_msg.execution_summary.lower()

    # Verify message was persisted to SQLite history
    history = chat_service.get_history(session.id)
    assert len(history) == 2  # 1 User turn + 1 Assistant turn
    assert history[0].role.value == "user"
    assert history[1].role.value == "assistant"

    # Clean up test session
    chat_service.delete_session(session.id)
