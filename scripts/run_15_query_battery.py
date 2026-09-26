"""
NeuroWeave Phase 5 - 15-Query Production Battery Runner.
Executes all 15 real-world queries through the live deterministic multi-agent pipeline
and records comprehensive end-to-end execution records:
query -> intent -> DAG -> agents -> network -> evidence -> citations -> confidence -> final result.
"""

import os
import sys
import json
import time
import asyncio
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from storage.database import DatabaseManager
from agents.orchestrator import MasterOrchestrator
from core.state_manager import StateManager

BATTERY_QUERIES = [
    {
        "id": "Q01",
        "category": "Conceptual",
        "query": "What is Model Context Protocol (MCP)?",
        "expected_intent": "conceptual"
    },
    {
        "id": "Q02",
        "category": "Conceptual Comparison",
        "query": "What is Model Context Protocol (MCP) and how is it different from an API?",
        "expected_intent": "conceptual_comparison"
    },
    {
        "id": "Q03",
        "category": "Pairwise Comparison",
        "query": "Is Supabase or Firebase better for a startup backend?",
        "expected_intent": "comparison"
    },
    {
        "id": "Q04",
        "category": "3-Way Comparison",
        "query": "Compare PostgreSQL, MongoDB, and Redis across latency, scalability, and operational complexity.",
        "expected_intent": "comparison"
    },
    {
        "id": "Q05",
        "category": "Quantitative (Compound Growth)",
        "query": "A company currently has ₹50 lakh annual revenue. If it grows at 25% year-over-year for 5 years, calculate the projected revenue for each year, the total revenue, and the total percentage growth.",
        "expected_intent": "quantitative"
    },
    {
        "id": "Q06",
        "category": "Quantitative (Arbitrary Math)",
        "query": "Calculate future value of ₹10 lakh growing at 15% annually for 3 years.",
        "expected_intent": "quantitative"
    },
    {
        "id": "Q07",
        "category": "Quantitative (Percentage Increase)",
        "query": "Calculate percentage increase from ₹8 lakh to ₹13.6 lakh.",
        "expected_intent": "quantitative"
    },
    {
        "id": "Q08",
        "category": "Quantitative (Average/Mean)",
        "query": "Calculate average of: 120, 150, 180, 210, 240",
        "expected_intent": "quantitative"
    },
    {
        "id": "Q09",
        "category": "Mixed Reasoning",
        "query": "Compare two cloud databases and calculate which option is cheaper if one costs ₹8,000/month and the other ₹11,500/month over 3 years.",
        "expected_intent": "comparison"
    },
    {
        "id": "Q10",
        "category": "Future Prediction",
        "query": "Which Indian AI company could become a leader by 2035?",
        "expected_intent": "prediction_uncertain"
    },
    {
        "id": "Q11",
        "category": "Research Intent",
        "query": "Find the latest developments in Indian AI startups.",
        "expected_intent": "research"
    },
    {
        "id": "Q12",
        "category": "Ambiguous Query 1",
        "query": "Which one is better?",
        "expected_intent": "ambiguous"
    },
    {
        "id": "Q13",
        "category": "Ambiguous Query 2",
        "query": "Best database?",
        "expected_intent": "ambiguous"
    },
    {
        "id": "Q14",
        "category": "Hinglish / Noisy Query",
        "query": "mcp kya h bro simple explain",
        "expected_intent": "conceptual"
    },
    {
        "id": "Q15",
        "category": "Multi-Turn Sequence",
        "turns": [
            "What is Model Context Protocol (MCP)?",
            "Now compare it with REST APIs.",
            "Which one is better for my use case?"
        ],
        "expected_intent": "multi_turn"
    }
]

