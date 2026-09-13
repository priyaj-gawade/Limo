"""Data models for Limo Agent Skills system."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SkillDefinition(BaseModel):
    """Parsed representation of a file-backed skill (SKILL.md)."""

    name: str = Field(description="Unique skill name identifier (e.g. 'document', 'presentation')")
    description: str = Field(description="One-line summary of what the skill produces or guides")
    category: str = Field(default="general", description="Skill classification (e.g. 'deliverable', 'analysis', 'audit')")
    triggers: List[str] = Field(default_factory=list, description="Keywords or regex phrases that activate the skill")
    deliverables: List[str] = Field(default_factory=list, description="Associated OutputFormats or deliverable types")
    modes: List[str] = Field(default_factory=list, description="Associated FeatureMode strings (e.g. 'docs', 'slides', 'video')")
    intents: List[str] = Field(default_factory=list, description="Recognized agent intents or high-level user goals")
    required_tools: List[str] = Field(default_factory=list, description="Names of tools frequently needed by this skill")
    system_instructions: str = Field(default="", description="Complete markdown instruction body (Tier 2 progressive disclosure)")
    path: Optional[str] = Field(default=None, description="Absolute filesystem path to the SKILL.md file")

    def to_catalog_summary(self) -> Dict[str, Any]:
        """Tier 1 metadata summary for inclusion in system prompt / discovery catalog."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "triggers": self.triggers,
            "deliverables": self.deliverables,
            "modes": self.modes,
        }
