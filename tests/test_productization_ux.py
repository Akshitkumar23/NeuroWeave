"""
tests/test_productization_ux.py
Rigorous verification of Phase 5 Productization, UX, Report Quality,
7 Report Modes, Claim Lineage Provenance, and Zero-API compliance.
"""

import pytest
import asyncio
from core.deterministic_engine import QueryIntent, detect_query_intent
from core.superpower_synthesizer import SuperpowerSynthesizer, resolve_report_mode
from api.routes import _parse_report_evidence

@pytest.mark.parametrize("query,expected_mode", [
    ("PostgreSQL vs MongoDB throughput comparison under high concurrency", "COMPARISON"),
    ("Deep dive into modern transformer KV cache attention mechanisms", "RESEARCH"),
    ("A startup has 50 lakh revenue growing at 25% annually for 5 years calculate total cumulative revenue", "NUMERICAL"),
    ("Who will be the undisputed market leader in AI search engines by 2035?", "FORECAST / FUTURE"),
    ("Design a high-availability microservices architecture with Redis and Kafka", "TECHNICAL"),
    ("Help me decide between Supabase and Firebase for high traffic real-time sync", "DECISION SUPPORT"),
    ("What is Model Context Protocol and how is it different from traditional REST APIs?", "CONCEPTUAL"),
])
def test_seven_publication_report_modes(query, expected_mode):
    mode = resolve_report_mode(query)
    assert mode == expected_mode, f"Expected mode {expected_mode} for '{query}', got {mode}"


def test_dossier_mandatory_sections_and_mode_badging():
    query = "PostgreSQL vs MongoDB for high-throughput time-series IoT data"
    brief = SuperpowerSynthesizer.synthesize(
        topic=query,
        subtask_outputs={
            "_meta": {
                "agency_pod": {
                    "division": "engineering",
                    "lead_persona": {"name": "System Architect", "role": "Principal Systems Specialist", "bound_tools": ["web_search", "python_sandbox"]},
                    "supporting_personas": [
                        {"name": "Backend Architect", "role": "Database Specialist", "bound_tools": ["domain_analyzer"]},
                        {"name": "Developer Tooling Engineer", "role": "Operational Auditor", "bound_tools": ["python_sandbox"]}
                    ]
                },
                "citations": [
                    {"id": "1", "title": "PostgreSQL Benchmarks", "url": "https://postgresql.org/benchmarks"},
                    {"id": "2", "title": "MongoDB Enterprise Specs", "url": "https://mongodb.com/specs"}
                ],
                "synced_claims": [
                    {"claim": "PostgreSQL TimescaleDB hypertable partitioning achieves 150k writes/sec", "source": "PostgreSQL Benchmarks", "url": "https://postgresql.org/benchmarks", "relevance": 0.95},
                    {"claim": "MongoDB WiredTiger storage engine uses document-level locking and compression", "source": "MongoDB Enterprise Specs", "url": "https://mongodb.com/specs", "relevance": 0.92},
                    {"claim": "Time-series compression reduces storage requirements by up to 90 percent", "source": "PostgreSQL Benchmarks", "url": "https://postgresql.org/benchmarks", "relevance": 0.90},
                    {"claim": "High ingestion workloads exhibit lower p99 write latency on partitioned tables", "source": "Database Ingestion Telemetry", "url": "https://postgresql.org/benchmarks", "relevance": 0.88}
                ]
            }
        }
    )

    # 1. Mode Badge
    assert "> 🏷️ **REPORT MODE: COMPARISON**" in brief

    # 2. Agency Pod Header
    assert "🏛️ **AGENCY DIVISION POD: ENGINEERING**" in brief
    assert "System Architect" in brief
    assert "Backend Architect" in brief
    assert "Developer Tooling Engineer" in brief

    # 3. Mandatory Sections
    assert "## Executive Summary" in brief
    assert "## Key Findings" in brief or "## Architectural & Strategic Analysis" in brief
    assert "## Sources & Evidence Citations" in brief
    assert "## ⚖️ Dialectical Counter-Factual Consensus Matrix" in brief
    assert "## 🔍 Auditable Claim-Level Provenance & Lineage Trace" in brief

    # 4. Provenance Table and Chains
    assert "| **CLM-01** |" in brief
    assert "| **CLM-02** |" in brief
    assert "| **CLM-03** |" in brief
    assert "| **CLM-04** |" in brief
    assert "### 🔗 Granular Evidence-to-Claim Provenance Chains" in brief
    assert "**`CLM-01` ➔ `E-01`**" in brief
    assert "**`CLM-02` ➔ `E-02`**" in brief
    assert "**`CLM-03` ➔ `E-03`**" in brief


