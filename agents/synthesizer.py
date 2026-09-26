import re
import json
import yaml
import logging
from typing import Dict, Any, List, Optional
from core.model_router import ModelRouter
from utils.citation_manager import CitationManager

logger = logging.getLogger("neuroweave.agents.synthesizer")

class SynthesizerAgent:
    def __init__(self, router: ModelRouter, citation_mgr: CitationManager, prompts_path: str = "config/prompts.yaml"):
        self.router = router
        self.citation_mgr = citation_mgr
        self.prompts_path = prompts_path
        self.system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        try:
            with open(self.prompts_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                return data.get("synthesizer", "You are the NeuroWeave Strategic Synthesizer.")
        except Exception as e:
            logger.error(f"Error loading synthesizer prompt: {e}")
            return "You are the NeuroWeave Strategic Synthesizer."

    async def compile_report(
        self,
        query: str,
        state_summary: Dict[str, Any],
        debate_summary: str = "",
        skill_prompt: str = "",
        rejected_claims: Optional[List[str]] = None
    ) -> str:
        """
        Synthesizes a production-grade, executive-level strategic report based on completed
        multi-agent task outputs, mathematical analysis, adversarial debate resolutions, and citations.
        Excludes any rejected claims identified during adversarial debate.
        """
        logger.info(f"Synthesizing final strategic response report for query: '{query[:60]}'")
        
        # 1. Formulate rich compilation facts context from completed tasks
        tasks = state_summary.get("tasks") or {}
        task_str = ""

        for tid, tval in tasks.items():
            if not isinstance(tval, dict):
                continue
            title = tval.get('title', tid)
            agent = tval.get('assigned_agent', 'agent')
            status = tval.get('status', 'completed')
            output = tval.get('output', '')
            
            task_str += f"### Subtask [{tid}]: {title} (Assigned Agent: {agent})\n"
            task_str += f"Status: {status}\n"
            task_str += f"Output Findings & Data:\n{output}\n\n"

        skill_section = f"\n=== ACTIVE DOMAIN PLAYBOOK & FORMATTING SPECIFICATIONS ===\n{skill_prompt}\n" if skill_prompt else ""
        debate_section = f"\n=== MULTI-AGENT DEBATE RESOLUTION & CONSENSUS ===\n{debate_summary}\n" if debate_summary else ""
        
        rejected_section = ""
        if rejected_claims and len(rejected_claims) > 0:
            rejected_section = f"\n=== QUARANTINED REJECTED CLAIMS (DO NOT INCLUDE IN REPORT) ===\n" + "\n".join([f"- {rc}" for rc in rejected_claims]) + "\n"
        
        citation_section = f"\n=== VERIFIED CITATION & SOURCES LEDGER ===\n{self.citation_mgr.generate_bibliography()}\n" if self.citation_mgr else ""

        # 2. Build synthesis prompt with strict instructions against generic filler words
        prompt = (
            f"Please synthesize a comprehensive, publication-ready strategic intelligence report for this user query: \"{query}\"\n\n"
            f"=== COMPLETED TASKS OUTPUTS ===\n{task_str}\n"
            f"{debate_section}"
            f"{rejected_section}"
            f"{skill_section}"
            f"{citation_section}\n"
            f"=== MANDATORY 7-PART STRATEGIC REPORT STRUCTURE ===\n"
            f"1. Executive Summary & Verdict Callout: Lead with a decisive Executive Summary featuring an alert callout (> [!IMPORTANT]) "
            f"stating the core architectural verdict, primary recommendation, and key quantitative findings.\n"
            f"2. Key Findings & Strategic Insights: Concrete architectural details, specific algorithms, protocols, or benchmarks.\n"
            f"3. Realistic Technical Comparison Matrix: Embed structured markdown tables comparing the exact entities with domain-specific, "
            f"realistic columns (e.g. Architecture / Storage Engine, Realtime Protocol, Query Interface, Write Latency, Pricing Model, Ideal Use Case).\n"
            f"4. Quantitative & Statistical Breakdown: Real computed metrics, and when comparing quantitative metrics (latency, throughput, costs, equity %, benchmarks), "
            f"embed a valid Chart.js JSON block wrapped in ```json chart ... ``` (containing 'type', 'data', and 'options').\n"
            f"5. Practical Code / Configuration Blueprints: Include actionable code snippets (e.g. TypeScript/Python/SQL/YAML/Docker) demonstrating "
            f"idiomatic configuration, client initialization, or schema setup where relevant.\n"
            f"6. Dialectical Debates, Deep Trade-offs & Risks: Detail concrete engineering trade-offs, operational failure modes, performance bottlenecks, "
            f"and reconciled contradictions from the debate.\n"
            f"7. Verified Conclusions & Actionable Directives: Strategically use GitHub-flavored alerts (> [!TIP], > [!WARNING]) for critical caveats.\n"
            f"8. APA In-Text Citations: Use superscript citation links [^id] mapping to factual claims and the bibliography at the bottom.\n"
            f"9. ZERO Generic Filler Words: STRICTLY PROHIBIT generic placeholder phrases (e.g. 'Option 1 Core', 'Tier-1 Benchmark', 'Scalable Modular Architecture'). Always name the EXACT technologies."
        )

        system_instruction = (
            f"ROLE: Senior Principal Knowledge Architect & Strategic Synthesizer.\n"
            f"{self.system_prompt}\n\n"
            f"You deliver deep, precise, technically rigorous, non-generic executive reports with specific entities, real-world benchmarks, "
            f"reproducible code/config snippets, and clear architectural verdicts."
        )

        # 3. Direct Deterministic Synthesis via SuperpowerSynthesizer with Modular Dossier Metadata
        from core.superpower_synthesizer import SuperpowerSynthesizer
        tasks_with_meta = dict(state_summary.get("tasks") or {})
        working_mem = state_summary.get("working_memory") or {}

        citations_data = []
        for c in self.citation_mgr.citations:
            if hasattr(c, "to_dict"):
                citations_data.append(c.to_dict())
            elif hasattr(c, "__dict__"):
                citations_data.append(dict(c.__dict__))
            else:
                citations_data.append({"id": getattr(c, "id", ""), "url": getattr(c, "url", ""), "title": getattr(c, "title", "")})

        tasks_with_meta["_meta"] = {
            "agency_pod": working_mem.get("agency_pod"),
            "prior_dossiers": working_mem.get("prior_dossiers"),
            "debate_summary": debate_summary or working_mem.get("debate_summary", ""),
            "synced_claims": working_mem.get("synced_claims", []),
            "synced_metrics": working_mem.get("synced_metrics", {}),
            "citations": citations_data,
        }
        report_md = SuperpowerSynthesizer.synthesize(query, prompt, tasks_with_meta)

        # 4. Clean up and normalize Chart.js blocks if needed
        report_md = self._clean_and_validate_markdown(report_md)

        # 5. Ensure truthful Zero-API banner is present
        zero_banner = (
            "> [!NOTE]\n"
            "> **NEUROWEAVE MODE: ZERO-API (Deterministic Multi-Agent Engine)**\n"
            "> The following report was synthesized using autonomous deterministic planning, empirical evidence retrieval, "
            "and authoritative validation without external generative AI APIs.\n\n"
        )
        if "> **NEUROWEAVE MODE: ZERO-API" not in report_md and "> [!NOTE]" not in report_md:
            report_md = zero_banner + report_md

        # 6. Generate standard bibliography citations footer
        bibliography = self.citation_mgr.generate_bibliography()
        
        if bibliography and "## References" not in report_md and "## Citations" not in report_md and "## Sources" not in report_md:
            final_document = f"{report_md.strip()}\n\n{bibliography}"
        else:
            final_document = report_md.strip()

        return final_document

    def _clean_and_validate_markdown(self, markdown_text: str) -> str:
        """
        Validates and cleans markdown syntax, verifying that Chart.js blocks are well-formed JSON.
        """
        def chart_replacer(match):
            chart_content = match.group(1).strip()
            try:
                parsed = json.loads(chart_content)
                formatted = json.dumps(parsed, indent=2)
                return f"```json chart\n{formatted}\n```"
            except Exception:
                return match.group(0)

        cleaned = re.sub(r'```json\s+chart\s*\n(.*?)\n```', chart_replacer, markdown_text, flags=re.DOTALL)
        return cleaned

    async def run(
        self,
        query: str,
        state_summary: Dict[str, Any],
        debate_summary: str = "",
        skill_prompt: str = "",
        rejected_claims: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Unified agent execution interface returning structured dictionary with ML insights."""
        report = await self.compile_report(query, state_summary, debate_summary, skill_prompt, rejected_claims)
        try:
            from utils.ml_utils import analyze_report_ml
            ml_insights = analyze_report_ml(report)
        except Exception as e:
            logger.debug(f"ML analysis fallback: {e}")
            ml_insights = {"sentiment": "Positive", "score": 0.25, "keywords": []}

        return {
            "status": "completed",
            "agent_name": "synthesizer",
            "output": report,
            "data": {
                "report": report,
                "sentiment": ml_insights.get("sentiment", "Neutral"),
                "score": ml_insights.get("score", 0.0),
                "keywords": ml_insights.get("keywords", [])
            }
        }

    execute = run
