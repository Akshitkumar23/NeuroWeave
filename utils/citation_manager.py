import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("neuroweave.citation_manager")

class Citation:
    def __init__(self, citation_id: int, url: str, snippet: str, title: str, credibility: float):
        self.id: int = citation_id
        self.url: str = url
        self.snippet: str = snippet
        self.title: str = title
        self.credibility: float = credibility

class CitationManager:
    """
    Tracks gathered facts, rates source credibility, maintains evidence chains,
    and formats professional APA / strategic reference bibliographies.
    """
    def __init__(self):
        self.citations: List[Citation] = []
        self._url_map: Dict[str, Citation] = {}

    def add_source(self, url: str, snippet: str, title: str, credibility: float = 0.85) -> int:
        """
        Registers an external fact source in the ledger. Returns its citation key integer.
        """
        if url in self._url_map:
            return self._url_map[url].id
            
        cit_id = len(self.citations) + 1
        citation = Citation(cit_id, url, snippet, title, credibility)
        self.citations.append(citation)
        self._url_map[url] = citation
        logger.info(f"Registered citation [^{cit_id}] for source: {url}")
        return cit_id

    def get_citation(self, citation_id: int) -> Optional[Citation]:
        if 0 < citation_id <= len(self.citations):
            return self.citations[citation_id - 1]
        return None

    def generate_bibliography(self) -> str:
        """
        Formats APA-like research references at the bottom of the synthesized reports.
        """
        if not self.citations:
            return ""
            
        bib_lines = ["\n## Sources & Evidence Citations\n"]
        for cit in self.citations:
            # Format APA string
            source_title = cit.title or "Online Reference Resource"
            domain = cit.url.split("//")[-1].split("/")[0] if cit.url and "//" in cit.url else (cit.url or "unknown-source")
            line = f"[^{cit.id}]: *{source_title}*. Retrieved from [{domain}]({cit.url}). " \
                   f"(Confidence Reliability: {cit.credibility * 100:.1f}%)"
            bib_lines.append(line)
            
        return "\n".join(bib_lines)

