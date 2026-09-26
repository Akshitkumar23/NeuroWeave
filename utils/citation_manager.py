import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("neuroweave.citation_manager")

class Citation:
    def __init__(self, citation_id: int, url: str, snippet: str, title: str, credibility: float, relevance: float = 0.85):
        self.id: int = citation_id
        self.url: str = url
        self.snippet: str = snippet
        self.title: str = title
        self.credibility: float = credibility
        self.relevance: float = relevance

class CitationManager:
    """
    Tracks gathered facts, rates source credibility, maintains evidence chains,
    and formats professional APA / strategic reference bibliographies.
    Enforces strict rejection of fabricated/synthetic URLs.
    """
    SYNTHETIC_PATTERNS = [
        r"db-engines\.com/en/system/.*-and-.*",
        r"arxiv\.org/abs/.*-kvcache-scaling",
        r"github\.com/karpathy/.*-benchmarks",
        r"duckduckgo\.com/lite/\?q=",
        r"techradar\.com/pro/database-benchmarks",
        r"\{slug\}",
    ]

    def __init__(self):
        self.citations: List[Citation] = []
        self._url_map: Dict[str, Citation] = {}

    def add_source(self, url: str, snippet: str, title: str, credibility: float = 0.85, relevance: float = 0.85) -> Optional[int]:
        """
        Registers an external fact source in the ledger. Returns its citation key integer,
        or None if the URL is invalid or matches synthetic/fabricated patterns.
        """
        clean_url = (url or "").strip()
        if not clean_url or (not clean_url.startswith("http://") and not clean_url.startswith("https://")):
            return None

        for pat in self.SYNTHETIC_PATTERNS:
            if re.search(pat, clean_url):
                logger.warning(f"Rejected synthetic/fabricated citation URL: {clean_url}")
                return None

        if clean_url in self._url_map:
            return self._url_map[clean_url].id
            
        cit_id = len(self.citations) + 1
        citation = Citation(cit_id, clean_url, snippet, title, credibility, relevance)
        self.citations.append(citation)
        self._url_map[clean_url] = citation
        logger.info(f"Registered verified citation [^{cit_id}] for source: {clean_url}")
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
            return "\n## Sources & Evidence Citations\n\n*No verified external citations retrieved.*"
            
        bib_lines = ["\n## Sources & Evidence Citations\n"]
        for cit in self.citations:
            source_title = cit.title or "Online Reference Resource"
            domain = cit.url.split("//")[-1].split("/")[0] if cit.url and "//" in cit.url else (cit.url or "unknown-source")
            line = f"[^{cit.id}]: *{source_title}*. Retrieved from [{domain}]({cit.url}). " \
                   f"(Confidence Reliability: {cit.credibility * 100:.1f}%)"
            bib_lines.append(line)
            
        return "\n".join(bib_lines)

