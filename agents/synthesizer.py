import yaml
import logging
from typing import Dict, Any, List
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
            with open(self.prompts_path, 'r') as f:
                data = yaml.safe_load(f) or {}
                return data.get("synthesizer", "You are the NeuroWeave Synthesizer.")
        except Exception as e:
            logger.error(f"Error loading synthesizer prompt: {e}")
            return "You are the NeuroWeave Synthesizer."

    async def compile_report(self, query: str, state_summary: Dict[str, Any], debate_summary: str = "") -> str:
        logger.info("Synthesizing final strategic response report.")
        
        # Formulate compilation facts context
        tasks = state_summary.get("tasks") or {}
        task_str = ""
        for tid, tval in tasks.items():
            if not isinstance(tval, dict):
                continue
            task_str += f"### Subtask: {tval.get('title')} (Agent: {tval.get('assigned_agent')})\n"
            task_str += f"Status: {tval.get('status')}\n"
            task_str += f"Output findings: {tval.get('output')}\n\n"

        prompt = (
            f"Please synthesize the final, production-grade strategic report for this query: \"{query}\"\n\n"
            f"=== COMPLETED TASKS OUTPUTS ===\n{task_str}\n\n"
            f"=== MULTI-AGENT DEBATE RESOLUTION ===\n{debate_summary}\n\n"
            f"=== CITATIONS GATHERED ===\n"
            f"Please ensure all major factual statements trace back to superscript citations linked to the index values. "
            f"Format as a publication-ready strategic document.\n"
            f"Incorporate tables for competitive metrics, alert boxes for market risks, and distinct sections."
        )
        
        # Synthesize final document
        response = await self.router.call_llm(prompt, self.system_prompt, "reasoning_task", complexity=8)
        if not response or not isinstance(response, dict):
            report_md = "Error compiling strategic synthesized report: No response from language model router."
        else:
            report_md = response.get("content", "Error compiling strategic synthesized report.")

        # Generate standard bibliography citations footer
        bibliography = self.citation_mgr.generate_bibliography()
        
        final_document = (
            f"{report_md}\n\n"
            f"{bibliography}"
        )
        
        return final_document
