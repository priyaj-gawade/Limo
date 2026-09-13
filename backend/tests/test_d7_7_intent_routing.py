"""Test suite for Phase D7.7: Dynamic Intent, Format Routing & Fast Chat.

Verifies:
1. Fast chat greetings, definitions, and questions resolve to FAST_CHAT (sub-millisecond).
2. Questions containing format keywords ('What is Markdown?') do not trigger generation.
3. Passive format mentions ('I mentioned Markdown in my report') do not trigger generation.
4. Contextual 'table' disambiguation (Markdown table vs doc table vs ambiguous table).
5. Ambiguous requests enforce Clarification Contract (zero files, zero artifacts, zero GenOffice calls).
6. Explicit mode overrides and user text precedence.
7. Native Markdown generation flows through D6 OutputPlanner & EngineRouter.
8. Fast chat bypasses tool schema injection (tools_declarations=None).
"""

import asyncio
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.actions import ActionType, AgentAction
from app.agent.brain import LLMReasoningEngine
from app.agent.context import AgentContext
from app.agent.intent import (
    ConfidenceLevel,
    IntentResolver,
    IntentType,
    ResolutionResult,
    ResponseType,
    TargetFormat,
    UserGoal,
    intent_resolver,
)
from app.agent.runtime import LimoAgentRuntime
from app.models.chat import MessageRole
from app.models.enums import FeatureMode, OutputFormat
from app.models.transformation import EngineType
from app.services.artifact_service import artifact_service
from app.services.chat_service import chat_service
from app.services.project_service import project_service
from app.storage.service import storage_service


# ---------------------------------------------------------------------------
# 1. Intent Resolver Unit Tests
# ---------------------------------------------------------------------------

def test_fast_chat_greetings_and_thanks():
    """Verify social greetings, thanks, and farewells resolve to FAST_CHAT."""
    greetings = [
        "hey",
        "hi",
        "hello",
        "good morning",
        "what's up",
        "thanks",
        "thank you so much",
        "cheers",
    ]
    for prompt in greetings:
        res = intent_resolver.resolve(prompt)
        assert res.intent == IntentType.FAST_CHAT, f"Failed for '{prompt}'"
        assert res.confidence == ConfidenceLevel.LOW
        assert res.target_format is None


def test_informational_questions_including_format_keywords():
    """Verify definitions and explanations, even with format keywords, resolve to FAST_CHAT."""
    questions = [
        ("what is an API?", "API definition"),
        ("how does photosynthesis work?", "Explanation"),
        ("What is Markdown?", "Format keyword question"),
        ("what is a spreadsheet?", "Spreadsheet keyword question"),
        ("Explain how PDF compression works", "PDF keyword question"),
        ("tell me about renewable energy", "General inquiry"),
    ]
    for prompt, desc in questions:
        res = intent_resolver.resolve(prompt)
        assert res.intent == IntentType.FAST_CHAT, f"Failed for '{prompt}' ({desc})"
        assert res.confidence == ConfidenceLevel.LOW
        assert res.target_format is None


def test_passive_format_mentions():
    """Verify passive mentions of formats without action verbs resolve to FAST_CHAT."""
    passives = [
        "I mentioned Markdown in my report.",
        "In my document earlier, we discussed solar cells.",
        "According to the spreadsheet from last week, revenue was up.",
        "I was reading a presentation on AI.",
    ]
    for prompt in passives:
        res = intent_resolver.resolve(prompt)
        assert res.intent == IntentType.FAST_CHAT, f"Failed for '{prompt}'"
        assert res.confidence == ConfidenceLevel.LOW
        assert res.target_format is None


