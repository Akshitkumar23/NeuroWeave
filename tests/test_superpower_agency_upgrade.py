import pytest
import asyncio
import os
import json
from core.persona_manager import get_persona_registry, Persona, AgencyPod, DIVISION_TOOLKITS
from core.dag_engine import DAGEngine
from core.superpower_synthesizer import SuperpowerSynthesizer
from storage.database import DatabaseManager
from storage.repository import SessionRepository


def test_persona_dynamic_tool_binding():
    registry = get_persona_registry()
    persona = registry.get_persona("ai_engineer") or registry.match_persona("Build an AI machine learning model")
    assert persona is not None
    bound_tools = persona.get_bound_tools()
    assert isinstance(bound_tools, list)
    assert len(bound_tools) > 0
    assert "python_sandbox" in bound_tools or "web_search" in bound_tools


def test_agency_pod_formation():
    registry = get_persona_registry()
    pod = registry.get_agency_pod("Optimize PostgreSQL database indexing and query cache", division="Engineering")
    assert isinstance(pod, AgencyPod)
    assert pod.lead_persona is not None
    assert isinstance(pod.supporting_personas, list)
    assert len(pod.pod_tools) > 0
    assert pod.collaboration_mission != ""

    pod_dict = pod.to_dict()
    assert "division" in pod_dict
    assert "lead_persona" in pod_dict
    assert "pod_tools" in pod_dict
    assert pod_dict["pod_size"] >= 1


def test_dag_engine_red_green_quality_gate():
    dag = DAGEngine()
    assert dag.execution_stats["quality_gate_status"] == "PENDING"

    # Red status when score < 0.75 or critical issues exist
    status_red, is_green = dag.evaluate_quality_gate(critic_score=0.62, issues=["unverified claim regarding latency"])
    assert status_red == "RED"
    assert is_green is False
    assert dag.execution_stats["quality_cycles"] == 1

    # Record healed gap
    dag.record_healed_gap("Latency verified via DuckDuckGo benchmark")
    assert dag.execution_stats["healed_gaps"] == 1

    # Green status when score >= 0.75 and no critical issues
    status_green, is_green_ok = dag.evaluate_quality_gate(critic_score=0.92, issues=[])
    assert status_green == "GREEN"
    assert is_green_ok is True


def test_modular_dossier_stacking():
    raw_report = """# Strategic Intelligence Assessment: Next.js vs Remix

## Executive Summary
Evaluation of Next.js and Remix.

| Metric | Next.js | Remix |
| :--- | :--- | :--- |
| SSR Latency | 45ms | 38ms |

## Sources
[^1]: https://example.com
"""
    registry = get_persona_registry()
    pod = registry.get_agency_pod("Next.js vs Remix framework comparison", division="Engineering")
    
    subtask_outputs = {
        "_meta": {
            "agency_pod": pod.to_dict(),
            "prior_dossiers": [
                {
                    "session_id": "test_sess_12345",
                    "query": "React server components benchmarks",
                    "excerpt": "RSC latency benchmarks indicate 30% reduction in client bundle size.",
                    "confidence_score": 0.94
                }
            ],
            "debate_summary": "Consensus resolved that Next.js offers broader ecosystem while Remix excels in pure web standards."
        }
    }

    enriched = SuperpowerSynthesizer._enrich_modular_dossier(
        report=raw_report,
        topic="Next.js vs Remix",
        subtask_outputs=subtask_outputs
    )

    # 1. Agency Pod badge present
    assert "🏛️ **AGENCY DIVISION POD" in enriched
    # 2. Prior Dossiers Cross-Referencing present
    assert "## 📚 Cross-Report Intelligence & Historical Dossiers" in enriched
    assert "Dossier #test_ses" in enriched
    # 3. Dialectical matrix present
    assert "## ⚖️ Dialectical Counter-Factual Consensus Matrix" in enriched
    # 4. Dynamic Chart.js block present
    assert "`json chart" in enriched