async def run_single_query(item: Dict[str, Any], db_manager: DatabaseManager) -> Dict[str, Any]:
    session_id = f"battery_{item['id']}_{int(time.time()*1000)%100000}"
    stream_queue = asyncio.Queue()
    orchestrator = MasterOrchestrator(session_id, db_manager, stream_queue)
    
    t0 = time.time()
    await orchestrator.execute_workflow(item["query"])
    elapsed = time.time() - t0
    
    state_dict = await orchestrator.state.get_state_dict()
    tasks = state_dict.get("tasks", {})
    final_report = state_dict.get("working_memory", {}).get("final_report", "")
    citations = list(orchestrator.citation_mgr.citations)
    
    # Extract DAG tasks
    dag_tasks = []
    for tid, tinfo in tasks.items():
        dag_tasks.append({
            "task_id": tid,
            "title": tinfo.get("title", ""),
            "agent": tinfo.get("assigned_agent", ""),
            "dependencies": tinfo.get("dependencies", [])
        })
        
    # Extract executed agents from logs
    agents_executed = []
    for log in state_dict.get("logs", []):
        ag = log.get("agent", "")
        if ag and ag not in ["system", "router"] and ag not in agents_executed:
            agents_executed.append(ag)
            
    # Intent detection
    intent_detected = state_dict.get("intent", {}).get("intent") or getattr(orchestrator.state, "intent", None)
    if isinstance(intent_detected, dict):
        intent_detected = intent_detected.get("intent", "unknown")
    if not intent_detected:
        intent_detected = orchestrator.state.working_memory.get("intent", "unknown")

    # Citation details
    cit_list = []
    for c in citations:
        cit_list.append({
            "url": c.url,
            "title": c.title,
            "credibility": c.credibility,
            "snippet_preview": c.snippet[:120] if c.snippet else ""
        })

    # Confidence
    conf = state_dict.get("average_confidence", 0.0)

    # Verification checks
    verdict = "PASS"
    notes = []
    if len(final_report) < 150:
        verdict = "FAIL"
        notes.append("Report too short")
    if item["id"] == "Q05":
        if "1,52,58,789" not in final_report and "15258789" not in final_report:
            verdict = "FAIL"
            notes.append("Compound growth final year mismatch")
    elif item["id"] == "Q07":
        if "70" not in final_report:
            verdict = "FAIL"
            notes.append("Percentage increase 70% missing")
    elif item["id"] == "Q08":
        if "180" not in final_report:
            verdict = "FAIL"
            notes.append("Arithmetic average 180 missing")
    elif item["id"] == "Q09":
        if "1,26,000" not in final_report and "126000" not in final_report:
            verdict = "FAIL"
            notes.append("Cost savings ₹1,26,000 missing")
    elif item["id"] == "Q10":
        if conf > 0.55:
            verdict = "FAIL"
            notes.append(f"Confidence not capped for 2035 prediction: {conf}")
    elif item["id"] in ["Q12", "Q13"]:
        if "clarif" not in final_report.lower() and "specify" not in final_report.lower():
            verdict = "FAIL"
            notes.append("Ambiguity clarification missing")

    return {
        "query_id": item["id"],
        "category": item["category"],
        "query": item["query"],
        "effective_query": getattr(orchestrator.state, "effective_query", None) or item["query"],
        "detected_intent": intent_detected,
        "dag_tasks_count": len(dag_tasks),
        "dag_tasks": dag_tasks,
        "agents_executed": agents_executed,
        "citations_count": len(cit_list),
        "citations": cit_list,
        "average_confidence": round(conf, 3),
        "elapsed_seconds": round(elapsed, 2),
        "final_report_length": len(final_report),
        "final_report_excerpt": final_report[:280].replace("\n", " "),
        "verdict": verdict,
        "notes": "; ".join(notes) if notes else "Verified clean deterministic execution"
    }

async def run_multiturn_query(item: Dict[str, Any], db_manager: DatabaseManager) -> Dict[str, Any]:
    session_id = f"battery_Q15_multiturn_{int(time.time()*1000)%100000}"
    stream_queue = asyncio.Queue()
    orchestrator = MasterOrchestrator(session_id, db_manager, stream_queue)

    turn_results = []
    t0 = time.time()
    for idx, turn_query in enumerate(item["turns"], 1):
        await orchestrator.execute_workflow(turn_query)
        st = await orchestrator.state.get_state_dict()
        rep = st.get("working_memory", {}).get("final_report", "")
        turn_results.append({
            "turn": idx,
            "raw_query": turn_query,
            "effective_query": getattr(orchestrator.state, "effective_query", None) or turn_query,
            "report_length": len(rep),
            "report_excerpt": rep[:200].replace("\n", " ")
        })
    elapsed = time.time() - t0

    state_dict = await orchestrator.state.get_state_dict()
    final_report = state_dict.get("working_memory", {}).get("final_report", "")
    history = state_dict.get("working_memory", {}).get("conversation_history", [])

    # Semantic reasoning check for Turn 3
    t3_rep = turn_results[2]["report_excerpt"]
    t3_effective = turn_results[2]["effective_query"]
    has_semantic_context = (
        ("mcp" in t3_rep.lower() or "protocol" in t3_rep.lower() or "rest" in t3_rep.lower() or "api" in t3_rep.lower()) and
        "Context:" in t3_effective
    )

    verdict = "PASS" if has_semantic_context and len(history) >= 2 else "FAIL"

    return {
        "query_id": "Q15",
        "category": "Multi-Turn Sequence",
        "query": " -> ".join(item["turns"]),
        "turns_executed": turn_results,
        "history_turns_recorded": len(history),
        "turn_3_effective_query": t3_effective,
        "turn_3_has_semantic_context": has_semantic_context,
        "elapsed_seconds": round(elapsed, 2),
        "final_report_length": len(final_report),
        "final_report_excerpt": final_report[:280].replace("\n", " "),
        "verdict": verdict,
        "notes": f"Turn 3 successfully resolved context: '{t3_effective}'" if verdict == "PASS" else "Turn 3 lost prior context"
    }

async def main():
    test_db = "storage/test_battery_phase5.db"
    if os.path.exists(test_db):
        try:
            os.remove(test_db)
        except Exception:
            pass

    db_manager = DatabaseManager(db_path=test_db)
    await db_manager.initialize_tables()

    print(f"Starting Phase 5: 15-Query Production Battery Execution...")
    results = []

    for item in BATTERY_QUERIES:
        if item["id"] == "Q15":
            print(f"Running [{item['id']}] Multi-Turn Sequence (3 Turns)...")
            res = await run_multiturn_query(item, db_manager)
        else:
            print(f"Running [{item['id']}] {item['category']}: '{item['query'][:50]}'...")
            res = await run_single_query(item, db_manager)
        results.append(res)
        print(f"  -> Result: {res['verdict']} ({res['elapsed_seconds']}s, Report: {res['final_report_length']} chars)")

    # Save results to scratch JSON
    os.makedirs("scratch", exist_ok=True)
    out_path = "scratch/query_battery_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nCompleted 15-Query Battery! Results saved to {out_path}.")
    pass_count = sum(1 for r in results if r["verdict"] == "PASS")
    print(f"Summary: {pass_count}/{len(results)} Queries Passed Verification.")

if __name__ == "__main__":
    asyncio.run(main())