def test_evidence_parser_extracts_structured_chains():
    sample_report = """# Executive Dossier
> 🏷️ **REPORT MODE: TECHNICAL**

## Executive Summary
Direct answer to architectural scaling.

## Sources & Evidence Citations
[^1]: *Kafka Architecture Guide*. Retrieved from [apache.org](https://kafka.apache.org/documentation)
[^2]: *Redis Clustering Whitepaper*. Retrieved from [redis.io](https://redis.io/docs/clustering)

## 🔍 Auditable Claim-Level Provenance & Lineage Trace

| Claim ID | Substantive Empirical Claim | Attributed Specialist | Tool Privileges | Evidence Anchor | Verification Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CLM-01** | High availability messaging cluster design | System Architect (Lead) | `web_search` | [E-01] https://kafka.apache.org/documentation | **VERIFIED (GREEN)** |
| **CLM-02** | Low-latency state caching boundaries | Backend Architect (Support 1) | `domain_analyzer` | [E-02] https://redis.io/docs/clustering | **VERIFIED (GREEN)** |

### 🔗 Granular Evidence-to-Claim Provenance Chains
- **`CLM-01` ➔ `E-01`**:
  - **Source Anchor**: `https://kafka.apache.org/documentation`
  - **Extracted Fact**: *"Kafka provides partitioned commit log durability across replica nodes."*
  - **Originating Node**: `task_pod_lead` | **Attributed Specialist**: `System Architect`
  - **Tool Privileges Executed**: `web_search`
  - **Critic Verdict**: `SUPPORTED (GREEN)` — Confidence Score: 0.95 / 1.00

- **`CLM-02` ➔ `E-02`**:
  - **Source Anchor**: `https://redis.io/docs/clustering`
  - **Extracted Fact**: *"Redis in-memory store offers sub-millisecond read latencies."*
  - **Originating Node**: `task_pod_sup1` | **Attributed Specialist**: `Backend Architect`
  - **Tool Privileges Executed**: `domain_analyzer`
  - **Critic Verdict**: `SUPPORTED (GREEN)` — Validated
"""

    parsed = _parse_report_evidence(sample_report, "sess-test-123")
    assert parsed["session_id"] == "sess-test-123"
    assert len(parsed["citations"]) == 2
    assert parsed["citations"][0]["url"] == "https://kafka.apache.org/documentation"

    assert len(parsed["claims"]) == 2
    clm1 = parsed["claims"][0]
    assert clm1["claim_id"] == "CLM-01"
    assert clm1["status"] == "VERIFIED (GREEN)"
    assert clm1["chain"]["originating_node"] == "task_pod_lead"
    assert clm1["chain"]["attributed_specialist"] == "System Architect"
    assert "SUPPORTED (GREEN)" in clm1["chain"]["critic_verdict"]

    assert parsed["verified_count"] == 2
    assert parsed["sources_count"] == 2


def test_zero_api_compliance():
    """Verify that no external API keys, paid services, or Ollama are required."""
    from api.routes import get_key_status
    status = asyncio.run(get_key_status())
    assert status["mode"] == "zero_api"
    assert status["neuroweave_mode"] == "ZERO_API"
    assert status["active_count"] == 0
