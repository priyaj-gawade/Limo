"""API endpoints for agent skills discovery (D10.6)."""

from typing import Any, Dict, List
from fastapi import APIRouter
from ...agent.skills import SkillRegistry

router = APIRouter(prefix="/skills", tags=["Skills"])

_registry = SkillRegistry()


@router.get("", response_model=List[Dict[str, Any]])
async def list_skills() -> List[Dict[str, Any]]:
    """List all discovered skills across root skills/ and builtin directories."""
    return [skill.to_catalog_summary() for skill in _registry.list_skills()]


@router.get("/{skill_name}")
async def get_skill(skill_name: str) -> Dict[str, Any]:
    """Retrieve full skill definition including instructions."""
    skill = _registry.get_skill(skill_name)
    if not skill:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
    data = skill.model_dump()
    return data
