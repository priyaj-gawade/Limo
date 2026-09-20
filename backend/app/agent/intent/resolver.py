"""Deterministic Fast Intent Gate and Format Resolver (Phase D7.7).

Implements authoritative decision order:
User message -> USER GOAL / INTENT -> RESPONSE TYPE -> OUTPUT FORMAT -> D6 Pipeline

Response Types:
- CHAT_RESPONSE: Pure conversational response directly in chat (zero artifacts, zero GenOffice calls).
- GENERATE_ARTIFACT: Explicit deliverable creation routed through D6.
- TRANSFORM_TO_ARTIFACT: Explicit conversion/export request routed through D6.
- EDIT_ARTIFACT: Direct open/edit action on existing artifact.
- AMBIGUOUS: Vague, conflicting, or containerless requests triggering clarification without generation.
"""

from enum import StrEnum
import logging
import re
from typing import List, Optional, Tuple, Union
from pydantic import BaseModel, Field

from ...exceptions import BadRequestError
from ...models.enums import FeatureMode, OutputFormat

logger = logging.getLogger("limo.agent.intent")


class UserGoal(StrEnum):
    """Categorical classification of the user's primary conversational goal."""
    SUMMARIZE = "SUMMARIZE"
    EXPLAIN = "EXPLAIN"
    ANALYZE = "ANALYZE"
    COMPARE = "COMPARE"
    EXTRACT = "EXTRACT"
    REWRITE = "REWRITE"
    TRANSLATE = "TRANSLATE"
    QUESTION_ANSWER = "QUESTION_ANSWER"
    CASUAL_CHAT = "CASUAL_CHAT"
    CREATE_DELIVERABLE = "CREATE_DELIVERABLE"
    CONVERT_DELIVERABLE = "CONVERT_DELIVERABLE"
    EDIT_DELIVERABLE = "EDIT_DELIVERABLE"
    SEARCH_WEB = "SEARCH_WEB"
    SEARCH_YOUTUBE = "SEARCH_YOUTUBE"
    RESEARCH = "RESEARCH"
    AMBIGUOUS = "AMBIGUOUS"


class ResponseType(StrEnum):
    """Authoritative response type governing downstream execution dispatch."""
    CHAT_RESPONSE = "CHAT_RESPONSE"
    GENERATE_ARTIFACT = "GENERATE_ARTIFACT"
    TRANSFORM_TO_ARTIFACT = "TRANSFORM_TO_ARTIFACT"
    EDIT_ARTIFACT = "EDIT_ARTIFACT"
    AMBIGUOUS = "AMBIGUOUS"

    # Backward compatibility aliases for D7.7 callers
    FAST_CHAT = "CHAT_RESPONSE"
    GENERATE = "GENERATE_ARTIFACT"
    TRANSFORM = "TRANSFORM_TO_ARTIFACT"


# Backward compatibility alias
IntentType = ResponseType


