import os
import re
import json
import yaml
from pathlib import Path
from typing import Dict, Any, List

def sync_all_agency_agents():
    repo_dir = Path("external_agency_agents")
    dest_dir = Path("personas")
    dest_dir.mkdir(exist_ok=True)

    if not repo_dir.exists():
        print(f"Error: {repo_dir} directory not found!")
        return

    # Load canonical divisions metadata from divisions.json
    divisions_meta: Dict[str, Any] = {}
    div_json_path = repo_dir / "divisions.json"
    if div_json_path.exists():
        try:
            with open(div_json_path, "r", encoding="utf-8") as f:
                div_data = json.load(f)
                divisions_meta = div_data.get("divisions", {})
        except Exception as e:
            print(f"Warning reading divisions.json: {e}")

    excluded_dirs = {".git", ".github", "scripts", "examples", "integrations"}
    total_synced = 0
    division_counts: Dict[str, int] = {}

    for div_folder in repo_dir.iterdir():
        if not div_folder.is_dir() or div_folder.name in excluded_dirs or div_folder.name.startswith("."):
            continue

        div_key = div_folder.name
        div_info = divisions_meta.get(div_key, {})
        canonical_label = div_info.get("label", div_key.replace("-", " ").title())
        div_color = div_info.get("color", "#6366F1")
        div_icon = div_info.get("icon", "Sparkles")

        division_counts[canonical_label] = 0

        for md_file in div_folder.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                
                # 1. Parse YAML Frontmatter
                metadata: Dict[str, Any] = {}
                body = content
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        try:
                            metadata = yaml.safe_load(parts[1]) or {}
                        except Exception as e:
                            print(f"Frontmatter parse error in {md_file.name}: {e}")
                        body = parts[2].strip()

                agent_name = metadata.get("name") or md_file.stem.replace(f"{div_key}-", "").replace("-", " ").title()
                description = metadata.get("description", "").strip()
                emoji = metadata.get("emoji", "🤖")
                color = metadata.get("color", div_color)
                vibe = metadata.get("vibe", "").strip()
                raw_tools = metadata.get("tools", "")

                tools_list = []
                if isinstance(raw_tools, list):
                    tools_list = raw_tools
                elif isinstance(raw_tools, str) and raw_tools:
                    tools_list = [t.strip() for t in raw_tools.split(",") if t.strip()]

                # 2. Extract Capabilities
                capabilities: List[str] = []
                cap_patterns = [
                    r'## (?:🧠 )?Core Capabilities\s*\n(.*?)(?=\n## |\Z)',
                    r'## (?:🎯 )?Your Core Mission\s*\n(.*?)(?=\n## |\Z)',
                    r'## (?:⚡ )?Key Responsibilities\s*\n(.*?)(?=\n## |\Z)'
                ]
                for pat in cap_patterns:
                    m = re.search(pat, body, re.DOTALL)
                    if m:
                        for line in m.group(1).splitlines():
                            line = line.strip()
                            if line.startswith("- ") or line.startswith("* ") or line.startswith("### "):
                                clean_item = re.sub(r'^(?:[-*]|###)\s*(?:\*\*)?', '', line).split('**')[0].strip(' :')
                                if clean_item and len(clean_item) > 3 and clean_item not in capabilities:
                                    capabilities.append(clean_item)
                        if capabilities:
                            break

                # 3. Extract Specialized Skills / Rules
                specialized_skills: List[str] = []
                skills_match = re.search(r'## (?:🚨 )?(?:Specialized Skills|Critical Rules|Rules You Must Follow)\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL)
                if skills_match:
                    for line in skills_match.group(1).splitlines():
                        line = line.strip()
                        if line.startswith("- ") or line.startswith("* ") or line.startswith("### "):
                            clean_item = re.sub(r'^(?:[-*]|###)\s*(?:\*\*)?', '', line).split('**')[0].strip(' :')
                            if clean_item and len(clean_item) > 3 and clean_item not in specialized_skills:
                                specialized_skills.append(clean_item)

                # 4. Extract Success Metrics / Decision Framework
                success_metrics: List[str] = []
                metrics_match = re.search(r'## (?:📊 )?(?:Success Metrics|Decision Framework|Key Deliverables)\s*\n(.*?)(?=\n## |\Z)', body, re.DOTALL)
                if metrics_match:
                    for line in metrics_match.group(1).splitlines():
                        line = line.strip()
                        if line.startswith("- ") or line.startswith("* "):
                            clean_item = re.sub(r'^[-*]\s*(?:\*\*)?', '', line).split('**')[0].strip(' :')
                            if clean_item and len(clean_item) > 3 and clean_item not in success_metrics:
                                success_metrics.append(clean_item)

                # 5. Construct Rich Native Prompt Injection
                caps_formatted = "\n".join([f"- {c}" for c in (capabilities[:6] if capabilities else ["Expert domain analysis and execution"])])
                skills_formatted = "\n".join([f"- {s}" for s in (specialized_skills[:5] if specialized_skills else ["Industry-standard decision frameworks"])])
                metrics_formatted = "\n".join([f"- {m}" for m in (success_metrics[:4] if success_metrics else ["High-confidence empirical verification"])])

                prompt_injection = f"""=== SPECIALIST AGENCY AGENT: {agent_name.upper()} ({canonical_label.upper()}) ===
Role: {metadata.get('role', f'{canonical_label} Specialist')}
Vibe: {vibe if vibe else 'Rigorous, data-driven domain expert.'}
Description: {description}

Core Directives & Missions:
{caps_formatted}

Specialized Decision Rules & Standards:
{skills_formatted}

Success Metrics & Verification Rubric:
{metrics_formatted}

Operational Execution Guidelines:
1. Conduct all research and calculations strictly through the professional lens of a {agent_name}.
2. Adhere strictly to the domain success metrics and quantitative thresholds listed above.
3. Validate all trade-offs, architecture decisions, and financial/marketing assumptions with verified citations."""

                persona_payload = {
                    "name": agent_name,
                    "role": metadata.get("role", f"{canonical_label} Specialist"),
                    "division": canonical_label,
                    "icon": div_icon,
                    "emoji": emoji,
                    "color": color,
                    "vibe": vibe,
                    "description": description,
                    "tools": tools_list if tools_list else ["WebSearch", "PythonExecution", "DomainReasoning"],
                    "capabilities": capabilities[:10] if capabilities else ["Strategic Analysis", "Domain Execution"],
                    "specialized_skills": specialized_skills[:8] if specialized_skills else [],
                    "success_metrics": success_metrics[:6] if success_metrics else [],
                    "prompt_injection": prompt_injection.strip()
                }

                slug = re.sub(r'[^a-z0-9_]', '_', agent_name.lower().strip())
                slug = re.sub(r'_+', '_', slug).strip('_')
                out_path = dest_dir / f"{slug}.yaml"

                with open(out_path, "w", encoding="utf-8") as f:
                    yaml.dump(persona_payload, f, sort_keys=False, allow_unicode=True)

                total_synced += 1
                division_counts[canonical_label] += 1
            except Exception as e:
                print(f"Error syncing {md_file}: {e}")

    print("=" * 80)
    print(f"🚀 NATIVE AGENCY AGENTS SYNC COMPLETE: {total_synced} Specialized Agents Synced")
    print("=" * 80)
    for div, count in sorted(division_counts.items()):
        print(f"  • {div:22}: {count:2} agents")
    print("=" * 80)

if __name__ == "__main__":
    sync_all_agency_agents()