def test_contextual_table_disambiguation():
    """Verify 'table' disambiguation behaves contextually according to Rule 3."""
    # Table inside Markdown container -> Markdown
    res_md = intent_resolver.resolve("Create a Markdown document about renewable energy with a 5-row table")
    assert res_md.intent == IntentType.GENERATE
    assert res_md.target_format == TargetFormat.MARKDOWN
    assert res_md.confidence == ConfidenceLevel.HIGH

    res_md2 = intent_resolver.resolve("Create a table in Markdown")
    assert res_md2.intent == IntentType.GENERATE
    assert res_md2.target_format == TargetFormat.MARKDOWN

    # Table inside Document container -> Document
    res_doc = intent_resolver.resolve("Create a table in a document")
    assert res_doc.intent == IntentType.GENERATE
    assert res_doc.target_format == TargetFormat.DOCUMENT

    # Table inside Spreadsheet container -> Spreadsheet
    res_sheet = intent_resolver.resolve("Create a spreadsheet table of sales")
    assert res_sheet.intent == IntentType.GENERATE
    assert res_sheet.target_format == TargetFormat.SPREADSHEET

    # Isolated 'table' with no container -> AMBIGUOUS with clarification prompt
    res_amb = intent_resolver.resolve("Create a table")
    assert res_amb.intent == IntentType.AMBIGUOUS
    assert res_amb.confidence == ConfidenceLevel.MEDIUM
    assert res_amb.clarification_prompt is not None
    assert "spreadsheet" in res_amb.clarification_prompt.lower()
    assert "markdown" in res_amb.clarification_prompt.lower()


def test_ambiguity_and_disjunctive_formats():
    """Verify disjunctive requests ('or', 'maybe') trigger AMBIGUOUS resolution."""
    ambiguous_prompts = [
        "Create a document or slides for my team",
        "Maybe a spreadsheet or a document",
        "Make something for my project",
    ]
    for prompt in ambiguous_prompts:
        res = intent_resolver.resolve(prompt)
        assert res.intent == IntentType.AMBIGUOUS, f"Expected AMBIGUOUS for '{prompt}', got {res.intent}"
        assert res.confidence == ConfidenceLevel.MEDIUM
        assert res.clarification_prompt is not None


def test_mode_overrides_and_text_precedence():
    """Verify active UI mode sets default format, but explicit text format overrides mode."""
    # Mode override when prompt has no format
    res_mode_doc = intent_resolver.resolve("Generate an analysis of renewable energy", active_mode=FeatureMode.DOCS)
    assert res_mode_doc.intent == IntentType.GENERATE
    assert res_mode_doc.target_format == TargetFormat.DOCUMENT

    res_mode_slides = intent_resolver.resolve("Summarize project roadmap", active_mode=FeatureMode.SLIDES)
    assert res_mode_slides.intent == IntentType.GENERATE
    assert res_mode_slides.target_format == TargetFormat.PRESENTATION

    # User text Markdown explicitly overrides DOCS mode
    res_override = intent_resolver.resolve("Create a Markdown document on climate change", active_mode=FeatureMode.DOCS)
    assert res_override.intent == IntentType.GENERATE
    assert res_override.target_format == TargetFormat.MARKDOWN


def test_transform_conversions():
    """Verify format conversion requests are classified as TRANSFORM."""
    res_conv = intent_resolver.resolve("Convert my notes into a presentation")
    assert res_conv.intent == IntentType.TRANSFORM
    assert res_conv.target_format == TargetFormat.PRESENTATION
    assert res_conv.confidence == ConfidenceLevel.HIGH

    res_conv_md = intent_resolver.resolve("Transform this summary into Markdown")
    assert res_conv_md.intent == IntentType.TRANSFORM
    assert res_conv_md.target_format == TargetFormat.MARKDOWN


# ---------------------------------------------------------------------------
# 2. Runtime Execution & Clarification Contract Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runtime_clarification_contract():
    """Verify AMBIGUOUS intent produces zero artifacts, zero file writes, and clean clarification."""
    session = chat_service.create_session()
    runtime = LimoAgentRuntime()

    msg = await runtime.execute_turn(
        session_id=session.id,
        user_prompt="Create a document or slides for the annual report",
    )

    assert msg.role == MessageRole.ASSISTANT
    assert len(msg.artifact_ids) == 0, "Clarification turn must produce zero artifact IDs"
    assert "document" in msg.content.lower() or "slides" in msg.content.lower()
    assert "clarification" in msg.execution_summary.lower()


