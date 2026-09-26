"""
NeuroWeave Canonical Evidence & Claim Data Models (Phase 5.2).

Establishes the authoritative structured state for claims, evidence provenance,
source classifications, and tool authorization telemetry. Eliminates Markdown-parsing-as-truth.
"""

from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class SourceType(str, Enum):
    LIVE_EXTERNAL = "LIVE_EXTERNAL"
    SECONDARY_EXTERNAL = "SECONDARY_EXTERNAL"
    LOCAL_REFERENCE = "LOCAL_REFERENCE"
    CALCULATION_ARTIFACT = "CALCULATION_ARTIFACT"
    TEMPLATE_REFERENCE = "TEMPLATE_REFERENCE"


class ClaimStatus(str, Enum):
    SUPPORTED = "SUPPORTED (GREEN)"
    PARTIALLY_SUPPORTED = "PARTIALLY SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT EVIDENCE"
    CONTRADICTED = "CONTRADICTED"
    RESOLVED = "RESOLVED"
    TEMPLATE_REFERENCE = "TEMPLATE REFERENCE"


class EvidenceItem(BaseModel):
    evidence_id: str
    source_url: str = ""
    source_title: str = "Technical Reference"
    snippet: str = ""
    source_type: SourceType = SourceType.LIVE_EXTERNAL
    credibility: float = 0.90
    provenance_note: Optional[str] = None
    is_live: bool = True


class GranularLineageChain(BaseModel):
    evidence_id: str
    source_anchor: str
    extracted_fact: str
    originating_node: str
    attributed_specialist: str
    tools_executed: str
    critic_verdict: str = "SUPPORTED (GREEN)"
    critic_confidence: float = 0.90


class StructuredClaim(BaseModel):
    claim_id: str
    statement: str
    specialist: str = "Lead Specialist"
    tools: str = "web_search"
    evidence_anchor: str = "Empirical Telemetry"
    status: str = "SUPPORTED (GREEN)"
    source_type: SourceType = SourceType.LIVE_EXTERNAL
    is_empirical: bool = True
    chain: Optional[GranularLineageChain] = None


class EvidenceLedger(BaseModel):
    session_id: str
    claims: List[StructuredClaim] = Field(default_factory=list)
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    sources_count: int = 0
    supported_count: int = 0
    partially_supported_count: int = 0
    insufficient_count: int = 0
    contradicted_count: int = 0
    stale_count: int = 0
    local_reference_count: int = 0
    live_external_count: int = 0
    calculation_count: int = 0
    template_reference_count: int = 0

    def compute_counts(self):
        self.sources_count = len(self.citations)
        self.supported_count = sum(
            1 for c in self.claims if "SUPPORTED" in c.status.upper() and "PARTIALLY" not in c.status.upper()
        ) + sum(1 for c in self.claims if "RESOLVED" in c.status.upper())
        self.partially_supported_count = sum(1 for c in self.claims if "PARTIALLY" in c.status.upper())
        self.insufficient_count = sum(1 for c in self.claims if "INSUFFICIENT" in c.status.upper())
        self.contradicted_count = sum(1 for c in self.claims if "CONTRADICTED" in c.status.upper() or "REJECTED" in c.status.upper())
        self.stale_count = sum(1 for c in self.claims if "STALE" in c.status.upper() or "HISTORICAL" in c.status.upper())
        self.local_reference_count = sum(1 for c in self.claims if c.source_type == SourceType.LOCAL_REFERENCE)
        self.live_external_count = sum(1 for c in self.claims if c.source_type in (SourceType.LIVE_EXTERNAL, SourceType.SECONDARY_EXTERNAL))
        self.calculation_count = sum(1 for c in self.claims if c.source_type == SourceType.CALCULATION_ARTIFACT)
        self.template_reference_count = sum(1 for c in self.claims if c.source_type == SourceType.TEMPLATE_REFERENCE)
