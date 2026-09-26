import re
import yaml
import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from core.model_router import ModelRouter
from core.structured_output import StructuredOutputParser
from utils.citation_manager import CitationManager
from tools.web_search import web_search

logger = logging.getLogger("neuroweave.agents.researcher")

class ResearchOutput(BaseModel):
    findings: str = Field(description="Synthesized objective research facts gathered from sources")
    suggested_queries: List[str] = Field(description="Recommended follow-up search terms")
    citations_used: List[Dict[str, str]] = Field(description="List of sources used, each containing 'url', 'title', 'snippet'")

class ResearcherAgent:
    def __init__(self, router: ModelRouter, citation_mgr: CitationManager, prompts_path: str = "config/prompts.yaml"):
        self.router = router
        self.citation_mgr = citation_mgr
        self.prompts_path = prompts_path
        self.system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        try:
            with open(self.prompts_path, 'r') as f:
                data = yaml.safe_load(f) or {}
                return data.get("researcher", "You are the NeuroWeave Researcher.")
        except Exception as e:
            logger.error(f"Error loading researcher prompt: {e}")
            return "You are the NeuroWeave Researcher."

    async def execute_task(self, task_description: str, memory_context: str = "") -> ResearchOutput:
        logger.info(f"Researcher executing task: '{task_description}'")
        
        # 1. Autonomously choose query search terms
        prompt_query = (
            f"Given this task: \"{task_description}\", determine the optimal web search keyword string. "
            f"Output ONLY the plain search term."
        )
        query_response = await self.router.call_llm(prompt_query, "You choose search queries.", "simple_task", complexity=3)
        search_query = query_response.get("content", task_description).strip().replace('"', '')

        # 2. Invoke the registered Web Search tool
        search_payload = await web_search(search_query)
        sources_list = search_payload.get("results", [])

        # 3. Register sources in the central citation manager ledger
        citations_refs = []
        for src in sources_list:
            cit_id = self.citation_mgr.add_source(
                url=src["url"],
                snippet=src["snippet"],
                title=src["title"],
                credibility=src.get("credibility", 0.85)
            )
            citations_refs.append(f"[^{cit_id}] (Source: {src['url']})")

        # 4. Generate structured research findings
        prompt_findings = (
            f"Synthesize the gathered facts for the task: \"{task_description}\"\n"
            f"Web search results collected:\n{sources_list}\n"
            f"RAG References:\n{memory_context}\n\n"
            f"Cite your sources using superscript notations [^id] corresponding to the index values: {citations_refs}."
        )
        
        model_call = lambda p, s: self.router.call_llm(p, s, task_type="reasoning", complexity=6)
        
        validated_result, _ = await StructuredOutputParser.parse_with_correction(
            llm_call_func=model_call,
            prompt=prompt_findings,
            system_instruction=self.system_prompt,
            schema=ResearchOutput
        )
        
        # 5. Extract and validate citation IDs referenced in findings, aligning them with the ledger
        findings_text = validated_result.findings
        cited_ids_in_text = re.findall(r'\[\^(\d+)\]', findings_text)
        
        # Keep track of which citation IDs are actually valid in the ledger
        valid_cited_ids = []
        for cid_str in cited_ids_in_text:
            cid = int(cid_str)
            citation = self.citation_mgr.get_citation(cid)
            if citation:
                if cid not in valid_cited_ids:
                    valid_cited_ids.append(cid)
            else:
                # LLM cited an ID that is not in the ledger. Let's see if we can resolve it using URL mapping
                resolved = False
                for llm_cit in validated_result.citations_used:
                    url = llm_cit.get("url")
                    if url and url in self.citation_mgr._url_map:
                        real_cid = self.citation_mgr._url_map[url].id
                        # Correct the hallucinated ID in the text to the correct ledger ID
                        findings_text = findings_text.replace(f"[^{cid}]", f"[^{real_cid}]")
                        if real_cid not in valid_cited_ids:
                            valid_cited_ids.append(real_cid)
                        resolved = True
                        logger.info(f"Re-mapped hallucinated citation ID [^{cid}] to correct ledger ID [^{real_cid}] using URL match.")
                        break
                
                if not resolved:
                    # Remove the invalid citation tag
                    findings_text = findings_text.replace(f"[^{cid}]", "")
                    logger.warning(f"Removed invalid/unresolvable citation tag [^{cid}] from research findings.")
        
        validated_result.findings = findings_text
        
        # Re-build citations_used from actual ledger entries to ensure absolute mapping fidelity
        aligned_citations = []
        for cid in sorted(valid_cited_ids):
            cit = self.citation_mgr.get_citation(cid)
            if cit:
                aligned_citations.append({
                    "id": str(cit.id),
                    "url": cit.url,
                    "title": cit.title,
                    "snippet": cit.snippet,
                    "credibility": f"{cit.credibility:.2f}"
                })
                
        # If the LLM didn't cite anything in text but we have search results, default to linking top search results
        if not aligned_citations and sources_list:
            for src in sources_list[:3]:
                cit_id = self.citation_mgr.add_source(
                    url=src["url"],
                    snippet=src["snippet"],
                    title=src["title"],
                    credibility=src.get("credibility", 0.85)
                )
                aligned_citations.append({
                    "id": str(cit_id),
                    "url": src["url"],
                    "title": src["title"],
                    "snippet": src["snippet"],
                    "credibility": f"{src.get('credibility', 0.85):.2f}"
                })
                
        validated_result.citations_used = aligned_citations
        
        return validated_result

