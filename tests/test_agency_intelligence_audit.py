import pytest
import asyncio
from core.persona_manager import get_persona_registry, AgencyPod
from core.dag_engine import DAGEngine
from core.superpower_synthesizer import SuperpowerSynthesizer


# =========================================================================
# PILLAR A: 20-Query Diversity & Non-Stagnation Stress Test
# =========================================================================
def test_pillar_a_20_query_diversity_matrix():
    registry = get_persona_registry()
    
    test_queries = [
        ("Optimize PostgreSQL query indexing, execution planner, and replication lag", "Engineering"),
        ("HIPAA PHI compliance audit and data privacy enforcement in healthtech", "Security"),
        ("Next.js vs Remix server-side rendering hydration latency benchmarks", "Engineering"),
        ("Discounted Cash Flow (DCF) valuation and 5-year revenue forecast for SaaS", "Finance"),
        ("Kubernetes container security, runtime eBPF monitoring, and pod isolation", "Security"),
        ("B2B SaaS customer churn reduction and net revenue retention playbook", "Marketing"),
        ("TimescaleDB IoT sensor telemetry aggregation and hypertable retention", "Engineering"),
        ("AEO generative engine optimization and organic brand citation strategy", "Marketing"),
        ("Mobile app store optimization (ASO) and conversion rate funnel", "Marketing"),
        ("Zero-trust API gateway authentication and OAuth2 token rotation", "Security"),
        ("Automated unit test generation and boundary fuzzer for Python FastAPI", "Testing"),
        ("Ad creative performance, ROAS maximization, and paid social targeting", "Paid Media"),
        ("Customer support ticket clustering and automated SLA escalation", "Support"),
        ("Git workflow master, CI/CD pipeline automation, and pre-commit hooks", "Engineering"),
        ("Executive KPI financial dashboard with CAC, LTV, and runway projections", "Finance"),
        ("LLM transformer VRAM quantization and speculative decoding memory footprint", "Engineering"),
        ("Payment gateway microservices idempotency and webhook retry architecture", "Engineering"),
        ("Civil engineering GIS geospatial routing and spatial database query", "Specialized"),
        ("Algorithmic cryptocurrency trading bot with EMA crossover and risk manager", "Specialized"),
        ("Web application accessibility (WCAG 2.1 AA) audit and screen reader support", "Testing")
    ]
    
    lead_personas = set()
    supporting_personas = set()
    pod_records = []
    
    for query, expected_div in test_queries:
        pod = registry.get_agency_pod(query)
        assert isinstance(pod, AgencyPod)
        assert pod.lead_persona is not None
        assert len(pod.supporting_personas) >= 1
        
        lead_personas.add(pod.lead_persona.name)
        for sp in pod.supporting_personas:
            supporting_personas.add(sp.name)
            
        pod_records.append({
            "query": query[:40],
            "lead": pod.lead_persona.name,
            "sups": [p.name for p in pod.supporting_personas],
            "tools": pod.pod_tools[:3]
        })

    print(f"\n[PILLAR A AUDIT] 20 Queries Processed.")
    print(f"Distinct Lead Personas Activated: {len(lead_personas)} / 20")
    print(f"Distinct Supporting Personas Activated: {len(supporting_personas)}")
    
    # Rigorous diversity assertion:
    # 20 diverse queries must NOT collapse into the same 1-3 personas!
    assert len(lead_personas) >= 12, f"Too low diversity in Leads: {len(lead_personas)}"
    assert len(supporting_personas) >= 15, f"Too low diversity in Supporting: {len(supporting_personas)}"


# =========================================================================
# PILLAR B: Causal Collaboration Proof (A/B Mutation Test)
# =========================================================================
def test_pillar_b_causal_collaboration_mutation():
    async def _run_b():
        registry = get_persona_registry()
        pod = registry.get_agency_pod("Optimize PostgreSQL connection pool and query cache", division="Engineering")
        
        # Run variant A: Supporting Specialist 1 reports latency bottleneck
        collab_a = await pod.execute_collaboration(
            query="Optimize PostgreSQL connection pool",
            override_sup1_output="Supporting Specialist 1: Latency critical limit is 50ms max under heavy write load."
        )
        
        # Run variant B: Supporting Specialist 1 reports memory leak
        collab_b = await pod.execute_collaboration(
            query="Optimize PostgreSQL connection pool",
            override_sup1_output="Supporting Specialist 1: Massive memory leak detected in connection pool worker threads."
        )
        
        dir_a = collab_a["synthesized_directive"]
        dir_b = collab_b["synthesized_directive"]
        
        # Causal assertions:
        assert dir_a != dir_b, "Lead directive failed to causally change when supporting input mutated!"
        assert "50ms max" in dir_a, "Lead directive failed to incorporate finding A!"
        assert "memory leak" in dir_b, "Lead directive failed to incorporate finding B!"
        
        print("\n[PILLAR B AUDIT] Causal mutation verified: Lead directive altered dynamically based on Support 1 finding.")
    asyncio.run(_run_b())


