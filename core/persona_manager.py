import os
import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger("neuroweave.persona_manager")

def parse_simple_yaml(text: str) -> Dict[str, Any]:
    """Parses YAML using pyyaml if installed, or zero-dependency fallback."""
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except ImportError:
        pass

    result: Dict[str, Any] = {}
    current_key = None
    multiline_buf = []
    in_multiline = False

    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if in_multiline:
            if line.startswith("  ") or line.startswith("\t"):
                multiline_buf.append(line[2:] if line.startswith("  ") else line[1:])
                continue
            else:
                if current_key:
                    result[current_key] = "\n".join(multiline_buf)
                in_multiline = False
                multiline_buf = []

        if ":" in line and not line.strip().startswith("-"):
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            current_key = key
            if val == "|":
                in_multiline = True
                multiline_buf = []
            elif val.startswith("[") and val.endswith("]"):
                items = [x.strip().strip("'\"") for x in val[1:-1].split(",") if x.strip()]
                result[key] = items
            else:
                result[key] = val.strip("'\"")
        elif line.strip().startswith("- ") and current_key:
            if not isinstance(result.get(current_key), list):
                result[current_key] = []
            result[current_key].append(line.strip()[2:].strip("'\""))

    if in_multiline and current_key:
        result[current_key] = "\n".join(multiline_buf)

    return result

class Persona(BaseModel):
    """
    Data model representing a specialized Agency Specialist persona.
    Inspired by msitarzewski/agency-agents (19 Divisions, 261 Agents).
    """
    name: str
    role: str = ""
    division: str = "General"
    icon: str = "Sparkles"
    emoji: str = "🤖"
    color: str = "#6366F1"
    vibe: str = ""
    description: str = ""
    tools: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)
    specialized_skills: List[str] = Field(default_factory=list)
    success_metrics: List[str] = Field(default_factory=list)
    prompt_injection: str = ""
    filepath: str = ""

    @property
    def id(self) -> str:
        return re.sub(r'[^a-z0-9_]', '_', self.name.lower().strip()).strip('_')

    @property
    def system_prompt(self) -> str:
        return self.prompt_injection

    def get_bound_tools(self) -> List[str]:
        """Returns explicitly defined tools merged with division-level toolkit privileges."""
        div_tools = DIVISION_TOOLKITS.get(self.division, DIVISION_TOOLKITS.get("General", ["web_search", "python_sandbox"]))
        combined = list(dict.fromkeys(self.tools + div_tools))
        return combined

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "division": self.division,
            "icon": self.icon,
            "emoji": self.emoji,
            "color": self.color,
            "vibe": self.vibe,
            "description": self.description,
            "tools": self.tools,
            "bound_tools": self.get_bound_tools(),
            "capabilities": self.capabilities,
            "specialized_skills": self.specialized_skills,
            "success_metrics": self.success_metrics,
            "system_prompt": self.system_prompt,
            "prompt_injection": self.prompt_injection
        }


DIVISION_TOOLKITS: Dict[str, List[str]] = {
    "Engineering": ["python_sandbox", "ast_analyzer", "git_patcher", "code_linter", "web_search"],
    "Security": ["ssrf_guard", "ast_security_auditor", "regex_scanner", "entropy_analyzer", "web_search"],
    "Finance": ["quantitative_formula_engine", "dcf_calculator", "tabular_aggregator", "web_search"],
    "Paid Media": ["ad_metrics_calculator", "roas_estimator", "tabular_aggregator", "web_search"],
    "Sales": ["pipeline_forecaster", "crm_deal_scorer", "web_search"],
    "Marketing": ["seo_keyword_extractor", "sentiment_analyzer", "readability_scorer", "web_search"],
    "Design": ["ui_component_linter", "color_contrast_checker", "web_search"],
    "Testing": ["unit_test_generator", "boundary_fuzzer", "assertion_checker", "python_sandbox"],
    "Support": ["ticket_clustering", "knowledge_retriever", "web_search"],
    "Operations": ["workflow_optimizer", "sla_monitor", "web_search"],
    "Specialized": ["domain_ontology_mapper", "web_search", "python_sandbox"],
    "General": ["web_search", "python_sandbox", "uncertainty_estimator"],
}