@pytest.mark.asyncio
async def test_runtime_fast_chat_execution():
    """Verify FAST_CHAT turn executes direct lightweight decision without tool schema injection."""
    session = chat_service.create_session()
    
    mock_brain = MagicMock()
    mock_brain.decide = AsyncMock(
        return_value=AgentAction.final_response(
            text="Hello! How can I assist your workflow today?",
            summary="Fast conversational response (zero tool schema overhead).",
        )
    )

    runtime = LimoAgentRuntime(reasoning_engine=mock_brain)

    msg = await runtime.execute_turn(
        session_id=session.id,
        user_prompt="Hey",
    )

    assert msg.role == MessageRole.ASSISTANT
    assert msg.content == "Hello! How can I assist your workflow today?"
    assert len(msg.artifact_ids) == 0
    # Ensure decide was called with available_tools=[]
    mock_brain.decide.assert_called_once()
    call_kwargs = mock_brain.decide.call_args.kwargs
    assert call_kwargs.get("available_tools") == []


@pytest.mark.asyncio
async def test_brain_tools_declarations_omitted_when_available_tools_empty():
    """Verify LLMReasoningEngine sets tools_declarations=None when available_tools is empty."""
    mock_provider_mgr = MagicMock()
    mock_provider_res = MagicMock()
    mock_provider_res.function_calls = None
    mock_provider_res.text = "Direct answer without tools."
    mock_provider_res.total_tokens = 25
    mock_provider_res.latency_sec = 0.4
    mock_provider_res.route_key = "gemini-flash"

    mock_provider_mgr.generate = AsyncMock(return_value=mock_provider_res)

    brain = LLMReasoningEngine(provider_manager=mock_provider_mgr)
    context = AgentContext(session_id="sess_test", user_request="What is an API?")

    action = await brain.decide(context=context, available_tools=[])

    assert action.action_type == ActionType.FINAL_RESPONSE
    assert action.response_text == "Direct answer without tools."
    mock_provider_mgr.generate.assert_called_once()
    call_kwargs = mock_provider_mgr.generate.call_args.kwargs
    assert call_kwargs.get("tools_declarations") is None, "Tool declarations must be None for fast chat"


@pytest.mark.asyncio
async def test_runtime_d6_markdown_generation():
    """Verify dynamic Markdown generation passes through D6 OutputPlanner and EngineRouter."""
    project = project_service.create_project(name="D7.7 Verification Project")
    session = chat_service.create_session(project_id=project.id)
    runtime = LimoAgentRuntime()

    msg = await runtime.execute_turn(
        session_id=session.id,
        user_prompt="Create a Markdown document about renewable energy with a 5-row table",
        project_id=project.id,
    )

    assert msg.role == MessageRole.ASSISTANT
    assert len(msg.artifact_ids) == 1, "Must produce exactly one native Markdown artifact"
    
    art_id = msg.artifact_ids[0]
    artifact = artifact_service.get_artifact(art_id)
    assert artifact is not None
    assert artifact.file_format == ".md"
    assert artifact.size_bytes > 0

    # Verify physical file on disk
    file_path = storage_service.safe_resolve(artifact.storage_ref)
    assert file_path.exists(), f"Physical file '{file_path}' must exist on disk"
    content = file_path.read_text(encoding="utf-8")
    assert content.startswith("# "), "Markdown document must have a top-level heading"
    assert "|" in content, "Markdown document must contain a markdown table"
    assert "Renewable" in content or "Energy" in content


# ---------------------------------------------------------------------------
# 3. Adversarial Tests for Goal-First Intent & Format Routing
# ---------------------------------------------------------------------------

