"""File-backed Skill Registry for Limo Agent Infrastructure.

Implements progressive disclosure:
- Tier 1: Discovery catalog (lightweight metadata) for system prompt.
- Tier 2: Progressive loading of full markdown instructions (SKILL.md) upon activation.
- Multi-dimensional matching: mode, intent, and trigger keywords (MUST-FIX #4).
"""

import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import yaml

from .models import SkillDefinition
from ..context import AgentContext

logger = logging.getLogger("limo.agent.skills")


class SkillRegistry:
    """Registry discovering and managing file-backed skills (SKILL.md)."""

    def __init__(self, skills_dir: Optional[Path] = None, root_skills_dir: Optional[Path] = None) -> None:
        self.skills_dir = skills_dir or (Path(__file__).parent / "builtin")
        self.root_skills_dir = root_skills_dir or (Path(__file__).resolve().parents[4] / "skills")
        self._skills: Dict[str, SkillDefinition] = {}
        self.discover()

    def register(self, skill: SkillDefinition) -> None:
        """Register a parsed skill definition."""
        self._skills[skill.name.lower()] = skill

    def get_skill(self, name: str) -> Optional[SkillDefinition]:
        """Retrieve a full skill definition by name."""
        return self._skills.get(name.lower())

    def list_catalog(self) -> List[Dict[str, Any]]:
        """Return Tier 1 metadata catalog for system prompt inclusion."""
        return [skill.to_catalog_summary() for skill in self._skills.values()]

    def list_skills(self) -> List[SkillDefinition]:
        """Return all registered skill objects."""
        return list(self._skills.values())

    def match_skills(
        self,
        prompt: str,
        mode: Optional[str] = None,
        intent: Optional[str] = None,
        context: Optional[AgentContext] = None,
    ) -> List[SkillDefinition]:
        """Match and activate skills based on mode, intent, and prompt triggers (MUST-FIX #4).
        
        Evaluates:
        1. Explicit feature mode (e.g. 'docs', 'slides', 'video', 'spreadsheet')
        2. Explicit intent (e.g. 'research', 'validate', 'generate_brief')
        3. Trigger keywords or phrases in the user prompt
        """
        matched: Dict[str, SkillDefinition] = {}
        prompt_lower = prompt.lower() if prompt else ""
        norm_mode = mode.lower().strip() if mode else None
        norm_intent = intent.lower().strip() if intent else None

        # Check context for mode if not explicitly passed
        if not norm_mode and context and getattr(context, "active_mode", None):
            raw_mode = context.active_mode
            norm_mode = raw_mode.value if hasattr(raw_mode, "value") else str(raw_mode)
            norm_mode = norm_mode.lower().strip()

        for name, skill in self._skills.items():
            # 1. Mode matching
            if norm_mode and any(norm_mode == m.lower() for m in skill.modes):
                matched[name] = skill
                continue

            # 2. Intent matching
            if norm_intent and any(norm_intent == i.lower() for i in skill.intents):
                matched[name] = skill
                continue

            # 3. Trigger keyword matching in prompt
            if prompt_lower:
                for trigger in skill.triggers:
                    trig_lower = trigger.lower().strip()
                    # Check substring or regex word boundary match
                    if trig_lower in prompt_lower:
                        matched[name] = skill
                        break
                    elif re.search(r"\b" + re.escape(trig_lower) + r"\b", prompt_lower):
                        matched[name] = skill
                        break

        return list(matched.values())

    def discover(self) -> None:
        """Scan skills directories (root skills/ and builtin/) for SKILL.md and load them."""
        # 1. Scan builtin skills
        if self.skills_dir.exists() and self.skills_dir.is_dir():
            for skill_md in self.skills_dir.glob("**/SKILL.md"):
                try:
                    skill = self._parse_skill_file(skill_md)
                    self.register(skill)
                    logger.debug("Discovered builtin skill '%s' from %s", skill.name, skill_md)
                except Exception as e:
                    logger.error("Failed to parse skill at %s: %s", skill_md, e)

        # 2. Scan repository root skills/ (Claude/Codex-style modular skills)
        if self.root_skills_dir.exists() and self.root_skills_dir.is_dir():
            for skill_md in self.root_skills_dir.glob("**/SKILL.md"):
                try:
                    skill = self._parse_skill_file(skill_md)
                    self.register(skill)
                    logger.debug("Discovered root skill '%s' from %s", skill.name, skill_md)
                except Exception as e:
                    logger.error("Failed to parse root skill at %s: %s", skill_md, e)

    def _parse_skill_file(self, file_path: Path) -> SkillDefinition:
        """Parse YAML frontmatter and markdown body from a SKILL.md file."""
        content = file_path.read_text(encoding="utf-8")
        
        # Match YAML frontmatter between --- and ---
        frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        if not frontmatter_match:
            # Fallback if no frontmatter delimiters: use folder name as skill name
            return SkillDefinition(
                name=file_path.parent.name,
                description=f"Skill from {file_path.parent.name}",
                system_instructions=content,
                path=str(file_path.resolve()),
            )

        fm_text = frontmatter_match.group(1)
        body = frontmatter_match.group(2).strip()

        data = yaml.safe_load(fm_text) or {}
        
        name = str(data.get("name") or file_path.parent.name)
        description = str(data.get("description") or "")
        version = str(data.get("version") or "1.0.0")
        category = str(data.get("category") or "general")
        triggers = list(data.get("triggers") or [])
        deliverables = list(data.get("deliverables") or [])
        modes = list(data.get("modes") or [])
        intents = list(data.get("intents") or [])
        supported_inputs = list(data.get("supported_inputs") or [])
        supported_outputs = list(data.get("supported_outputs") or [])
        required_tools = list(data.get("required_tools") or [])

        return SkillDefinition(
            name=name,
            description=description,
            version=version,
            category=category,
            triggers=triggers,
            deliverables=deliverables,
            modes=modes,
            intents=intents,
            supported_inputs=supported_inputs,
            supported_outputs=supported_outputs,
            required_tools=required_tools,
            system_instructions=body,
            path=str(file_path.resolve()),
        )