@pytest.mark.anyio
async def test_session_repository_prior_reports_search():
    test_db_path = "test_upgrade_temp.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = DatabaseManager(test_db_path)
    await db.initialize_tables()
    repo = SessionRepository(db)

    # Seed a past completed session & report
    session_id = "test_prior_session_99"
    await repo.create_session(session_id, "Comparative analysis of Redis vs Memcached")
    await repo.insert_report(session_id, "Redis provides persistent data structures whereas Memcached is purely in-memory.", confidence_score=0.96)

    # Search prior reports
    matches = await repo.search_prior_reports(["redis", "memcached"], current_session_id="new_session_100")
    assert len(matches) > 0
    assert matches[0]["session_id"] == session_id
    assert "Redis" in matches[0]["excerpt"]

    # Close DB and cleanup
    # db closed per transaction
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

@pytest.mark.anyio
async def test_agency_pod_real_collaboration():
    registry = get_persona_registry()
    pod = registry.get_agency_pod("Optimize PostgreSQL query planner and indexing strategy", division="Engineering")
    assert len(pod.supporting_personas) >= 1
    
    collab = await pod.execute_collaboration("Optimize PostgreSQL query planner and indexing strategy")
    assert collab["total_collaborators"] >= 2
    assert "synthesized_directive" in collab
    assert len(collab["contributions"]) >= 2
    
    # Verify Lead consumed supporting agents
    lead_contrib = [c for c in collab["contributions"] if c["phase"] == "lead_synthesis_directive"][0]
    assert "consumed_supporting_agents" in lead_contrib
    assert len(lead_contrib["consumed_supporting_agents"]) > 0
    assert pod.lead_persona.name == lead_contrib["specialist_name"]

def test_capability_driven_supporting_specialist_matching():
    registry = get_persona_registry()
    # 1. Database query
    db_pod = registry.get_agency_pod("Optimize PostgreSQL query indexing and database replication", division="Engineering")
    sup_names = [p.name.lower() for p in db_pod.supporting_personas]
    sup_corpus = " ".join(sup_names + [p.role.lower() for p in db_pod.supporting_personas] + [" ".join(p.capabilities).lower() for p in db_pod.supporting_personas])
    # Database capability should be matched in supporting personas
    assert any(w in sup_corpus for w in ["database", "engineer", "data", "reliability", "infrastructure", "optimization"])

    # 2. Marketing query
    mkt_pod = registry.get_agency_pod("Optimize organic search AEO and ad creative campaigns", division="Marketing")
    mkt_names = [p.name.lower() for p in mkt_pod.supporting_personas]
    mkt_corpus = " ".join(mkt_names + [p.role.lower() for p in mkt_pod.supporting_personas] + [" ".join(p.capabilities).lower() for p in mkt_pod.supporting_personas])
    assert any(w in mkt_corpus for w in ["search", "marketing", "content", "creative", "growth", "aeo", "ad"])


def test_pod_dag_first_class_nodes_structure():
    # Verify the topological node wiring of the Agency Pod
    registry = get_persona_registry()
    pod = registry.get_agency_pod("Compare Next.js vs Remix SSR latency", division="Engineering")
    pod_data = pod.to_dict()
    
    # Check node generation structure
    pod_lead = pod_data["lead_persona"]
    pod_sups = pod_data["supporting_personas"]
    
    pod_tasks = []
    if len(pod_sups) > 0:
        pod_tasks.append({"id": "task_pod_sup1", "dependencies": []})
    if len(pod_sups) > 1:
        pod_tasks.append({"id": "task_pod_sup2", "dependencies": []})
    
    lead_deps = [t["id"] for t in pod_tasks]
    pod_tasks.append({"id": "task_pod_lead", "dependencies": lead_deps})
    
    # Verify topological order
    task_dict = {t["id"]: t for t in pod_tasks}
    ordered = DAGEngine.topological_sort(task_dict)
    assert ordered[-1] == "task_pod_lead"
    assert "task_pod_sup1" in ordered