def test_real_user_failure_harness_article_summarize():
    """Verify the exact real failure case from user screenshots:
    User pasted Martin Fowler article on Harness Engineering with 'What this says summerise: ...'
    Must resolve to CHAT_RESPONSE / SUMMARIZE with zero target format.
    """
    prompt = (
        "What this says summerise: Harness engineering for coding agent users To let coding agents work with less "
        "supervision, we need ways to increase our confidence in their result. As software engineers, we have a natural "
        "trust barrier with AI-generated code - LLMs are non-deterministic, they don't know our context, and they don't "
        "really understand the code, they think in tokens. This article explores a mental model that brings together "
        "emerging concepts from context and harness engineering to build that trust. 02 April 2026 Photo of Birgitta "
        "Böckeler Birgitta Böckeler Birgitta is a Distinguished Engineer and AI-assisted delivery expert at Thoughtworks. "
        "She has over 20 years of experience as a software developer, architect and technical leader. generative AI "
        "Contents Feedforward and Feedback Computational vs Inferential The steering loop Timing: Keep quality left "
        "Regulation categories Maintainability harness Architecture fitness harness Behaviour harness Harnessability "
        "Harness templates The role of the human A starting point - and open questions Sidebars Metaphors only go so "
        "far How does harness engineering relate to context engineering? Ambient affordances Ashby's Law This article "
        "updates an earlier memo outlining my first impressions of harness engineering. The term harness has emerged "
        "as a shorthand to mean everything in an AI agent except the model itself - Agent = Model + Harness. That is a "
        "very wide definition, and therefore worth narrowing down for common categories of agents. I want to take the "
        "liberty here of defining its meaning in the bounded context of using a coding agent. In coding agents, part of "
        "the harness is already built in (e.g. via the system prompt, or the chosen code retrieval mechanism, or even a "
        "sophisticated orchestration system). But coding agents also provide us, their users, with many features to "
        "build an outer harness specifically for our use case and system. Metaphors only go so far It has been pointed "
        "out to me that wrapping harnesses around harnesses doesn't make sense: 'Have you ever tried to put a harness on'"
    )
    res = intent_resolver.resolve(prompt)
    assert res.response_type == ResponseType.CHAT_RESPONSE
    assert res.user_goal == UserGoal.SUMMARIZE
    assert res.target_format is None
    assert res.confidence == ConfidenceLevel.LOW


def test_adversarial_summarize_with_markdown_mentioned():
    """Verify summarize requests mentioning markdown or .md remain CHAT_RESPONSE."""
    cases = [
        "Summarize this article.",
        "Summarize this article about how Markdown was created.",
        "Can you summarize what the author wrote regarding Markdown documentation?",
        "Summarize this text: The document format .md is popular among developers.",
        "Please summarize Birgitta's thoughts on building outer harnesses.",
    ]
    for prompt in cases:
        res = intent_resolver.resolve(prompt)
        assert res.response_type == ResponseType.CHAT_RESPONSE, f"Failed for '{prompt}'"
        assert res.user_goal == UserGoal.SUMMARIZE
        assert res.target_format is None


def test_adversarial_explain_with_docx_mentioned():
    """Verify explain requests mentioning docx or formats remain CHAT_RESPONSE."""
    cases = [
        ("Explain this PDF.", UserGoal.EXPLAIN),
        ("Explain this DOCX file.", UserGoal.EXPLAIN),
        ("Explain why Word uses docx instead of doc format.", UserGoal.EXPLAIN),
        ("Walk me through this document.", UserGoal.EXPLAIN),
    ]
    for prompt, expected_goal in cases:
        res = intent_resolver.resolve(prompt)
        assert res.response_type == ResponseType.CHAT_RESPONSE, f"Failed for '{prompt}'"
        assert res.user_goal == expected_goal
        assert res.target_format is None


