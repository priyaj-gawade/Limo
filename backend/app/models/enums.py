"""Explicit domain enums for Limo.

Maintains strict separation between:
- FeatureMode: Frontend conversational interaction mode
- OutputFormat: The 7 required SIH transformation deliverables
"""

from enum import StrEnum


class FeatureMode(StrEnum):
    """Conversational creation modes available in the Limo frontend."""
    NONE = "none"
    DOCS = "docs"
    SLIDES = "slides"
    SHEETS = "sheets"
    VIDEO = "video"
    AUDIO = "audio"
    WEBSITES = "websites"
    CODE = "code"


class OutputFormat(StrEnum):
    """The transformation output deliverables across Limo."""
    VIDEO = "video"
    LINKEDIN = "linkedin"
    TWITTER = "twitter"
    ADVISORY = "advisory"
    INFOGRAPHIC = "infographic"
    SUMMARY = "summary"
    PRESENTATION = "presentation"
    DOCUMENT = "document"
    SPREADSHEET = "spreadsheet"
    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"
    AUDIO = "audio"


class SourceType(StrEnum):
    """Types of ingested multi-modal raw sources."""
    FILE = "file"
    URL = "url"
    TEXT = "text"
    AUDIO = "audio"
    VIDEO = "video"
    TABULAR = "tabular"


class MessageRole(StrEnum):
    """Chat message turn identity."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class JobState(StrEnum):
    """Lifecycle state of an asynchronous transformation job."""
    QUEUED = "queued"
    PROCESSING = "processing"
    WAITING_EXTERNAL = "waiting_external"
    PARTIALLY_COMPLETED = "partially_completed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStatus(StrEnum):
    """Execution status of an orchestration workflow."""
    PENDING = "pending"
    RUNNING = "running"
    STAGE_COMPLETED = "stage_completed"
    COMPLETED = "completed"
    WAITING_EXTERNAL = "waiting_external"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DetailLevel(StrEnum):
    """Granularity of generated transformation content."""
    CONCISE = "concise"
    STANDARD = "standard"
    DETAILED = "detailed"
    ANALYTICAL = "analytical"
    COMPREHENSIVE = "comprehensive"


class CommunicationObjective(StrEnum):
    """Target strategic objective for transformed deliverables."""
    INFORM = "inform"
    PERSUADE = "persuade"
    ALERT = "alert"
    EDUCATE = "educate"
    SYNTHESIZE = "synthesize"


class ContentStyle(StrEnum):
    """Editorial style guide applied to deliverables."""
    CORPORATE = "corporate"
    JOURNALISTIC = "journalistic"
    ACADEMIC = "academic"
    SOCIAL_FIRST = "social_first"


class ArtifactType(StrEnum):
    """Deliverable artifact classification."""
    DOC = "doc"
    SLIDE = "slide"
    SHEET = "sheet"
    VIDEO = "video"
    WEBSITE = "website"
    CODE = "code"
    POST = "post"
    INFOGRAPHIC = "infographic"
    AUDIO = "audio"


class ValidationStatus(StrEnum):
    """Status of citation and factuality validation."""
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"