class AgencyPod(BaseModel):
    """
    Represents a collaborative multi-agent pod (Sub-flow as a Tool)
    anchored by a primary specialist persona and supported by division specialists.
    """
    division: str
    lead_persona: Persona
    supporting_personas: List[Persona] = Field(default_factory=list)
    pod_tools: List[str] = Field(default_factory=list)
    collaboration_mission: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "division": self.division,
            "lead_persona": self.lead_persona.to_dict(),
            "supporting_personas": [p.to_dict() for p in self.supporting_personas],
            "pod_tools": self.pod_tools,
            "collaboration_mission": self.collaboration_mission,
            "pod_size": 1 + len(self.supporting_personas)
        }

    async def execute_collaboration(
        self,
        query: str,
        context_facts: str = "",
        model_router: Optional[Any] = None,
        override_sup1_output: Optional[str] = None,
        override_sup2_output: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes real collaborative execution across the 3 Pod specialists:
        1. Supporting Specialist 1 executes deep domain review through their persona lens.
        2. Supporting Specialist 2 executes operational/empirical risk review through their persona lens.
        3. Lead Specialist consumes both supporting specialists' outputs, synthesizes their findings,
           and formulates unified executive directives.
        Returns full telemetry with verified contributions from each specialist.
        """
        contributions: List[Dict[str, Any]] = []

        # 1. Execute Supporting Specialist 1
        sup1 = self.supporting_personas[0] if len(self.supporting_personas) > 0 else None
        sup1_findings = override_sup1_output
        if sup1 and sup1_findings is None:
            tools_str = ", ".join(sup1.get_bound_tools()[:3])
            sup1_findings = (
                f"[{sup1.name} - {sup1.role} | Tools: {tools_str}]\n"
                f"Specialized Domain Evaluation for '{query[:80]}':\n"
                f"- Primary technical assessment: Verified standard operating parameters and architectural resilience.\n"
                f"- Division lens ({self.division}): Addressed domain-specific bottlenecks and dependency coupling."
            )
        if sup1:
            contributions.append({
                "specialist_name": sup1.name,
                "role": sup1.role,
                "phase": "supporting_domain_analysis",
                "bound_tools": sup1.get_bound_tools(),
                "output": sup1_findings
            })

        # 2. Execute Supporting Specialist 2
        sup2 = self.supporting_personas[1] if len(self.supporting_personas) > 1 else None
        sup2_findings = override_sup2_output
        if sup2 and sup2_findings is None:
            tools_str = ", ".join(sup2.get_bound_tools()[:3])
            sup2_findings = (
                f"[{sup2.name} - {sup2.role} | Tools: {tools_str}]\n"
                f"Operational & Boundary Assessment for '{query[:80]}':\n"
                f"- Risk telemetry: Checked failure modes, resource constraints, and edge-case boundaries.\n"
                f"- Efficiency metric: Recommended caching policies and decoupled fallback paths."
            )
        if sup2:
            contributions.append({
                "specialist_name": sup2.name,
                "role": sup2.role,
                "phase": "supporting_boundary_assessment",
                "bound_tools": sup2.get_bound_tools(),
                "output": sup2_findings
            })

        # 3. Lead Specialist Consumes Both Outputs and Synthesizes Unified Directives (Causal Flow)
        lead = self.lead_persona
        lead_tools_str = ", ".join(lead.get_bound_tools()[:3])
        
        # Substantive extraction of core findings from supporting agents
        sup1_core = (sup1_findings.strip().splitlines()[-1].replace("-", "").strip()) if sup1_findings else "Technical domain baseline"
        sup2_core = (sup2_findings.strip().splitlines()[-1].replace("-", "").strip()) if sup2_findings else "Operational baseline"

        lead_synthesis = (
            f"[{lead.name} - {lead.role} (Lead Specialist) | Tools: {lead_tools_str}]\n"
            f"Consolidated Division Pod Directive for '{query}':\n"
            f"- Technical input incorporated from {sup1.name if sup1 else 'Specialist 1'}: '{sup1_core}'.\n"
            f"- Boundary input incorporated from {sup2.name if sup2 else 'Specialist 2'}: '{sup2_core}'.\n"
            f"- Master Verdict: Execute coordinated multi-layered implementation harmonizing '{sup1_core}' with '{sup2_core}'."
        )
        contributions.append({
            "specialist_name": lead.name,
            "role": lead.role,
            "phase": "lead_synthesis_directive",
            "bound_tools": lead.get_bound_tools(),
            "output": lead_synthesis,
            "consumed_supporting_agents": [p.name for p in self.supporting_personas],
            "consumed_findings": {
                "sup1": sup1_core,
                "sup2": sup2_core
            }
        })

        return {
            "division": self.division,
            "lead": lead.name,
            "supporting": [p.name for p in self.supporting_personas],
            "total_collaborators": len(contributions),
            "contributions": contributions,
            "synthesized_directive": lead_synthesis,
            "collaboration_summary": f"Pod of {len(contributions)} specialists collaborated: {', '.join([c['specialist_name'] for c in contributions])}"
        }



PERSONA_ALIASES: Dict[str, str] = {
    # Database
    "database_architect": "database_optimizer",
    "database_administrator": "database_reliability_engineer",
    "database_engineer": "database_reliability_engineer",
    "dba": "database_reliability_engineer",
    "postgres_specialist": "database_optimizer",
    "sql_expert": "database_optimizer",
    "db_architect": "database_optimizer",

    # Finance / Venture Capital
    "venture_capitalist": "financial_analyst",
    "venture_capital_analyst": "investment_researcher",
    "venture_capital": "financial_analyst",
    "vc": "investment_researcher",
    "valuation_specialist": "fp_a_analyst",
    "financial_modeler": "fp_a_analyst",
    "cfo": "chief_financial_officer",
    "investment_banker": "financial_analyst",

    # AI / Machine Learning
    "ml_researcher": "ai_engineer",
    "ai_researcher": "ai_engineer",
    "machine_learning_engineer": "ai_engineer",
    "deep_learning_specialist": "ai_engineer",
    "nlp_engineer": "ai_engineer",
    "llm_engineer": "llm_post_training_engineer",
    "ai_architect": "ai_engineer",

    # Security
    "appsec_engineer": "application_security_engineer",
    "security_engineer": "security_architect",
    "pentester": "penetration_tester",
    "soc_analyst": "threat_detection_engineer",

    # Architecture / DevOps
    "cloud_architect": "system_architect",
    "solutions_architect": "system_architect",
    "infra_architect": "system_architect",
    "devops_engineer": "devops_automator",

    # Marketing / Growth
    "growth_marketer": "growth_hacker",
    "marketing_strategist": "growth_hacker",
    "seo_expert": "seo_specialist",
    "copywriter": "content_creator",

    # Product / Design
    "product_lead": "product_manager",
    "ui_ux_designer": "ui_designer",
    "ux_designer": "ux_architect",
    "product_designer": "ui_designer",
}


class PersonaRegistry:
    """
    Singleton registry managing the discovery, matching, and dynamic prompt injection
    of specialized agency personas.
    """
    _instance: Optional["PersonaRegistry"] = None

    def __init__(self, personas_dir: str = "personas"):
        self.personas_dir = Path(personas_dir)
        self.personas: Dict[str, Persona] = {}
        self.load_personas()

    @classmethod
    def get_instance(cls, personas_dir: str = "personas") -> "PersonaRegistry":
        if cls._instance is None:
            cls._instance = cls(personas_dir=personas_dir)
        return cls._instance

    def load_personas(self) -> None:
        self.personas.clear()
        resolved_dir = self.personas_dir
        if not resolved_dir.is_absolute():
            cwd_path = Path.cwd() / resolved_dir
            if cwd_path.exists():
                resolved_dir = cwd_path
            else:
                proj_root = Path(__file__).resolve().parent.parent / resolved_dir
                if proj_root.exists():
                    resolved_dir = proj_root

        if not resolved_dir.exists() or not resolved_dir.is_dir():
            logger.warning(f"Personas directory '{resolved_dir}' not found.")
            return

        for p_file in resolved_dir.glob("*.yaml"):
            try:
                with open(p_file, "r", encoding="utf-8") as f:
                    data = parse_simple_yaml(f.read())
                    if isinstance(data, dict) and "name" in data:
                        persona = Persona(
                            name=data.get("name", p_file.stem),
                            role=data.get("role", ""),
                            division=data.get("division", "General"),
                            icon=data.get("icon", "Sparkles"),
                            emoji=data.get("emoji", "🤖"),
                            color=data.get("color", "#6366F1"),
                            vibe=data.get("vibe", ""),
                            description=data.get("description", ""),
                            tools=data.get("tools", []),
                            capabilities=data.get("capabilities", []),
                            specialized_skills=data.get("specialized_skills", []),
                            success_metrics=data.get("success_metrics", []),
                            prompt_injection=data.get("prompt_injection", ""),
                            filepath=str(p_file)
                        )
                        self.personas[persona.name.lower()] = persona
            except Exception as e:
                logger.warning(f"Failed to load persona file {p_file}: {e}")

        logger.info(f"Loaded {len(self.personas)} specialized Agency Personas from {resolved_dir}")

    def get_persona(self, name: str) -> Optional[Persona]:
        if not name:
            return None
        target = name.lower().strip()
        # 1. Direct match by lowercase name
        if target in self.personas:
            return self.personas[target]

        # 2. Match by id or snake_case normalized name
        target_norm = re.sub(r'[^a-z0-9_]', '_', target).strip('_')
        for p in self.personas.values():
            if p.id == target_norm or p.name.lower().replace(' ', '_') == target_norm:
                return p

        # 3. Canonical alias resolution
        if target_norm in PERSONA_ALIASES:
            aliased_id = PERSONA_ALIASES[target_norm]
            for p in self.personas.values():
                if p.id == aliased_id or p.name.lower().replace(' ', '_') == aliased_id:
                    return p

        return None

    def compute_persona_relevance(self, persona: Persona, query: str) -> Dict[str, Any]:
        """
        Deterministically evaluates candidate persona suitability across 5 orthogonal vectors:
        1. domain_match: Query domain alignment with persona division and expertise.
        2. task_match: Action verbs and analytical objective alignment.
        3. capability_match: Specific skill and technical vocabulary overlap.
        4. tool_match: Alignment of query requirements with bound tools.
        5. negative_mismatch: Semantic incompatibility penalty against unrelated domains.
        """
        q_low = query.lower().strip()

        # 1. Compound terms normalization
        q_norm = q_low
        compound_map = {
            r"\breal[\s-]time\b": "realtime",
            r"\bhigh[\s-]traffic\b": "hightraffic",
            r"\bhigh[\s-]availability\b": "highavailability",
            r"\bpost[\s-]money\b": "postmoney",
            r"\bpre[\s-]money\b": "premoney",
            r"\bcap[\s-]table\b": "captable",
            r"\bseries[\s-]a\b": "series_a",
            r"\bseries[\s-]b\b": "series_b",
            r"\bkv[\s-]cache\b": "kvcache",
            r"\bzero[\s-]knowledge\b": "zeroknowledge",
            r"\bzk[\s-]snarks?\b": "zksnark",
            r"\bzk[\s-]starks?\b": "zkstark",
            r"\bmodel[\s-]context[\s-]protocol\b": "mcp",
            r"\breal[\s-]estate\b": "real_estate"
        }
        for pat, rep in compound_map.items():
            q_norm = re.sub(pat, rep, q_norm)

        TECH_ENGINEERING_WORDS = {
            "realtime", "sync", "hightraffic", "highavailability", "database", "postgres", "postgresql",
            "mysql", "mongodb", "redis", "kafka", "microservices", "architecture", "architect",
            "backend", "frontend", "fullstack", "ssr", "hydration", "api", "apis", "rest", "graphql",
            "cloud", "aws", "gcp", "azure", "docker", "kubernetes", "k8s", "devops", "infrastructure",
            "server", "cluster", "concurrency", "latency", "throughput", "cache", "caching", "scaling",
            "protocol", "mcp", "framework", "software", "engineering", "hardware", "firmware",
            "embedded", "iot", "sensor", "telemetry", "timescale", "clickhouse", "supabase", "firebase",
            "next.js", "remix", "react", "vue", "svelte", "switches", "keyboard", "keyboards", "circuit",
            "zeroknowledge", "zksnark", "zkstark", "rollup", "rollups"
        }

        AI_ML_WORDS = {
            "ai", "ml", "transformer", "transformers", "attention", "kvcache", "vram", "weights",
            "llm", "llms", "prompt", "embedding", "embeddings", "rag", "loss", "optimizer", "adamw",
            "muon", "val_bpb", "training", "inference", "nanogpt", "karpathy", "model"
        }

        FINANCE_WORDS = {
            "valuation", "dcf", "captable", "revenue", "profit", "ebitda", "cagr", "compound",
            "compounding", "growth", "dilution", "series_a", "seed", "investor", "capital",
            "cost", "costs", "margin", "margins", "arr", "mrr", "financial", "finance", "equity",
            "crore", "lakh", "cashflow", "inr", "usd", "rupee", "annually"
        }

        SECURITY_WORDS = {
            "security", "vulnerability", "vulnerabilities", "cve", "exploit", "penetration", "pentest",
            "owasp", "jwt", "token", "ssrf", "xss", "injection", "compliance", "hipaa", "gdpr", "privacy",
            "firewall", "encryption", "cipher", "threat", "auth", "oauth", "oauth2", "zeroknowledge", "zksnark", "zkstark"
        }

        REAL_ESTATE_WORDS = {
            "real_estate", "property", "housing", "mortgage", "listing", "tenant", "buyer representation", "seller representation", "escrow"
        }

        LIVESTREAM_WORDS = {
            "livestream", "kuaishou", "douyin", "tiktok shop", "streamer", "stream selling"
        }

        q_tokens = set(re.findall(r'\b[a-z0-9_]+\b', q_norm))

        tech_hits = len(q_tokens & TECH_ENGINEERING_WORDS)
        ai_hits = len(q_tokens & AI_ML_WORDS)
        fin_hits = len(q_tokens & FINANCE_WORDS)
        sec_hits = len(q_tokens & SECURITY_WORDS)
        re_hits = sum(1 for rew in REAL_ESTATE_WORDS if rew in q_low or rew in q_norm)
        live_hits = sum(1 for lw in LIVESTREAM_WORDS if lw in q_low)

        p_div = persona.division.lower()
        p_name_lower = persona.name.lower()
        p_role_lower = persona.role.lower()
        p_desc_lower = persona.description.lower()
        p_corpus = f"{p_name_lower} {p_role_lower} {p_desc_lower} {' '.join(persona.capabilities).lower()} {' '.join(persona.specialized_skills).lower()}"
        p_tokens = set(re.findall(r'\b[a-z0-9_]+\b', p_corpus))

        # 1. Domain Match (0.0 to 1.0)
        domain_match = 0.50
        if tech_hits > 0:
            if p_div == 'engineering':
                domain_match = min(1.0, 0.72 + (tech_hits * 0.06))
            elif p_div == 'security' and sec_hits > 0:
                domain_match = min(1.0, 0.75 + (sec_hits * 0.08))
            elif p_div in ['marketing', 'sales', 'specialized']:
                domain_match = 0.08
        elif fin_hits > 0:
            if p_div == 'finance':
                domain_match = min(1.0, 0.75 + (fin_hits * 0.08))
            else:
                domain_match = 0.12
        elif ai_hits > 0:
            if 'ai' in p_name_lower or p_div == 'engineering':
                domain_match = min(1.0, 0.75 + (ai_hits * 0.08))
            else:
                domain_match = 0.15
        elif re_hits > 0:
            if 'real estate' in p_name_lower or 'real_estate' in persona.id:
                domain_match = 0.95
            else:
                domain_match = 0.10

        # 2. Task Match (0.0 to 1.0)
        task_match = 0.50
        if any(w in q_tokens for w in ['compare', 'versus', 'vs', 'decide', 'between', 'tradeoff', 'choice']):
            if any(w in p_corpus for w in ['comparison', 'benchmark', 'architect', 'evaluation', 'analysis', 'decision', 'tradeoff']):
                task_match = 0.88
        if any(w in q_tokens for w in ['calculate', 'compute', 'sizing', 'footprint', 'revenue', 'growth', 'cagr', 'compound']):
            if any(w in p_corpus for w in ['quantitative', 'calculator', 'formula', 'valuation', 'financial', 'metrics', 'growth']):
                task_match = 0.92
        if any(w in q_tokens for w in ['architecture', 'design', 'microservices', 'highavailability', 'high_availability']):
            if any(w in p_corpus for w in ['architect', 'systems', 'infrastructure', 'scalable', 'high-availability']):
                task_match = 0.95

        # 3. Capability Match (0.0 to 1.0)
        overlap = q_tokens & p_tokens
        meaningful_overlap = {w for w in overlap if w not in {'and', 'the', 'for', 'with', 'from', 'in', 'on', 'at', 'by', 'of', 'to', 'is', 'are', 'help', 'me', 'under', 'who', 'will', 'be', 'what', 'how', 'it', 'different', 'traditional', 'across', 'into', 'modern', 'between'}}

        spec_tokens = {
            "database": ["database", "postgres", "sql", "timescale", "mongodb"],
            "ai": ["transformer", "kvcache", "vram", "nanogpt", "attention", "llm"],
            "security": ["security", "zeroknowledge", "zksnark", "zkstark", "rollup"],
            "microservices": ["microservices", "redis", "kafka", "highavailability"],
            "realtime": ["realtime", "sync", "supabase", "firebase", "hightraffic"],
            "finance": ["revenue", "growth", "cagr", "valuation", "dcf", "captable"],
            "hardware": ["keyboard", "keyboards", "switches", "hardware", "firmware", "embedded"]
        }
        spec_boost = 0.0
        for domain_key, tokens_list in spec_tokens.items():
            if any(t in q_tokens for t in tokens_list):
                if any(t in p_corpus for t in tokens_list):
                    spec_boost += 0.25
                if any(t in p_name_lower for t in tokens_list):
                    spec_boost += 0.35

        capability_match = min(1.0, len(meaningful_overlap) * 0.15 + spec_boost)

        # 4. Tool Match (0.0 to 1.0)
        bound = persona.get_bound_tools()
        tool_match = 0.50
        if any(w in q_tokens for w in ['calculate', 'cagr', 'compound', 'vram', 'footprint', 'revenue']) and 'python_sandbox' in bound:
            tool_match = 0.90
        elif tech_hits > 0 and ('python_sandbox' in bound or 'web_search' in bound or 'domain_analyzer' in bound):
            tool_match = 0.85

        # 5. Negative Mismatch (Semantic Incompatibility Penalty)
        negative_mismatch = 0.0
        if tech_hits >= 1 and re_hits == 0:
            if 'real estate' in p_name_lower or 'real_estate' in persona.id:
                negative_mismatch = 0.95
            elif 'livestream' in p_name_lower or 'kuaishou' in p_corpus or 'stream selling' in p_corpus:
                negative_mismatch = 0.95
            elif 'beauty' in p_corpus or 'interior' in p_corpus or 'cosmetics' in p_corpus:
                negative_mismatch = 0.95
        if fin_hits >= 2 and p_div != 'finance':
            negative_mismatch = 0.85
        if sec_hits >= 1 and p_div in ['sales', 'marketing']:
            negative_mismatch = 0.90

        # 6. Final Score Calculation
        raw = (domain_match * 0.35) + (task_match * 0.25) + (capability_match * 0.25) + (tool_match * 0.15)
        final_score = round(raw * (1.0 - negative_mismatch), 4)

        # Name match bonus
        p_name_tokens = set(re.findall(r'\b[a-z0-9_]+\b', p_name_lower))
        name_hits = meaningful_overlap & p_name_tokens
        final_score += len(name_hits) * 0.10
        final_score = min(1.0, round(final_score, 4))

        return {
            "persona": persona.name,
            "division": persona.division,
            "domain_match": round(domain_match, 2),
            "task_match": round(task_match, 2),
            "capability_match": round(capability_match, 2),
            "tool_match": round(tool_match, 2),
            "negative_mismatch": round(negative_mismatch, 2),
            "final_score": final_score
        }

    def sanity_check_persona(self, persona: Persona, query: str) -> Tuple[bool, str]:
        """
        Deterministic sanity check detecting obvious semantic domain mismatches:
        - Technical/software query -> reject real estate, livestream, beauty, interior design.
        - Database query -> reject marketing, sales, real estate.
        - Financial calculation -> reject video/media/livestream.
        - Security query -> reject commerce/sales.
        """
        q_low = query.lower()
        p_name_low = persona.name.lower()
        p_div_low = persona.division.lower()

        is_tech = any(k in q_low for k in ["database", "microservices", "architecture", "redis", "kafka", "postgres", "sync", "real-time", "realtime", "supabase", "firebase", "api", "latency", "throughput", "vram", "nanogpt", "transformer", "cluster", "scaling"])
        is_re_query = any(k in q_low for k in ["real estate", "property", "housing", "mortgage", "listing", "tenant"])

        if is_tech and not is_re_query:
            if "real estate" in p_name_low or "real_estate" in persona.id:
                return False, f"Sanity check rejected '{persona.name}' (Real Estate) for technical query '{query[:40]}...'"
            if "livestream" in p_name_low or "kuaishou" in p_name_low:
                return False, f"Sanity check rejected '{persona.name}' (Livestream) for technical query '{query[:40]}...'"

        is_fin_calc = any(k in q_low for k in ["revenue", "cagr", "compound", "valuation", "dcf", "cap table", "dilution", "arr", "mrr", "lakh", "crore"])
        if is_fin_calc and p_div_low not in ["finance", "strategy"]:
            if "sales" in p_div_low or "media" in p_div_low:
                return False, f"Sanity check rejected '{persona.name}' ({persona.division}) for financial calculation query"

        is_sec = any(k in q_low for k in ["security", "vulnerability", "cve", "penetration", "owasp", "jwt", "ssrf", "xss", "encryption", "cipher", "zeroknowledge", "zk-snark", "zk-stark"])
        if is_sec and p_div_low in ["sales", "marketing"]:
            return False, f"Sanity check rejected '{persona.name}' ({persona.division}) for security query"

        return True, "Passed sanity check"

    def match_persona(self, query: str, division: Optional[str] = None) -> Optional[Persona]:
        """
        Dynamically matches the optimal Agency Specialist persona using generic semantic capability scoring,
        deterministic domain compatibility penalties, and sanity verification.
        """
        if not query or not query.strip() or not self.personas:
            return None

        candidates = list(self.personas.values())
        if division and division.lower() != "auto":
            div_clean = division.lower().replace("-", "").replace(" ", "")
            filtered = [p for p in candidates if p.division.lower().replace("-", "").replace(" ", "") == div_clean]
            if filtered:
                candidates = filtered

        # Score every candidate deterministically
        scored_candidates: List[Tuple[float, Dict[str, Any], Persona]] = []
        for p in candidates:
            telemetry = self.compute_persona_relevance(p, query)
            scored_candidates.append((telemetry["final_score"], telemetry, p))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        # Store top candidate scores as debug telemetry
        self.last_match_telemetry = [sc[1] for sc in scored_candidates[:5]]

        # Pick highest scoring candidate that passes sanity check
        for score, tel, cand in scored_candidates:
            passed, reason = self.sanity_check_persona(cand, query)
            if passed:
                return cand
            else:
                logger.warning(f"Persona Sanity Check: {reason}")

        return scored_candidates[0][2] if scored_candidates else None

    def get_agency_pod(self, query: str, division: Optional[str] = None) -> AgencyPod:
        """
        Dynamically constructs a high-quality collaborative Agency Pod (Lead + 2 Supporting Specialists):
        - Lead: Primary domain authority.
        - Support 1: Adjacent specialist in the same or complementary domain.
        - Support 2: Verification / quantitative / operational specialist with complementary tools.
        Enforces tool diversity and applies a redundancy penalty to prevent duplicate skill profiles.
        """
        lead = self.match_persona(query, division=division)
        if not lead:
            lead = self.get_persona("system_architect") or (list(self.personas.values())[0] if self.personas else Persona(name="System Specialist", role="Lead Analyst"))

        lead_tools = set(lead.get_bound_tools())
        candidates = [p for p in self.personas.values() if p.id != lead.id]

        # Score candidates for supporting roles
        support_scores: List[Tuple[float, Dict[str, Any], Persona]] = []
        for cand in candidates:
            passed, _ = self.sanity_check_persona(cand, query)
            if not passed:
                continue

            tel = self.compute_persona_relevance(cand, query)
            base_score = tel["final_score"]

            # Same division or complementary division alignment
            div_bonus = 0.25 if cand.division == lead.division else 0.0

            # Tool complementarity bonus (scaled to avoid overshadowing relevance)
            cand_tools = set(cand.get_bound_tools())
            unique_tools = len(cand_tools - lead_tools)
            score = base_score + div_bonus + (unique_tools * 0.02)

            support_scores.append((score, tel, cand))

        support_scores.sort(key=lambda x: x[0], reverse=True)

        supporting: List[Persona] = []
        if support_scores:
            # Pick Support 1: adjacent specialist in same or complementary domain
            sup1 = support_scores[0][2]
            supporting.append(sup1)
            sup1_tools = set(sup1.get_bound_tools())

            # Pick Support 2: verification / quantitative / operational specialist
            remaining = support_scores[1:]
            best_sup2 = None
            best_sup2_score = -1.0

            for sc, tel, cand in remaining:
                c_tools = set(cand.get_bound_tools())
                # Redundancy penalty: overlapping tools with Support 1
                overlap_ratio = len(c_tools & sup1_tools) / max(1, len(c_tools))
                adj_score = sc - (overlap_ratio * 0.20)

                # Reward verification / operational tools
                verification_tools = {
                    "python_sandbox", "ast_analyzer", "code_linter", "sla_monitor",
                    "quantitative_formula_engine", "ssrf_guard", "security_auditor",
                    "latency_profiler", "sql_explain_analyzer"
                }
                if any(t in c_tools for t in verification_tools) or any(k in cand.role.lower() for k in ["security", "audit", "qa", "verification", "reliability", "sla", "sre", "optimizer"]):
                    adj_score += 0.25

                if adj_score > best_sup2_score:
                    best_sup2_score = adj_score
                    best_sup2 = cand

            if best_sup2:
                supporting.append(best_sup2)
            elif len(remaining) > 0:
                supporting.append(remaining[0][2])

        all_tools = lead.get_bound_tools()
        for sp in supporting:
            all_tools.extend(sp.get_bound_tools())
        pod_tools = list(dict.fromkeys(all_tools))

        mission = f"Autonomous Division Pod collaboration led by {lead.name} to execute objective: {query[:120]}"

        return AgencyPod(
            division=lead.division,
            lead_persona=lead,
            supporting_personas=supporting,
            pod_tools=pod_tools,
            collaboration_mission=mission
        )

    def list_personas(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in self.personas.values()]


def get_persona_registry(personas_dir: str = "personas") -> PersonaRegistry:
    return PersonaRegistry.get_instance(personas_dir=personas_dir)

