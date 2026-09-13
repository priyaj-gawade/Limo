"""Unit tests for Limo Agent Skills and SkillRegistry."""

import pytest
from app.agent.skills import SkillRegistry, SkillDefinition
from app.agent.context import AgentContext


def test_builtin_skill_discovery():
    """Verify that all 6 builtin skills are discovered and parsed accurately."""
    registry = SkillRegistry()
    skills = registry.list_skills()
    assert len(skills) == 6

    names = {s.name for s in skills}
    expected = {"document", "presentation", "spreadsheet", "video", "research", "validation"}
    assert names == expected


def test_tier1_catalog_compactness():
    """Verify Tier 1 catalog returns lightweight summaries suitable for system prompts."""
    registry = SkillRegistry()
    catalog = registry.list_catalog()
    assert len(catalog) == 6

    for entry in catalog:
        assert "name" in entry
        assert "description" in entry
        assert "category" in entry
        assert "triggers" in entry
        assert "deliverables" in entry
        # Must NOT include large markdown body in Tier 1 catalog
        assert "system_instructions" not in entry


def test_tier2_progressive_loading():
    """Verify Tier 2 loading retrieves complete markdown instructions."""
    registry = SkillRegistry()
    doc_skill = registry.get_skill("document")
    assert doc_skill is not None
    assert "Document Generation & Synthesis Skill" in doc_skill.system_instructions
    assert "Executive Summary" in doc_skill.system_instructions
    assert doc_skill.category == "deliverable"


def test_multidimensional_skill_matching():
    """MUST-FIX #4: Verify skill matching works via mode, intent, and prompt triggers."""
    registry = SkillRegistry()

    # 1. Mode matching
    matched_slides = registry.match_skills(prompt="", mode="slides")
    assert any(s.name == "presentation" for s in matched_slides)

    matched_docs = registry.match_skills(prompt="", mode="docs")
    assert any(s.name == "document" for s in matched_docs)

    # 2. Intent matching
    matched_intent = registry.match_skills(prompt="", intent="deep_research")
    assert any(s.name == "research" for s in matched_intent)

    matched_val_intent = registry.match_skills(prompt="", intent="validate_artifact")
    assert any(s.name == "validation" for s in matched_val_intent)

    # 3. Prompt keyword trigger matching
    matched_prompt = registry.match_skills(prompt="Please build a financial model for Q3 revenues")
    assert any(s.name == "spreadsheet" for s in matched_prompt)

    matched_video_prompt = registry.match_skills(prompt="Create an engaging video script with scene pacing")
    assert any(s.name == "video" for s in matched_video_prompt)

    # 4. Context fallback
    from app.models.enums import FeatureMode
    context = AgentContext(session_id="dummy", active_mode=FeatureMode.SLIDES)
    matched_context = registry.match_skills(prompt="", context=context)
    assert any(s.name == "presentation" for s in matched_context)