# =========================================================================
# PILLAR C: Targeted RED -> GREEN Self-Healing Loop Proof
# =========================================================================
def test_pillar_c_targeted_red_to_green_self_healing():
    dag = DAGEngine()
    assert dag.execution_stats["quality_gate_status"] == "PENDING"
    
    # 1. Trigger RED state via Critic with specific identified gap
    specific_issue = "Missing 5-year CAGR financial calculation verification"
    status_1, is_green_1 = dag.evaluate_quality_gate(critic_score=0.55, issues=[specific_issue])
    assert status_1 == "RED"
    assert is_green_1 is False
    assert dag.execution_stats["quality_cycles"] == 1
    
    # 2. Simulate targeted gap resolution
    targeted_gap_resolution = f"Targeted research completed for gap: {specific_issue}"
    dag.record_healed_gap(targeted_gap_resolution)
    assert dag.execution_stats["healed_gaps"] == 1
    
    # 3. Re-evaluate quality gate after targeted gap healing -> GREEN
    dag.execution_stats["total_tasks"] = 2
    dag.execution_stats["completed"] = 2
    status_2, is_green_2 = dag.evaluate_quality_gate(critic_score=0.94, issues=[])
    assert status_2 == "GREEN"
    assert is_green_2 is True
    assert dag.execution_stats["quality_gate_status"] == "GREEN"
    assert dag.get_execution_summary()["is_green"] is True
    
    print("\n[PILLAR C AUDIT] Targeted RED -> GREEN quality cycle verified.")


# =========================================================================
# PILLAR D: Claim-Level Data Lineage Table Proof
# =========================================================================
def test_pillar_d_claim_level_data_lineage():
    registry = get_persona_registry()
    pod = registry.get_agency_pod("Benchmark Next.js vs Remix SSR throughput", division="Engineering")
    
    raw_report = """# Strategic Intelligence Assessment: Next.js vs Remix
## Executive Summary
Evaluation of Next.js and Remix.
| Framework | Latency |
| :--- | :--- |
| Next.js | 45ms |
## Sources
[^1]: https://example.com
"""
    subtask_outputs = {
        "_meta": {
            "agency_pod": pod.to_dict(),
            "pod_collaboration": {
                "synthesized_directive": "Execute Next.js App Router pilot with automated edge caching."
            },
            "synced_claims": [
                {"claim": "Next.js App Router utilizes React Server Components for streaming SSR", "source": "Next.js Official Documentation", "url": "https://nextjs.org/docs", "relevance": 0.95},
                {"claim": "Remix leverages native Web Fetch API request handlers with loader data streaming", "source": "Remix Architecture Specification", "url": "https://remix.run/docs", "relevance": 0.92},
                {"claim": "Edge rendering p99 response latency benchmarks at 45ms under concurrent load", "source": "Vercel Edge Network Telemetry", "url": "https://vercel.com/edge", "relevance": 0.88},
                {"claim": "Client-side JavaScript bundle size is minimized through server-first execution", "source": "Web Performance Architecture Review", "url": "https://w3.org/perf", "relevance": 0.85}
            ]
        }
    }
    
    enriched = SuperpowerSynthesizer._enrich_modular_dossier(
        report=raw_report,
        topic="Next.js vs Remix SSR",
        subtask_outputs=subtask_outputs
    )
    
    # Assert Granular Claim Lineage Table
    assert "## 🔍 Auditable Claim-Level Provenance & Lineage Trace" in enriched
    assert "| Claim ID | Substantive Empirical Claim | Attributed Specialist | Tool Privileges | Evidence Anchor | Verification Status |" in enriched
    assert "**CLM-01**" in enriched
    assert "**CLM-02**" in enriched
    assert "**CLM-03**" in enriched
    assert "**CLM-04**" in enriched
    assert "**VERIFIED (GREEN)**" in enriched
    assert pod.lead_persona.name in enriched
    
    print("\n[PILLAR D AUDIT] Auditable Claim-Level Lineage verified in synthesized dossier.")