class ConfidenceLevel(StrEnum):
    """Confidence tier governing downstream execution dispatch."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TargetFormat(StrEnum):
    """Normalized deliverable format targets."""
    DOCUMENT = "document"
    PRESENTATION = "presentation"
    SPREADSHEET = "spreadsheet"
    PDF = "pdf"
    MARKDOWN = "markdown"
    VIDEO = "video"
    AUDIO = "audio"
    INFOGRAPHIC = "infographic"


class ResolutionResult(BaseModel):
    """Structured outcome produced by the Fast Intent Gate."""
    response_type: ResponseType = Field(description="Authoritative response pathway")
    user_goal: UserGoal = Field(description="Detected underlying user goal")
    target_format: Optional[TargetFormat] = Field(default=None, description="Resolved output deliverable format")
    resolved_ratio: Optional[str] = Field(default=None, description="Resolved aspect ratio for poster/infographic deliverable")
    confidence: ConfidenceLevel = Field(description="Classification confidence level")
    reason: str = Field(description="Deterministic rationale for classification")
    source_reference: Optional[str] = Field(default=None, description="Extracted input source phrase for transforms")
    ambiguous_options: List[TargetFormat] = Field(default_factory=list, description="Contending formats if ambiguous")
    clarification_prompt: Optional[str] = Field(default=None, description="Conversational prompt to present to user")
    needs_web_search: bool = Field(default=False, description="Whether turn requires live web search")
    needs_youtube: bool = Field(default=False, description="Whether turn requires YouTube video lookup")
    needs_url_scrape: bool = Field(default=False, description="Whether turn requires remote URL/article scraping")
    uses_pasted_source: bool = Field(default=False, description="Whether prompt contains substantial pasted content bypassing web search")
    needs_current_information: bool = Field(default=False, description="Whether request demands current/real-time factual verification")
    target_url: Optional[str] = Field(default=None, description="Primary extracted web/article URL to scrape")
    target_urls: List[str] = Field(default_factory=list, description="All extracted web/article URLs to scrape")
    web_query: Optional[str] = Field(default=None, description="Extracted search or research query")

    @property
    def intent(self) -> ResponseType:
        """Backward compatibility alias for existing callers expecting .intent."""
        return self.response_type


class IntentResolver:
    """Fast, deterministic goal-first intent gate and format disambiguator."""

    @staticmethod
    def _extract_directive_and_body(prompt: str) -> Tuple[str, str]:
        """Separate operational user command directive from reference body text."""
        raw = prompt.strip()
        if not raw:
            return "", ""

        # Pattern A: Leading command prefix followed by colon or double newline
        # e.g. "What this says summerise: [Article...]" or "Summarize this article:\n\n[Article...]"
        m_prefix = re.match(
            r"^((?:what\s+(?:this\s+says\s+)?(?:summarise|summarize|summerise|says)|can\s+you\s+(?:summarize|explain|analyze|translate|rewrite)|summarize|summarise|summerise|explain|analyze|analyse|compare|extract|rewrite|translate|please\s+summarize|please\s+explain)[^:\n]{0,80})(?::|\n+)(.*)$",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m_prefix:
            return m_prefix.group(1).strip(), m_prefix.group(2).strip()

        # Pattern B: Explicit deliverable creation command followed by content
        # e.g. "Create a Markdown document summarizing this article: [Article...]"
        m_create = re.match(
            r"^((?:create|generate|make|draft|produce|build|write|export|convert|transform|turn)\s+(?:a\s+|an\s+)?(?:markdown\s+|md\s+|docx?\s+|slides?\s+|presentation\s+|spreadsheet\s+|sheets?\s+|xlsx\s+|pdf\s+)?(?:document|doc|report|presentation|slides|deck|spreadsheet|sheet|table|pdf|memo|file)[^:\n]{0,100})(?::|\n+)(.*)$",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m_create:
            return m_create.group(1).strip(), m_create.group(2).strip()

        # Pattern C: Multi-paragraph with trailing command
        paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]
        if len(paragraphs) > 1:
            last_p = paragraphs[-1].lower()
            if any(k in last_p for k in ["summarize", "summarise", "summerise", "explain", "analyze", "what does this say", "what do you think"]):
                return paragraphs[-1], "\n\n".join(paragraphs[:-1])

        return raw, ""

    @classmethod
    def _is_pasted_source(cls, prompt: str, directive: str, body: str) -> bool:
        """Classify whether the prompt actually contains supplied source material.

        Does NOT rely solely on raw character count. Requires strong evidence of
        supplied content, such as:
        1. Quoted or fenced blocks (triple quotes, markdown blocks, blockquotes, large quotes).
        2. Explicit source framing ("here is the article", "below is the document",
           "summarize the following", "use this content", "analyze this text").
        3. A clearly delimited substantive body following a source directive.
        """
        clean_prompt = prompt.strip()
        clean_body = body.strip()

        # If there's an explicit URL in the prompt, that is a URL scrape target, not pasted source
        if re.search(r"https?://[^\s)\]>\"']+", clean_prompt):
            return False

        # 1. Quoted or fenced source blocks
        # Triple quotes or markdown code blocks containing substantive text (>= 50 chars)
        if re.search(r'("""[\s\S]{50,}?"""|\'\'\'[\s\S]{50,}?\'\'\'|```[\s\S]{50,}?```)', clean_prompt):
            return True

        # Markdown blockquotes (lines starting with >)
        if re.search(r'(?:^|\n)>\s+.{50,}', clean_prompt, re.DOTALL):
            return True

        # Quoted text in double quotes after a colon or newline
        if re.search(r'(?::|\n+)\s*"([^"]{60,})"', clean_prompt):
            return True

        # 2. Explicit source framing phrases anywhere in prompt or directive
        source_framing_pattern = re.compile(
            r"\b(?:"
            r"(?:here\s+(?:is|are)|below\s+(?:is|are)|following\s+is|here's)\s+(?:the\s+|an?\s+)?(?:article|document|text|content|post|excerpt|paper|notes|transcript|speech|story|data)"
            r"|(?:summarize|analyse|analyze|explain|translate|rewrite|extract\s+from|read|evaluate)\s+(?:the\s+following|this\s+text|this\s+article|this\s+document|this\s+content|this\s+post|below)"
            r"|(?:use|based\s+on)\s+(?:this|the\s+following)\s+(?:content|text|article|document|source|information)"
            r"|(?:article|document|content|text|transcript|source|excerpt)\s*:\s*\n+"
            r")\b",
            re.IGNORECASE,
        )
        has_explicit_framing = bool(source_framing_pattern.search(directive) or source_framing_pattern.search(clean_prompt[:250]))

        # If explicit framing is present and there is substantive following body
        if has_explicit_framing and clean_body and len(clean_body) >= 60:
            return True

        # 3. Delimited body after a source-processing directive
        source_directive_pattern = re.compile(
            r"\b(?:summarize|summarise|summerise|analyze|analyse|explain|translate|rewrite|extract|what\s+does\s+this\s+say|what\s+this\s+says)\b"
            r".*?\b(?:article|document|text|post|excerpt|paper|content|transcript|notes|following|below|this)\b",
            re.IGNORECASE,
        )
        if clean_body and len(clean_body) >= 100:
            if source_directive_pattern.search(directive):
                return True

        # 4. Multi-paragraph prose following a clear colon separator after a directive
        if (":" in directive or clean_prompt.startswith(directive + ":")) and clean_body:
            paragraphs = [p.strip() for p in clean_body.split("\n\n") if p.strip()]
            if len(paragraphs) >= 2 and len(clean_body) >= 200:
                # Must not look like a bullet list of user questions or user instructions
                if not re.match(r"^(?:\d+[\.)]|\-|\*)\s+", clean_body):
                    return True

        return False

    def resolve(
        self,
        prompt: str,
        active_mode: Optional[Union[FeatureMode, str]] = None,
    ) -> ResolutionResult:
        res = self._resolve_internal(prompt, active_mode)

        # Web Reach Decision Policy (Phase D8.9)
        # Precedence hierarchy:
        # 1. Pasted Content Bypass (with "verify current claims" exception)
        # 2. Direct URL Content Extraction
        # 3. YouTube Video / Transcript Discovery
        # 4. Current / Temporal Information Needs
        # 5. General Knowledge Queries
        # 6. Normal Conversational Chat

        # Extract all URLs
        raw_urls = re.findall(r"https?://[^\s)\]>\"']+", prompt)
        clean_urls = [u.rstrip(".,;)\"'>]") for u in raw_urls if u.rstrip(".,;)\"'>]")]

        youtube_urls = [
            u for u in clean_urls
            if any(h in u.lower() for h in ("youtube.com/watch", "youtu.be/", "youtube.com/shorts", "youtube.com/channel"))
        ]
        web_urls = [u for u in clean_urls if u not in youtube_urls]

        directive, body = self._extract_directive_and_body(prompt)
        is_pasted_article = self._is_pasted_source(prompt, directive, body)

        # Check for explicit verification exception on pasted article
        has_verify_current = bool(
            re.search(
                r"\b(?:verify|check|fact-?check|validate|confirm|is\s+this\s+still|are\s+these\s+still)\b.*\b(?:current|today|now|recent|latest|true\s+today|still\s+accurate)\b",
                prompt,
                re.I,
            )
        )

        clean_search_query = re.sub(
            r"^(?:please\s+)?(?:create|make|generate|produce|build|draft|write|export|convert|transform|turn)?\s*(?:an?\s+)?(?:one-page\s+|2-slide\s+|small\s+|short\s+|8-second\s+|15-second\s+|\d+:\d+\s+)?(?:markdown\s+|md\s+|docx?\s+|slides?\s+|presentation\s+|spreadsheet\s+|sheets?\s+|xlsx\s+|pdf\s+|infographics?|posters?|images?|videos?|documents?|memo\s+pdf)?\s*(?:on|about|for|of|into|to|from|:)?\s*",
            "",
            prompt,
            flags=re.IGNORECASE,
        ).strip()
        clean_search_query = re.sub(
            r"^(?:please\s+)?(?:search(?:\s+the)?\s+(?:web|internet|google)(?:\s+for)?|look\s+up\s+online(?:\s+for)?|browse\s+the\s+web\s+for|what\s+is\s+the\s+latest|what\s+are\s+the\s+latest|tell\s+me\s+about\s+the\s+latest|summarize\s+(?:the\s+latest\s+)?|find\s+out\s+(?:about\s+)?)\s*",
            "",
            clean_search_query,
            flags=re.IGNORECASE,
        ).strip().rstrip(".!?")
        if not clean_search_query:
            clean_search_query = prompt

        clean_yt_query = re.sub(
            r"^(?:please\s+)?(?:find|search(?:\s+for)?|get|show\s+me|look\s+up|what\s+are)\s+(?:some\s+)?(?:youtube\s+)?(?:videos?|clips?)(?:\s+on\s+youtube)?(?:\s+(?:about|on|for|explaining|covering|that\s+explain|that\s+cover))?\s*",
            "",
            prompt,
            flags=re.IGNORECASE,
        ).strip().rstrip(".!?")
        if not clean_yt_query:
            clean_yt_query = prompt

        is_explicit_web_search = bool(
            re.search(
                r"\b(?:search(?:\s+the)?\s+(?:web|internet|google)|look\s+up\s+online|browse\s+the\s+web)\b",
                prompt,
                re.I,
            )
        )
        is_temporal = bool(
            re.search(
                r"\b(?:latest|recent|today's|breaking\s+news|current\s+(?:events?|price|status|developments|news|market)|news\s+(?:about|on|today)|developments\s+in|who\s+won|stock\s+price|weather\s+in|what\s+happened\s+(?:today|recently)|happening\s+today)\b",
                prompt,
                re.I,
            )
        )
        is_yt = bool(
            youtube_urls or re.search(r"\b(?:youtube|videos?\s+on\s+youtube|youtube\s+videos?|youtube\s+channel)\b", prompt, re.I)
        )

        # Tier 1: Pasted Content Bypass
        if is_pasted_article:
            res.uses_pasted_source = True
            if has_verify_current:
                res.needs_current_information = True
                res.needs_web_search = True
                res.web_query = clean_search_query
            else:
                # Pasted article bypass: strictly zero external browsing
                res.needs_web_search = False
                res.needs_url_scrape = False
                res.needs_youtube = False
                return res

        # Tier 2: Direct URL Content Extraction
        if web_urls:
            res.needs_url_scrape = True
            res.target_url = web_urls[0]
            res.target_urls = web_urls

        # Tier 3: YouTube Video / Transcript Discovery
        if is_yt:
            res.needs_youtube = True
            if youtube_urls:
                res.target_url = youtube_urls[0]
                res.target_urls = youtube_urls
            elif not res.web_query:
                res.web_query = clean_yt_query

        # Tier 4: Current / Temporal Information Needs
        if (is_explicit_web_search or is_temporal) and not res.needs_url_scrape and not is_pasted_article:
            res.needs_web_search = True
            res.needs_current_information = True
            if not res.web_query:
                res.web_query = clean_search_query

        return res

    def _resolve_internal(
        self,
        prompt: str,
        active_mode: Optional[Union[FeatureMode, str]] = None,
    ) -> ResolutionResult:
        """Analyze prompt and optional active mode following Goal -> Response Type -> Format."""
        if not prompt or not prompt.strip():
            return ResolutionResult(
                response_type=ResponseType.CHAT_RESPONSE,
                user_goal=UserGoal.CASUAL_CHAT,
                confidence=ConfidenceLevel.LOW,
                reason="Empty prompt defaulted to conversational chat",
            )

        directive, body = self._extract_directive_and_body(prompt)
        d_lower = directive.lower().strip()

        # Extract explicit aspect ratio token if requested (e.g. "3:4", "9:16", "16:9", "1:1", "4:3")
        ratio_match = re.search(r"\b(\d+:\d+)\b", prompt.lower())
        explicit_ratio_requested = ratio_match.group(1).strip() if ratio_match else None
        detected_ratio = explicit_ratio_requested or "3:4"

        # Normalize mode string
        mode_str = "none"
        if active_mode:
            mode_str = active_mode.value if hasattr(active_mode, "value") else str(active_mode).lower().strip()

        # -------------------------------------------------------------------
        # Pre-Analysis: Web Reach & External Access Signals (Phase D8.9)
        # -------------------------------------------------------------------
        url_match = re.search(r"https?://[^\s)\]>\"']+", prompt)
        found_url = url_match.group(0).rstrip(".,;") if url_match else None

        is_yt = bool(re.search(r"\b(?:youtube|videos?\s+on\s+youtube|youtube\s+videos?|youtube\s+channel)\b", prompt, re.I))

        # Pasted article bypass: substantive text provided directly in prompt
        is_pasted_article = self._is_pasted_source(prompt, directive, body)

        is_explicit_web_search = bool(
            re.search(
                r"\b(?:search(?:\s+the)?\s+(?:web|internet|google)|look\s+up\s+online|browse\s+the\s+web)\b",
                prompt,
                re.I,
            )
        )
        is_temporal = bool(
            re.search(
                r"\b(?:latest|recent|today's|breaking\s+news|current\s+(?:events?|price|status|developments|news|market)|news\s+(?:about|on|today)|developments\s+in|who\s+won|stock\s+price|weather\s+in|what\s+happened\s+(?:today|recently)|happening\s+today)\b",
                prompt,
                re.I,
            )
        )
        needs_search = (is_explicit_web_search or is_temporal) and not is_pasted_article

        clean_search_query = re.sub(
            r"^(?:please\s+)?(?:search(?:\s+the)?\s+(?:web|internet|google)(?:\s+for)?|look\s+up\s+online(?:\s+for)?|browse\s+the\s+web\s+for|what\s+is\s+the\s+latest|what\s+are\s+the\s+latest|tell\s+me\s+about\s+the\s+latest|summarize\s+(?:the\s+latest\s+)?|find\s+out\s+(?:about\s+)?)\s*",
            "",
            prompt,
            flags=re.IGNORECASE,
        ).strip().rstrip(".!?")
        if not clean_search_query:
            clean_search_query = prompt

        clean_yt_query = re.sub(
            r"^(?:please\s+)?(?:find|search(?:\s+for)?|get|show\s+me|look\s+up|what\s+are)\s+(?:some\s+)?(?:youtube\s+)?(?:videos?|clips?)(?:\s+on\s+youtube)?(?:\s+(?:about|on|for|explaining|covering|that\s+explain|that\s+cover))?\s*",
            "",
            prompt,
            flags=re.IGNORECASE,
        ).strip().rstrip(".!?")
        if not clean_yt_query:
            clean_yt_query = prompt

        has_deliverable_command = bool(
            re.search(
                r"\b(?:create|make|generate|produce|build|draft|write|export|convert|transform|turn)\s+(?:a\s+|an\s+)?(?:one-page\s+|2-slide\s+|small\s+|short\s+|8-second\s+|15-second\s+|\d+:\d+\s+)?(?:markdown\s+|md\s+|docx?\s+|slides?\s+|presentation\s+|spreadsheet\s+|sheets?\s+|xlsx\s+|pdf\s+|infographics?|posters?|images?|videos?)\b",
                d_lower,
            )
        ) or mode_str in ("docs", "slides", "sheets", "video", "audio", "infographic", "poster", "image")

        # Pure Conversational Web Reach Turns (No Deliverable Command)
        if not has_deliverable_command:
            if is_yt:
                return ResolutionResult(
                    response_type=ResponseType.CHAT_RESPONSE,
                    user_goal=UserGoal.SEARCH_YOUTUBE,
                    confidence=ConfidenceLevel.HIGH,
                    reason="YouTube video search requested",
                    needs_youtube=True,
                    web_query=clean_yt_query,
                )
            if found_url and not is_pasted_article:
                return ResolutionResult(
                    response_type=ResponseType.CHAT_RESPONSE,
                    user_goal=UserGoal.SUMMARIZE,
                    confidence=ConfidenceLevel.HIGH,
                    reason=f"Article URL reading requested for {found_url}",
                    needs_url_scrape=True,
                    target_url=found_url,
                )
            if needs_search:
                return ResolutionResult(
                    response_type=ResponseType.CHAT_RESPONSE,
                    user_goal=UserGoal.SEARCH_WEB,
                    confidence=ConfidenceLevel.HIGH,
                    reason="Web search requested for live/current information",
                    needs_web_search=True,
                    web_query=clean_search_query,
                )

        # -------------------------------------------------------------------
        # Rule 0: Edit / Open Deliverable Requests
        # -------------------------------------------------------------------
        if re.search(r"\b(open\s+in\s+genoffice|edit\s+(?:this\s+)?(?:document|doc|presentation|slides|spreadsheet|sheet|artifact|file))\b", d_lower):
            return ResolutionResult(
                response_type=ResponseType.EDIT_ARTIFACT,
                user_goal=UserGoal.EDIT_DELIVERABLE,
                confidence=ConfidenceLevel.HIGH,
                reason="Explicit edit/open artifact request",
            )

        # -------------------------------------------------------------------
        # Rule 1: Negative Generation Instructions
        # e.g. "Don't create a PDF, just summarize it"
        # -------------------------------------------------------------------
        if re.search(
            r"\b(don'?t\s+create|do\s+not\s+create|don'?t\s+make|do\s+not\s+make|no\s+(?:pdf|file|doc|document|slides?|spreadsheet|video|infographic|poster|image)|without\s+creating|don'?t\s+generate|do\s+not\s+generate)\b",
            d_lower,
        ):
            goal = UserGoal.SUMMARIZE if "summar" in d_lower else UserGoal.QUESTION_ANSWER
            return ResolutionResult(
                response_type=ResponseType.CHAT_RESPONSE,
                user_goal=goal,
                confidence=ConfidenceLevel.HIGH,
                reason="Explicit negative instruction against deliverable generation",
            )

        # -------------------------------------------------------------------
        # Rule 2: Opinion / Analytical Inquiries
        # e.g. "What do you think about this?"
        # -------------------------------------------------------------------
        if re.search(r"\bwhat\s+do\s+you\s+think\b", d_lower):
            return ResolutionResult(
                response_type=ResponseType.CHAT_RESPONSE,
                user_goal=UserGoal.ANALYZE,
                confidence=ConfidenceLevel.LOW,
                reason="Analytical opinion inquiry answered directly in chat",
            )

        # -------------------------------------------------------------------
        # Rule 3: Informational / How-To Questions
        # e.g. "What is Markdown?", "How do I create a Markdown website?", "Why did they create the PDF standard?",
        # "What does the author mean when saying '...'", "Explain why Word uses docx instead of doc"
        # -------------------------------------------------------------------
        is_how_to = bool(
            re.match(
                r"^(how\s+(?:do\s+i|can\s+i|to|does|did|would|could|is|are)|can\s+you\s+explain\s+how\s+to)\b",
                d_lower,
            )
        )
        is_info_question = bool(
            re.match(
                r"^(what|why|who|where|which|when)\s+(?:is|are|was|were|do|does|did|would|could|can|to|did\s+they|should|will)\b",
                d_lower,
            )
            or re.match(r"^(tell\s+me\s+about|can\s+you\s+tell\s+me|explain\s+(?:what|why|how)|can\s+you\s+explain\s+(?:what|why|how))\b", d_lower)
        )
        # Exclude polite generation commands like "Can you create a PDF...", "Could you make a document..."
        is_polite_generation_command = bool(
            re.match(
                r"^(?:can|could|would)\s+you\s+(?:please\s+)?(?:create|make|generate|build|draft|produce|export|convert|transform)\b",
                d_lower,
            )
        )
        if (is_how_to or is_info_question) and not is_polite_generation_command:
            goal = UserGoal.EXPLAIN if "explain" in d_lower else UserGoal.QUESTION_ANSWER
            return ResolutionResult(
                response_type=ResponseType.CHAT_RESPONSE,
                user_goal=goal,
                confidence=ConfidenceLevel.LOW,
                reason="Informational or how-to question answered directly in chat",
            )


        # -------------------------------------------------------------------
        # Rule 4: Input Source References
        # e.g. "Explain this PDF", "Analyze this spreadsheet", "Summarize the attached document"
        # -------------------------------------------------------------------
        has_output_transform_target = bool(
            re.search(
                r"\b(?:in|into|as|using|with|to)\s+(?:markdown|\.md|audio|speech|voice|narration|slides?|presentation|spreadsheets?|sheets?|xlsx|pdf|documents?|docs?|docx|infographics?|posters?|images?)\b",
                d_lower,
            )
        )
        if re.search(
            r"\b(?:explain|summarize|summarise|summerise|analyze|analyse|read|look\s+at|check|review|what\s+does)\s+(?:this|the|attached|my|that)?\s*(?:attached\s+)?(?:pdf|document|doc|spreadsheet|sheet|article|report|file)\b",
            d_lower,
        ) and not has_output_transform_target:
            goal = UserGoal.EXPLAIN if "explain" in d_lower else (UserGoal.ANALYZE if "analy" in d_lower else UserGoal.SUMMARIZE)
            return ResolutionResult(
                response_type=ResponseType.CHAT_RESPONSE,
                user_goal=goal,
                confidence=ConfidenceLevel.LOW,
                reason="Format keyword refers to input source reference, answering in chat",
            )

        # -------------------------------------------------------------------
        # Rule 5: Social Greetings & Passive Mentions
        # -------------------------------------------------------------------
        if re.match(
            r"^(hey|hi|hello|good\s+(morning|afternoon|evening)|sup|what\'?s\s+up|howdy|thanks|thank\s+you|thx|cheers|bye|goodbye)[\s.!?]*$",
            d_lower,
        ):
            return ResolutionResult(
                response_type=ResponseType.CHAT_RESPONSE,
                user_goal=UserGoal.CASUAL_CHAT,
                confidence=ConfidenceLevel.LOW,
                reason="Social greeting or polite gratitude",
            )

        if re.search(r"\b(i\s+mentioned|in\s+my|according\s+to|referring\s+to|i\s+was\s+reading|have\s+you\s+seen)\b", d_lower):
            if not re.search(r"\b(create|make|generate|produce|export|convert)\b", d_lower):
                return ResolutionResult(
                    response_type=ResponseType.CHAT_RESPONSE,
                    user_goal=UserGoal.CASUAL_CHAT,
                    confidence=ConfidenceLevel.LOW,
                    reason="Passive conversational mention without generation directive",
                )

        # -------------------------------------------------------------------
        # Rule 6: Explicit Conversion / Export Requests (TRANSFORM_TO_ARTIFACT)
        # Evaluated before pure conversational summary so "Export this summary as Markdown" is honored!
        # -------------------------------------------------------------------
        m_conv = re.search(r"\b(?:convert|transform|turn|export|put)\s+(.+?)\s+(?:in|as|to|into)\s+([a-z0-9_\s]+)", d_lower)
        if m_conv:
            src_phrase = m_conv.group(1).strip()
            target_str = m_conv.group(2).strip()

            if any(w in target_str for w in ["markdown", ".md"]):
                return ResolutionResult(
                    response_type=ResponseType.TRANSFORM_TO_ARTIFACT,
                    user_goal=UserGoal.CONVERT_DELIVERABLE,
                    target_format=TargetFormat.MARKDOWN,
                    confidence=ConfidenceLevel.HIGH,
                    reason="Explicit conversion to Markdown deliverable",
                    source_reference=src_phrase,
                )
            elif any(w in target_str for w in ["presentation", "slides", "deck", "pptx", "powerpoint"]):
                return ResolutionResult(
                    response_type=ResponseType.TRANSFORM_TO_ARTIFACT,
                    user_goal=UserGoal.CONVERT_DELIVERABLE,
                    target_format=TargetFormat.PRESENTATION,
                    confidence=ConfidenceLevel.HIGH,
                    reason="Explicit conversion to Presentation deliverable",
                    source_reference=src_phrase,
                )
            elif any(w in target_str for w in ["spreadsheet", "sheet", "xlsx", "excel", "csv"]):
                return ResolutionResult(
                    response_type=ResponseType.TRANSFORM_TO_ARTIFACT,
                    user_goal=UserGoal.CONVERT_DELIVERABLE,
                    target_format=TargetFormat.SPREADSHEET,
                    confidence=ConfidenceLevel.HIGH,
                    reason="Explicit conversion to Spreadsheet deliverable",
                    source_reference=src_phrase,
                )
            elif any(w in target_str for w in ["pdf"]):
                return ResolutionResult(
                    response_type=ResponseType.TRANSFORM_TO_ARTIFACT,
                    user_goal=UserGoal.CONVERT_DELIVERABLE,
                    target_format=TargetFormat.PDF,
                    confidence=ConfidenceLevel.HIGH,
                    reason="Explicit conversion to PDF deliverable",
                    source_reference=src_phrase,
                )
            elif any(w in target_str for w in ["document", "doc", "docx"]):
                return ResolutionResult(
                    response_type=ResponseType.TRANSFORM_TO_ARTIFACT,
                    user_goal=UserGoal.CONVERT_DELIVERABLE,
                    target_format=TargetFormat.DOCUMENT,
                    confidence=ConfidenceLevel.HIGH,
                    reason="Explicit conversion to Document deliverable",
                    source_reference=src_phrase,
                )
            elif any(w in target_str for w in ["video", "mp4"]):
                return ResolutionResult(
                    response_type=ResponseType.TRANSFORM_TO_ARTIFACT,
                    user_goal=UserGoal.CONVERT_DELIVERABLE,
                    target_format=TargetFormat.VIDEO,
                    confidence=ConfidenceLevel.HIGH,
                    reason="Explicit conversion to Video deliverable",
                    source_reference=src_phrase,
                )
            elif any(w in target_str for w in ["audio", "speech", "narration", "mp3", "voice"]):
                return ResolutionResult(
                    response_type=ResponseType.TRANSFORM_TO_ARTIFACT,
                    user_goal=UserGoal.CONVERT_DELIVERABLE,
                    target_format=TargetFormat.AUDIO,
                    confidence=ConfidenceLevel.HIGH,
                    reason="Explicit conversion to Audio/TTS deliverable",
                    source_reference=src_phrase,
                )
            elif any(w in target_str for w in ["infographic", "poster", "image", "visual", "graphic"]):
                if explicit_ratio_requested and explicit_ratio_requested not in ("3:4", "9:16", "16:9", "1:1", "4:3"):
                    raise BadRequestError(
                        f"Unsupported aspect ratio '{explicit_ratio_requested}'. Prismo supports: 3:4, 9:16, 16:9, 1:1, and 4:3."
                    )
                return ResolutionResult(
                    response_type=ResponseType.TRANSFORM_TO_ARTIFACT,
                    user_goal=UserGoal.CONVERT_DELIVERABLE,
                    target_format=TargetFormat.INFOGRAPHIC,
                    resolved_ratio=detected_ratio,
                    confidence=ConfidenceLevel.HIGH,
                    reason="Explicit conversion to Infographic/Poster deliverable",
                    source_reference=src_phrase,
                )
            elif any(w in target_str for w in ["notes", "something", "nicely"]):
                return ResolutionResult(
                    response_type=ResponseType.AMBIGUOUS,
                    user_goal=UserGoal.AMBIGUOUS,
                    confidence=ConfidenceLevel.MEDIUM,
                    reason="Conversion requested with vague target container",
                    ambiguous_options=[TargetFormat.DOCUMENT, TargetFormat.PRESENTATION, TargetFormat.MARKDOWN],
                    clarification_prompt=(
                        "What deliverable format would you like to create? "
                        "(For example: a document, presentation, spreadsheet, PDF, or Markdown file?)"
                    ),
                )

        # -------------------------------------------------------------------
        # Rule 7: Vague Formatting / Vague Notes Requests
        # e.g. "Format this nicely.", "Turn this into notes."
        # -------------------------------------------------------------------
        if re.search(r"\bformat\s+this\b", d_lower) or re.search(r"\bturn\s+this\s+into\s+notes\b", d_lower):
            return ResolutionResult(
                response_type=ResponseType.AMBIGUOUS,
                user_goal=UserGoal.AMBIGUOUS,
                confidence=ConfidenceLevel.MEDIUM,
                reason="Vague formatting request without specified output deliverable",
                ambiguous_options=[TargetFormat.DOCUMENT, TargetFormat.PRESENTATION, TargetFormat.MARKDOWN],
                clarification_prompt=(
                    "How would you like this formatted? "
                    "I can format it directly here in chat, or generate a document, presentation, or Markdown file."
                ),
            )

        # -------------------------------------------------------------------
        # Rule 8: Mode Override Evaluation
        # Active UI mode explicitly sets the deliverable format container.
        # Format explicitly requested in text (e.g. Markdown, PDF, Slides) overrides mode.
        # -------------------------------------------------------------------
        if mode_str in ("docs", "slides", "sheets", "video", "audio", "infographic", "poster", "image"):
            mode_to_fmt = {
                "docs": TargetFormat.DOCUMENT,
                "slides": TargetFormat.PRESENTATION,
                "sheets": TargetFormat.SPREADSHEET,
                "video": TargetFormat.VIDEO,
                "audio": TargetFormat.AUDIO,
                "infographic": TargetFormat.INFOGRAPHIC,
                "poster": TargetFormat.INFOGRAPHIC,
                "image": TargetFormat.INFOGRAPHIC,
            }
            override_fmt = mode_to_fmt[mode_str]

            # If user explicitly requested another format in text, text format takes precedence
            if re.search(r"\b(markdown|\.md)\b", d_lower):
                target_f = TargetFormat.MARKDOWN
            elif re.search(r"\b(videos?|explainer\s+video)\b", d_lower):
                target_f = TargetFormat.VIDEO
            elif re.search(r"\b(pdfs?|executive\s+memo\s+pdf)\b", d_lower):
                target_f = TargetFormat.PDF
            elif re.search(r"\b(presentations?|slides?|deck|pptx|powerpoint)\b", d_lower):
                target_f = TargetFormat.PRESENTATION
            elif re.search(r"\b(spreadsheets?|sheets?|xlsx|excel|csv)\b", d_lower):
                target_f = TargetFormat.SPREADSHEET
            elif re.search(r"\b(documents?|docs?|docx)\b", d_lower):
                target_f = TargetFormat.DOCUMENT
            elif re.search(r"\b(audio|speech|narration|voiceover|read\s+(?:this\s+)?aloud)\b", d_lower):
                target_f = TargetFormat.AUDIO
            elif re.search(r"\b(infographics?|posters?|images?|visual\s+posters?)\b", d_lower):
                target_f = TargetFormat.INFOGRAPHIC
            else:
                target_f = override_fmt

            if target_f == TargetFormat.INFOGRAPHIC and explicit_ratio_requested and explicit_ratio_requested not in ("3:4", "9:16", "16:9", "1:1", "4:3"):
                raise BadRequestError(
                    f"Unsupported aspect ratio '{explicit_ratio_requested}'. Prismo supports: 3:4, 9:16, 16:9, 1:1, and 4:3."
                )

            return ResolutionResult(
                response_type=ResponseType.GENERATE_ARTIFACT,
                user_goal=UserGoal.CREATE_DELIVERABLE,
                target_format=target_f,
                resolved_ratio=detected_ratio if target_f == TargetFormat.INFOGRAPHIC else None,
                confidence=ConfidenceLevel.HIGH,
                reason=f"Explicit feature mode '{mode_str}' acts as format authority (resolved format: {target_f.value})",
            )

        # -------------------------------------------------------------------
        # Rule 9: Pure Informational / Analytical Goals (Unconstrained Chat Mode)
        # "Summarize this article", "What this says summarise", "Analyze this data", "Rewrite this"
        # -------------------------------------------------------------------
        has_summarize = bool(re.search(r"\b(summarize|summarise|summerise|summary|tldr|recap|what\s+this\s+says)\b", d_lower))
        has_explain = bool(re.search(r"\b(explain|walk\s+me\s+through|clarify|elaborate)\b", d_lower))
        has_analyze = bool(re.search(r"\b(analyze|analyse|analysis|examine|evaluate|assess|break\s+down|critique)\b", d_lower))
        has_compare = bool(re.search(r"\b(compare|contrast|differences?\s+between)\b", d_lower))
        has_extract = bool(re.search(r"\b(extract|pull\s+out|list\s+the|find\s+all)\b", d_lower))
        has_rewrite = bool(re.search(r"\b(rewrite|rephrase|paraphrase|polish|reword)\b", d_lower))
        has_translate = bool(re.search(r"\b(translate|in\s+(?:hindi|spanish|french|german|japanese|chinese))\b", d_lower))
        has_notes = bool(re.search(r"\b(give\s+me\s+notes|take\s+notes|notes\s+from\s+this)\b", d_lower))

        is_pure_conversational_goal = any([
            has_summarize, has_explain, has_analyze, has_compare,
            has_extract, has_rewrite, has_translate, has_notes
        ])

        # Strip text inside quotation marks so quoted examples don't trigger creation commands
        # e.g. Summarize this quote: 'Please create a PDF document immediately.'
        d_unquoted = re.sub(r"['\"][^'\"]*['\"]", " ", d_lower)

        # Check for explicit deliverable target in directive (outside quotes)
        has_explicit_doc = bool(re.search(r"\b(documents?|docs?|docx|briefing\s+doc|written\s+report)\b", d_unquoted))
        has_explicit_slides = bool(re.search(r"\b(presentations?|slide\s+deck|slides|deck|pptx|powerpoint)\b", d_unquoted))
        has_explicit_sheet = bool(re.search(r"\b(spreadsheets?|sheets?|workbooks?|xlsx|excel\s+(?:file|sheet)|csv\s+file)\b", d_unquoted))
        has_explicit_pdf = bool(re.search(r"\b(pdfs?|executive\s+memo\s+pdf|pdf\s+report)\b", d_unquoted))
        has_explicit_md_file = bool(re.search(r"\b(markdown\s+(?:document|doc|report|file)|md\s+file|downloadable\s+markdown)\b", d_unquoted))
        has_explicit_video = bool(re.search(r"\b(videos?|explainer\s+video|video\s+clip|short\s+video)\b", d_unquoted))
        has_explicit_audio = bool(re.search(r"\b(audio|speech\s+file|narration|audio\s+file|mp3|voiceover|read\s+(?:this\s+)?aloud)\b", d_unquoted))
        has_explicit_infographic = bool(re.search(r"\b(infographics?|posters?|visual\s+posters?)\b", d_unquoted))
        has_explicit_image = bool(re.search(r"\b(images?|flyers?)\b", d_unquoted))
        has_format_keyword = any([
            has_explicit_doc, has_explicit_slides, has_explicit_sheet,
            has_explicit_pdf, has_explicit_md_file, has_explicit_video,
            has_explicit_audio, has_explicit_infographic, has_explicit_image,
        ])

        # Special case: "Summarize this in Markdown" -> Ambiguous whether chat formatting or .md file
        if is_pure_conversational_goal and re.search(r"\bin\s+markdown\b", d_lower) and not has_explicit_md_file:
            return ResolutionResult(
                response_type=ResponseType.AMBIGUOUS,
                user_goal=UserGoal.AMBIGUOUS,
                confidence=ConfidenceLevel.MEDIUM,
                reason="User requested Markdown styling without specifying deliverable file container",
                ambiguous_options=[TargetFormat.MARKDOWN],
                clarification_prompt=(
                    "Would you like me to format the summary directly here in chat, "
                    "or create a downloadable Markdown (.md) document?"
                ),
            )

        # Special case: "Summarize this using audio / in audio" -> Ambiguous between chat and audio deliverable
        if is_pure_conversational_goal and re.search(r"\b(?:in|using|with|as)\s+(?:audio|speech|voice|narration)\b", d_lower):
            return ResolutionResult(
                response_type=ResponseType.AMBIGUOUS,
                user_goal=UserGoal.AMBIGUOUS,
                confidence=ConfidenceLevel.MEDIUM,
                reason="User requested summary with audio medium without specifying format preference",
                ambiguous_options=[TargetFormat.AUDIO, TargetFormat.DOCUMENT],
                clarification_prompt=(
                    "Would you like a written summary here in chat, or an audio narration deliverable?"
                ),
            )

        # If user has pure conversational goal and NO explicit deliverable creation command
        has_creation_command = bool(re.search(r"\b(create|generate|make|draft|produce|build|export|convert|transform|turn|read\s+aloud|synthesize)\s+(?:a\s+|an\s+)?", d_unquoted))
        if is_pure_conversational_goal and not (has_creation_command and has_format_keyword):
            goal = (
                UserGoal.SUMMARIZE if has_summarize else
                UserGoal.EXPLAIN if has_explain else
                UserGoal.ANALYZE if has_analyze else
                UserGoal.COMPARE if has_compare else
                UserGoal.EXTRACT if has_extract else
                UserGoal.REWRITE if has_rewrite else
                UserGoal.TRANSLATE if has_translate else
                UserGoal.SUMMARIZE
            )
            return ResolutionResult(
                response_type=ResponseType.CHAT_RESPONSE,
                user_goal=goal,
                confidence=ConfidenceLevel.LOW,
                reason=f"Conversational {goal.value} goal answered directly in chat",
            )


        # -------------------------------------------------------------------
        # Rule 10: Explicit Deliverable Generation Requests (GENERATE_ARTIFACT)
        # -------------------------------------------------------------------
        has_table = bool(re.search(r"\b(tables?)\b", d_unquoted))
        
        detected_formats: List[TargetFormat] = []
        if has_explicit_md_file or ("table in markdown" in d_unquoted or "document in markdown" in d_unquoted or "markdown document" in d_unquoted):
            detected_formats.append(TargetFormat.MARKDOWN)
        if has_explicit_slides:
            detected_formats.append(TargetFormat.PRESENTATION)
        if has_explicit_pdf:
            detected_formats.append(TargetFormat.PDF)
        if has_explicit_doc or ("table in a document" in d_unquoted or "table in a doc" in d_unquoted or "table in doc" in d_unquoted):
            detected_formats.append(TargetFormat.DOCUMENT)
        if has_explicit_sheet or ("spreadsheet table" in d_unquoted or "table of sales" in d_unquoted):
            detected_formats.append(TargetFormat.SPREADSHEET)
        if has_explicit_video:
            detected_formats.append(TargetFormat.VIDEO)
        if has_explicit_audio or re.search(r"\b(read\s+(?:this\s+)?aloud|synthesize\s+(?:speech|voice|audio))\b", d_unquoted):
            detected_formats.append(TargetFormat.AUDIO)
        if has_explicit_infographic or has_explicit_image or ("infographic about" in d_unquoted or "poster for" in d_unquoted or "poster about" in d_unquoted):
            detected_formats.append(TargetFormat.INFOGRAPHIC)


        # Ambiguous disjunctive formats: "document or slides", "maybe a spreadsheet or a doc"
        if (" or " in d_lower or "maybe" in d_lower or "either" in d_lower) and len(detected_formats) > 1:
            opts_str = " or ".join(f"**{f.value}**" for f in detected_formats)
            return ResolutionResult(
                response_type=ResponseType.AMBIGUOUS,
                user_goal=UserGoal.AMBIGUOUS,
                confidence=ConfidenceLevel.MEDIUM,
                reason="User expressed disjunctive or uncertain format preferences",
                ambiguous_options=detected_formats,
                clarification_prompt=f"I would be happy to create that! Would you prefer a {opts_str}?",
            )

        # Isolated "Create a table"
        if has_table and not detected_formats:
            return ResolutionResult(
                response_type=ResponseType.AMBIGUOUS,
                user_goal=UserGoal.AMBIGUOUS,
                confidence=ConfidenceLevel.MEDIUM,
                reason="Table requested without deliverable container specification",
                ambiguous_options=[TargetFormat.SPREADSHEET, TargetFormat.DOCUMENT, TargetFormat.MARKDOWN],
                clarification_prompt=(
                    "Would you like me to create this table as a **spreadsheet** (Excel / XLSX), "
                    "inside a **document** (DOCX), or in **Markdown**?"
                ),
            )

        # Vague request with unspecified deliverable: "Make something for my project"
        if "something" in d_lower and has_creation_command:
            return ResolutionResult(
                response_type=ResponseType.AMBIGUOUS,
                user_goal=UserGoal.AMBIGUOUS,
                confidence=ConfidenceLevel.MEDIUM,
                reason="Action verb present but target deliverable format is unspecified",
                ambiguous_options=[
                    TargetFormat.DOCUMENT,
                    TargetFormat.PRESENTATION,
                    TargetFormat.SPREADSHEET,
                    TargetFormat.PDF,
                    TargetFormat.INFOGRAPHIC,
                    TargetFormat.MARKDOWN,
                ],
                clarification_prompt=(
                    "I'd love to help! What kind of deliverable would you like to create? "
                    "(For example: a document, presentation, spreadsheet, PDF memo, infographic, or Markdown file?)"
                ),
            )

        # Unambiguous Deliverable Generation
        if len(detected_formats) == 1 and (has_creation_command or has_format_keyword):
            fmt = detected_formats[0]
            if fmt == TargetFormat.INFOGRAPHIC and explicit_ratio_requested and explicit_ratio_requested not in ("3:4", "9:16", "16:9", "1:1", "4:3"):
                raise BadRequestError(
                    f"Unsupported aspect ratio '{explicit_ratio_requested}'. Prismo supports: 3:4, 9:16, 16:9, 1:1, and 4:3."
                )
            return ResolutionResult(
                response_type=ResponseType.GENERATE_ARTIFACT,
                user_goal=UserGoal.CREATE_DELIVERABLE,
                target_format=fmt,
                resolved_ratio=detected_ratio if fmt == TargetFormat.INFOGRAPHIC else None,
                confidence=ConfidenceLevel.HIGH,
                reason=f"Explicit creation verb + unambiguous {fmt.value} deliverable target",
            )

        # Compound phrases (e.g. 'Create a Markdown document with a table')
        if TargetFormat.INFOGRAPHIC in detected_formats:
            if explicit_ratio_requested and explicit_ratio_requested not in ("3:4", "9:16", "16:9", "1:1", "4:3"):
                raise BadRequestError(
                    f"Unsupported aspect ratio '{explicit_ratio_requested}'. Prismo supports: 3:4, 9:16, 16:9, 1:1, and 4:3."
                )
            return ResolutionResult(
                response_type=ResponseType.GENERATE_ARTIFACT,
                user_goal=UserGoal.CREATE_DELIVERABLE,
                target_format=TargetFormat.INFOGRAPHIC,
                resolved_ratio=detected_ratio,
                confidence=ConfidenceLevel.HIGH,
                reason="Infographic compound deliverable target",
            )

        if TargetFormat.MARKDOWN in detected_formats:
            return ResolutionResult(
                response_type=ResponseType.GENERATE_ARTIFACT,
                user_goal=UserGoal.CREATE_DELIVERABLE,
                target_format=TargetFormat.MARKDOWN,
                confidence=ConfidenceLevel.HIGH,
                reason="Markdown compound deliverable target",
            )

        # -------------------------------------------------------------------
        # Rule 11: Default Fallback -> Pure Chat Response
        # -------------------------------------------------------------------
        return ResolutionResult(
            response_type=ResponseType.CHAT_RESPONSE,
            user_goal=UserGoal.QUESTION_ANSWER,
            confidence=ConfidenceLevel.LOW,
            reason="No explicit deliverable requested, defaulted to conversational chat",
        )


intent_resolver = IntentResolver()