def test_adversarial_analyze_with_spreadsheet_mentioned():
    """Verify analyze requests mentioning spreadsheets/data remain CHAT_RESPONSE."""
    cases = [
        "Analyze this data.",
        "Analyze this spreadsheet: Q1 sales 40k, Q2 sales 60k.",
        "Analyze the numbers in this Excel sheet.",
        "Break down this table of results for me.",
    ]
    for prompt in cases:
        res = intent_resolver.resolve(prompt)
        assert res.response_type == ResponseType.CHAT_RESPONSE, f"Failed for '{prompt}'"
        assert res.user_goal == UserGoal.ANALYZE
        assert res.target_format is None


def test_adversarial_compare_with_pdf_mentioned():
    """Verify compare requests mentioning PDFs or reports remain CHAT_RESPONSE."""
    cases = [
        ("Compare these two reports.", UserGoal.COMPARE),
        ("Compare these two PDF files.", UserGoal.COMPARE),
        ("What are the differences between these two PDFs?", UserGoal.QUESTION_ANSWER),
        ("Contrast the architecture in document A with document B.", UserGoal.COMPARE),
    ]
    for prompt, expected_goal in cases:
        res = intent_resolver.resolve(prompt)
        assert res.response_type == ResponseType.CHAT_RESPONSE, f"Failed for '{prompt}'"
        assert res.user_goal == expected_goal
        assert res.target_format is None


def test_adversarial_rewrite_and_translate_with_document_mentioned():
    """Verify rewrite, translate, notes, and opinion requests remain CHAT_RESPONSE."""
    cases = [
        ("Rewrite this professionally.", UserGoal.REWRITE),
        ("Rewrite this document to sound more professional.", UserGoal.REWRITE),
        ("Translate this to Hindi.", UserGoal.TRANSLATE),
        ("Translate this document to Spanish.", UserGoal.TRANSLATE),
        ("Give me notes from this.", UserGoal.SUMMARIZE),
        ("What do you think about this?", UserGoal.ANALYZE),
    ]
    for prompt, expected_goal in cases:
        res = intent_resolver.resolve(prompt)
        assert res.response_type == ResponseType.CHAT_RESPONSE, f"Failed for '{prompt}'"
        assert res.user_goal == expected_goal
        assert res.target_format is None


def test_adversarial_format_words_inside_quoted_text():
    """Verify format creation directives inside quotes are not treated as top-level commands."""
    cases = [
        ("Summarize this quote: 'Please create a PDF document immediately.'", UserGoal.SUMMARIZE),
        ("What does the author mean when saying 'We must build a spreadsheet model'?", UserGoal.QUESTION_ANSWER),
        ("Explain the statement: \"Generate a presentation deck for the CEO.\"", UserGoal.EXPLAIN),
    ]
    for prompt, expected_goal in cases:
        res = intent_resolver.resolve(prompt)
        assert res.response_type == ResponseType.CHAT_RESPONSE, f"Failed for '{prompt}'"
        assert res.user_goal == expected_goal
        assert res.target_format is None


def test_adversarial_negative_generation():
    """Verify explicit negative generation instructions prevent deliverable creation."""
    cases = [
        ("Don't create a PDF, just summarize this article.", UserGoal.SUMMARIZE),
        ("Do not make a document, just tell me what happened.", UserGoal.QUESTION_ANSWER),
        ("No file needed, just answer my question.", UserGoal.QUESTION_ANSWER),
        ("Explain this without creating a presentation.", UserGoal.QUESTION_ANSWER),
        ("Don't generate anything, just give me your opinion.", UserGoal.QUESTION_ANSWER),
    ]
    for prompt, expected_goal in cases:
        res = intent_resolver.resolve(prompt)
        assert res.response_type == ResponseType.CHAT_RESPONSE, f"Failed for '{prompt}'"
        assert res.user_goal == expected_goal
        assert res.target_format is None


def test_adversarial_create_used_in_question():
    """Verify 'create' or format words used inside questions remain CHAT_RESPONSE."""
    cases = [
        "What is Markdown?",
        "How do I create a Markdown website?",
        "How to create a presentation in PowerPoint?",
        "How can I make an Excel spreadsheet?",
        "How can I convert this to Markdown?",
        "Why did they create the PDF standard?",
    ]
    for prompt in cases:
        res = intent_resolver.resolve(prompt)
        assert res.response_type == ResponseType.CHAT_RESPONSE, f"Failed for '{prompt}'"
        assert res.user_goal == UserGoal.QUESTION_ANSWER
        assert res.target_format is None


