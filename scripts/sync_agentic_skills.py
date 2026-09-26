import os
import sys
import shutil
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Source of cloned AAS skills
AAS_SKILLS_DIR = Path("scratch/agentic_awesome_skills/skills")
DEST_SKILLS_DIR = Path("skills")

# High-impact domain skills to sync for multi-agent workflows
SELECTED_SKILLS = [
    "deep-research",
    "competitor-analysis",
    "market-analysis",
    "financial_valuation",
    "tech_architecture",
    "fact_checking",
    "data_visualization",
    "code-review-excellence",
    "api-security",
    "kpi-dashboard-design",
    "customer-research",
    "launch-strategy",
    "system-architecture",
    "debugging-toolkit"
]

def sync_skills():
    print("=" * 60)
    print("🔄 SYNCING AGENTIC AWESOME SKILLS (AAS) INTO NEUROWEAVE")
    print("=" * 60)
    
    DEST_SKILLS_DIR.mkdir(exist_ok=True)
    synced_count = 0

    # Scan AAS cloned directory
    if AAS_SKILLS_DIR.exists():
        for skill_dir in AAS_SKILLS_DIR.iterdir():
            if skill_dir.is_dir() and skill_dir.name in SELECTED_SKILLS:
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    target_dir = DEST_SKILLS_DIR / skill_dir.name
                    target_dir.mkdir(exist_ok=True)
                    shutil.copy2(skill_md, target_dir / "SKILL.md")
                    print(f"  [+] Synced AAS skill: {skill_dir.name} -> skills/{skill_dir.name}/SKILL.md")
                    synced_count += 1

    print(f"\nSuccessfully synced {synced_count} high-impact skills into NeuroWeave.")
    
    # Reload SkillCatalog to verify
    from core.skill_loader import get_skill_catalog
    catalog = get_skill_catalog(force_reload=True)
    print(f"Total skills indexed in catalog: {len(catalog)}")
    for s in catalog.list_skills():
        print(f"  - 📚 {s['name']} (Domain: {s['domain'] or 'General'})")
    print("=" * 60)

if __name__ == "__main__":
    sync_skills()
