import os
import re
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger("neuroweave.skill_loader")


class Skill(BaseModel):
    """
    Data model representing an AAS (Agent Architecture Standard) skill / playbook.
    """
    name: str
    description: str = ""
    domain: str = ""
    keywords: List[str] = Field(default_factory=list)
    version: str = "1.0.0"
    content: str = ""
    filepath: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Returns metadata dictionary for the skill."""
        return {
            "name": self.name,
            "description": self.description,
            "domain": self.domain,
            "keywords": self.keywords,
            "version": self.version,
            "filepath": self.filepath,
        }

    @property
    def frontmatter_yaml(self) -> str:
        """Returns the formatted YAML frontmatter string."""
        kw_str = ", ".join(f"'{k}'" for k in self.keywords)
        return (
            f"---\n"
            f"name: {self.name}\n"
            f"domain: {self.domain}\n"
            f"version: {self.version}\n"
            f"description: \"{self.description}\"\n"
            f"keywords: [{kw_str}]\n"
            f"---"
        )

    def to_working_memory_dict(self) -> Dict[str, Any]:
        """Returns comprehensive working memory representation including frontmatter, keywords, and playbook."""
        return {
            "name": self.name,
            "domain": self.domain,
            "version": self.version,
            "description": self.description,
            "keywords": list(self.keywords),
            "frontmatter": self.frontmatter_yaml,
            "playbook": self.content,
            "filepath": self.filepath
        }

    def to_full_context(self) -> str:
        """Returns formatted markdown block with frontmatter, keywords, and execution playbook."""
        return (
            f"[Skill: {self.name}]\n"
            f"{self.frontmatter_yaml}\n\n"
            f"### EXECUTION PLAYBOOK ({self.domain}):\n"
            f"{self.content}"
        )


def parse_skill_file(filepath: Union[str, Path]) -> Optional[Skill]:
    """
    Parses a SKILL.md file with YAML frontmatter and body content.
    Extracts metadata from frontmatter and markdown instructions from content.
    """
    path = Path(filepath).resolve()
    if not path.is_file():
        logger.warning(f"Skill file does not exist: {path}")
        return None

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw_text = f.read()
    except Exception as e:
        logger.error(f"Error reading skill file {path}: {e}")
        return None

    frontmatter: Dict[str, Any] = {}
    content = raw_text

    # Parse YAML frontmatter
    lines = raw_text.splitlines()
    first_non_empty = 0
    while first_non_empty < len(lines) and not lines[first_non_empty].strip():
        first_non_empty += 1

    if first_non_empty < len(lines) and lines[first_non_empty].strip() == "---":
        closing_idx = -1
        for i in range(first_non_empty + 1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                closing_idx = i
                break

        if closing_idx != -1:
            fm_text = "\n".join(lines[first_non_empty + 1:closing_idx])
            content = "\n".join(lines[closing_idx + 1:]).strip()
            try:
                loaded = yaml.safe_load(fm_text)
                if isinstance(loaded, dict):
                    frontmatter = loaded
                else:
                    logger.warning(f"YAML frontmatter in {path} is not a dictionary: {loaded}")
            except Exception as e:
                logger.warning(f"Failed to parse YAML frontmatter in {path}: {e}")
        else:
            content = raw_text.strip()
    else:
        content = raw_text.strip()

    # Extract name (fallback to directory or filename)
    name = frontmatter.get("name")
    if not name or not str(name).strip():
        parent_dir = path.parent.name
        if parent_dir and parent_dir.lower() not in ("skills", ".", ""):
            name = parent_dir.replace("-", " ").replace("_", " ").title()
        else:
            name = path.stem.replace("-", " ").replace("_", " ").title()

    description = str(frontmatter.get("description", "") or "").strip()
    domain = str(frontmatter.get("domain", "") or "").strip()
    version = str(frontmatter.get("version", "1.0.0") or "1.0.0").strip()

    # Parse keywords list, tags list, or comma-separated string
    raw_keywords = frontmatter.get("keywords", [])
    if not raw_keywords:
        raw_keywords = frontmatter.get("tags", [])
    keywords: List[str] = []
    if isinstance(raw_keywords, list):
        keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]
    elif isinstance(raw_keywords, str):
        keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]

    return Skill(
        name=str(name).strip(),
        description=description,
        domain=domain,
        keywords=keywords,
        version=version,
        content=content.strip(),
        filepath=str(path),
    )


class SkillCatalog:
    """
    In-memory catalog for discovering, indexing, matching, and formatting
    domain skills and playbooks for LLM prompt injection.
    """

    def __init__(self, skills_dir: Union[str, Path] = "skills"):
        self.raw_skills_dir = skills_dir
        self.skills_dir = self._resolve_skills_dir(skills_dir)
        self.skills: Dict[str, Skill] = {}
        self.load_skills()

    def _resolve_skills_dir(self, skills_dir: Union[str, Path]) -> Path:
        """
        Resolves skills directory path supporting relative paths from current working
        directory and project root.
        """
        path = Path(skills_dir)
        if path.is_absolute() and path.exists():
            return path

        # Check relative to cwd
        cwd_path = Path.cwd() / path
        if cwd_path.exists():
            return cwd_path.resolve()

        # Check relative to project root (parent of core/)
        project_root = Path(__file__).resolve().parent.parent / path
        if project_root.exists():
            return project_root.resolve()

        # Default fallback to cwd_path even if not yet existing
        return cwd_path.resolve()

    def load_skills(self) -> None:
        """
        Discovers all `skills/**/SKILL.md` files from the skills directory,
        parses frontmatter and content, and caches skills in memory.
        """
        self.skills.clear()
        if not self.skills_dir.exists() or not self.skills_dir.is_dir():
            logger.info(f"Skills directory '{self.skills_dir}' does not exist. Initialized with 0 skills.")
            return

        try:
            # Case-insensitive discovery for SKILL.md files
            skill_files = [
                p for p in self.skills_dir.rglob("*.md")
                if p.name.lower() == "skill.md" and p.is_file()
            ]
        except Exception as e:
            logger.error(f"Error scanning skills directory '{self.skills_dir}': {e}")
            return

        for file_path in skill_files:
            try:
                skill = parse_skill_file(file_path)
                if skill:
                    self.skills[skill.name] = skill
                    logger.debug(f"Loaded skill: '{skill.name}' from {file_path}")
            except Exception as e:
                logger.warning(f"Error loading skill file '{file_path}': {e}")

        logger.info(f"Loaded {len(self.skills)} domain skills from {self.skills_dir}")

    def reload(self) -> None:
        """Forces a reload of all skills from disk."""
        self.skills_dir = self._resolve_skills_dir(self.raw_skills_dir)
        self.load_skills()

    def get_skill(self, name: str) -> Optional[Skill]:
        """Retrieves a skill by name (case-insensitive and hyphen/underscore-tolerant)."""
        if not name:
            return None
        target = name.strip().lower()
        target_norm = target.replace("-", "_")
        for skill_name, skill in self.skills.items():
            if skill_name.lower() == target or skill_name.lower().replace("-", "_") == target_norm:
                return skill
        return None

    def match_skills(self, query: str, top_k: int = 2, min_score: float = 3.5) -> List[Skill]:
        """
        Scores skills against the query using keyword matches (supporting underscore/hyphen variations),
        domain relevance, name overlap, and content alignment. Returns top_k matching skills exceeding min_score.
        """
        if not query or not query.strip() or not self.skills or top_k <= 0:
            return []

        query_lower = query.lower().strip()
        query_tokens = set(re.findall(r"\b[a-z0-9_]+\b", query_lower))
        if not query_tokens:
            return []

        scored_skills: List[Tuple[float, Skill]] = []

        for skill in self.skills.values():
            score = 0.0

            # 1. Keyword Matches (exact phrase, normalized space/underscore, or token overlap)
            for kw in skill.keywords:
                kw_clean = kw.lower().strip()
                if not kw_clean:
                    continue
                kw_spaces = kw_clean.replace('_', ' ').replace('-', ' ')
                
                # Check multi-word keyword
                if ' ' in kw_spaces:
                    if kw_spaces in query_lower or kw_clean in query_lower:
                        score += 8.0
                    else:
                        kw_subtokens = [w for w in kw_spaces.split() if len(w) > 2]
                        overlap_count = sum(1 for w in kw_subtokens if w in query_tokens)
                        if overlap_count >= 2:
                            score += overlap_count * 2.5
                else:
                    if kw_clean in query_tokens:
                        score += 6.0
                    elif re.search(r'\b' + re.escape(kw_clean) + r'\b', query_lower):
                        score += 4.0

            # 2. Domain Relevance
            if skill.domain:
                domain_clean = skill.domain.lower().strip()
                if domain_clean in query_lower:
                    score += 6.0
                else:
                    domain_tokens = set(re.findall(r"\b[a-z0-9_]+\b", domain_clean)) - {"and", "for", "the", "with", "of", "in"}
                    d_overlap = domain_tokens.intersection(query_tokens)
                    score += len(d_overlap) * 2.5

            # 3. Skill Name Overlap
            name_clean = skill.name.lower().replace("-", " ").replace("_", " ").strip()
            if name_clean in query_lower:
                score += 8.0
            else:
                name_tokens = set(re.findall(r"\b[a-z0-9_]+\b", name_clean))
                name_overlap = name_tokens.intersection(query_tokens)
                score += len(name_overlap) * 3.0

            # 4. Description Word Overlap
            if skill.description:
                desc_clean = skill.description.lower().strip()
                desc_tokens = set(re.findall(r"\b[a-z0-9_]+\b", desc_clean)) - {"and", "for", "the", "with", "of", "in", "to"}
                desc_overlap = desc_tokens.intersection(query_tokens)
                score += len(desc_overlap) * 1.0

            # 5. Content Word Overlap (lightweight term overlap)
            if skill.content:
                content_sample = skill.content.lower()[:3000]
                content_tokens = set(re.findall(r"\b[a-z0-9_]+\b", content_sample))
                content_overlap = content_tokens.intersection(query_tokens)
                score += min(len(content_overlap) * 0.15, 2.0)

            if score >= min_score:
                scored_skills.append((score, skill))

        # Sort descending by score
        scored_skills.sort(key=lambda item: item[0], reverse=True)
        return [skill for _, skill in scored_skills[:top_k]]

    def get_skill_prompt_injection(self, matched_skills: List[Skill]) -> str:
        """
        Formats matched skills into a comprehensive Markdown prompt block containing
        YAML frontmatter, domain keywords, and full execution playbooks:
        === ACTIVE DOMAIN PLAYBOOKS (AAS SKILLS) ===
        """
        if not matched_skills:
            return ""

        blocks = []
        for skill in matched_skills:
            blocks.append(skill.to_full_context())

        body = "\n\n".join(blocks)
        return f"=== ACTIVE DOMAIN PLAYBOOKS (AAS SKILLS) ===\n{body}"

    def get_skills_working_memory(self, matched_skills: List[Skill]) -> Dict[str, Any]:
        """
        Formats matched skills for direct injection into Working Memory context.
        """
        if not matched_skills:
            return {}
        return {
            "active_skills_names": [s.name for s in matched_skills],
            "active_skills_metadata": [s.to_dict() for s in matched_skills],
            "active_skills_keywords": {s.name: list(s.keywords) for s in matched_skills},
            "active_skills_frontmatter": {s.name: s.frontmatter_yaml for s in matched_skills},
            "active_skills_playbooks": self.get_skill_prompt_injection(matched_skills)
        }

    def list_skills(self) -> List[Dict[str, Any]]:
        """
        Returns metadata for all available skills in the catalog.
        """
        return [skill.to_dict() for skill in self.skills.values()]

    def __len__(self) -> int:
        return len(self.skills)

    def __repr__(self) -> str:
        return f"<SkillCatalog(skills_dir='{self.skills_dir}', total_skills={len(self.skills)})>"


# Global singleton instance cache
_GLOBAL_SKILL_CATALOG: Optional[SkillCatalog] = None


def get_skill_catalog(skills_dir: str = "skills", force_reload: bool = False) -> SkillCatalog:
    """
    Returns the global singleton instance of SkillCatalog.
    If force_reload is True, reloads the catalog from disk.
    """
    global _GLOBAL_SKILL_CATALOG
    if _GLOBAL_SKILL_CATALOG is None or force_reload:
        _GLOBAL_SKILL_CATALOG = SkillCatalog(skills_dir=skills_dir)
    return _GLOBAL_SKILL_CATALOG