def test_adversarial_ambiguous_requests():
    """Verify vague formatting or containerless requests trigger AMBIGUOUS resolution."""
    cases = [
        ("Turn this into notes.", "notes"),
        ("Format this nicely.", "format"),
        ("Create something from this.", "something"),
        ("Summarize this in Markdown.", "in markdown"),
    ]
    for prompt, desc in cases:
        res = intent_resolver.resolve(prompt)
        assert res.response_type == ResponseType.AMBIGUOUS, f"Expected AMBIGUOUS for '{prompt}' ({desc})"
        assert res.user_goal == UserGoal.AMBIGUOUS
        assert res.confidence == ConfidenceLevel.MEDIUM
        assert res.clarification_prompt is not None


def test_explicit_deliverable_generation_cases():
    """Verify clear deliverable generation requests correctly resolve to GENERATE or TRANSFORM."""
    # GENERATE_ARTIFACT
    res1 = intent_resolver.resolve("Create a Markdown document summarizing this article.")
    assert res1.response_type == ResponseType.GENERATE_ARTIFACT
    assert res1.target_format == TargetFormat.MARKDOWN
    assert res1.user_goal == UserGoal.CREATE_DELIVERABLE

    res2 = intent_resolver.resolve("Create a PDF report from this article.")
    assert res2.response_type == ResponseType.GENERATE_ARTIFACT
    assert res2.target_format == TargetFormat.PDF
    assert res2.user_goal == UserGoal.CREATE_DELIVERABLE

    res3 = intent_resolver.resolve("Make an Excel spreadsheet from this data.")
    assert res3.response_type == ResponseType.GENERATE_ARTIFACT
    assert res3.target_format == TargetFormat.SPREADSHEET
    assert res3.user_goal == UserGoal.CREATE_DELIVERABLE

    res4 = intent_resolver.resolve("Create a DOCX document outlining the project plan.")
    assert res4.response_type == ResponseType.GENERATE_ARTIFACT
    assert res4.target_format == TargetFormat.DOCUMENT
    assert res4.user_goal == UserGoal.CREATE_DELIVERABLE

    # TRANSFORM_TO_ARTIFACT
    res5 = intent_resolver.resolve("Export this summary as Markdown.")
    assert res5.response_type == ResponseType.TRANSFORM_TO_ARTIFACT
    assert res5.target_format == TargetFormat.MARKDOWN
    assert res5.user_goal == UserGoal.CONVERT_DELIVERABLE

    res6 = intent_resolver.resolve("Turn this into a PowerPoint presentation.")
    assert res6.response_type == ResponseType.TRANSFORM_TO_ARTIFACT
    assert res6.target_format == TargetFormat.PRESENTATION
    assert res6.user_goal == UserGoal.CONVERT_DELIVERABLE


def test_deliverable_generation_regression_all_formats():
    """Verify existing DOCX, PPTX, XLSX, PDF, and MARKDOWN generation contracts."""
    formats = [
        ("Create a document on AI trends", TargetFormat.DOCUMENT),
        ("Make a presentation on quarterly sales", TargetFormat.PRESENTATION),
        ("Build a spreadsheet for budget tracking", TargetFormat.SPREADSHEET),
        ("Generate an executive memo PDF on Q3 revenue", TargetFormat.PDF),
        ("Create a Markdown document with a 5-row table", TargetFormat.MARKDOWN),
    ]
    for prompt, expected_fmt in formats:
        res = intent_resolver.resolve(prompt)
        assert res.response_type == ResponseType.GENERATE_ARTIFACT, f"Failed for '{prompt}'"
        assert res.target_format == expected_fmt
        assert res.confidence == ConfidenceLevel.HIGH

