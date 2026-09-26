import pytest
from core.evidence_models import EvidenceLedger, StructuredClaim, SourceType, ClaimStatus
from core.superpower_synthesizer import SuperpowerSynthesizer
from api.routes import _parse_report_evidence


def test_claim_status_semantics_uses_supported_not_verified():
    """Verify that Critic-approved claims are labeled SUPPORTED (GREEN), never VERIFIED."""
    ledger = EvidenceLedger(session_id="test_ev_1")
    claim = StructuredClaim(
        claim_id="CLM-01",
        statement="PostgreSQL supports multi-version concurrency control (MVCC).",
        status=ClaimStatus.SUPPORTED.value,
        source_type=SourceType.LIVE_EXTERNAL
    )
    ledger.claims.append(claim)
    ledger.compute_counts()

    assert ledger.supported_count == 1
    assert "VERIFIED" not in claim.status
    assert "SUPPORTED" in claim.status


def test_local_reference_distinct_from_live_external():
    """Verify local KB facts receive LOCAL_REFERENCE source_type and do not count as live web evidence."""
    ledger = EvidenceLedger(session_id="test_ev_2")
    c1 = StructuredClaim(
        claim_id="CLM-01",
        statement="PostgreSQL WAL replication is reliable.",
        status=ClaimStatus.SUPPORTED.value,
        source_type=SourceType.LIVE_EXTERNAL
    )
    c2 = StructuredClaim(
        claim_id="CLM-02",
        statement="Offline architectural standard pattern for microservices.",
        status=ClaimStatus.SUPPORTED.value,
        source_type=SourceType.LOCAL_REFERENCE
    )
    ledger.claims.extend([c1, c2])
    ledger.compute_counts()

    assert ledger.live_external_count == 1
    assert ledger.local_reference_count == 1
    assert ledger.supported_count == 2


def test_template_reference_isolation():
    """Verify pre-curated archetype template material is not counted as empirical claims."""
    ledger = EvidenceLedger(session_id="test_ev_3")
    c1 = StructuredClaim(
        claim_id="CLM-01",
        statement="Supabase uses Postgres 16.",
        status=ClaimStatus.SUPPORTED.value,
        source_type=SourceType.LIVE_EXTERNAL
    )
    c_template = StructuredClaim(
        claim_id="CLM-02",
        statement="Curated TypeScript snippet for Supabase Realtime channel.",
        status=ClaimStatus.TEMPLATE_REFERENCE.value,
        source_type=SourceType.TEMPLATE_REFERENCE,
        is_empirical=False
    )
    ledger.claims.extend([c1, c_template])
    ledger.compute_counts()

    assert ledger.supported_count == 1
    assert ledger.template_reference_count == 1
    assert c_template.is_empirical is False


def test_markdown_cannot_create_verification_out_of_thin_air():
    """Verify that _parse_report_evidence correctly marks counts based on structured status strings."""
    dummy_markdown = """
| Claim ID | Substantive Empirical Claim | Attributed Specialist | Tool Privileges | Evidence Anchor | Verification Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CLM-01** | Production metrics verified | Lead Specialist | `web_search` | [E-01] | **SUPPORTED (GREEN)** |
| **CLM-02** | Contradicted latency bounds | Risk Specialist | `sla_monitor` | [E-02] | **CONTRADICTED** |
| **CLM-03** | Insufficient source material | Auditor | `tool` | [E-03] | **INSUFFICIENT EVIDENCE** |
"""
    parsed = _parse_report_evidence(dummy_markdown, "sess_md_test")
    assert parsed["supported_count"] == 1
    assert parsed["contradicted_count"] == 1
    assert parsed["insufficient_count"] == 1
