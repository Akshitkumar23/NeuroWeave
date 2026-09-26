'''
test_deep_pipeline.py
Comprehensive End-to-End Verification Test Suite for NeuroWeave Multi-Agent Research & Synthesis Engine.

Tests the full orchestration pipeline across 8 diverse, real-world user queries:
- Query 1: 'Compare Supabase vs Firebase for real-time web apps with latency, pricing, and self-hosting trade-offs'
- Query 2: 'Compare Next.js vs Remix vs SvelteKit for enterprise web applications'
- Query 3: 'How to build an automated algorithmic trading bot in Python with risk management'
- Query 4: 'Calculate nanoGPT parameter sizing, KV-cache VRAM footprint for 128k context, and FlashAttention MFU'
- Query 5: 'Series A Cap Table valuation model with 20% option pool and founder dilution'
- Query 6: 'PostgreSQL TimescaleDB vs MongoDB TimeSeries for 50k events/sec IoT telemetry'
- Query 7: 'Best mechanical keyboards under 4000 in India with hot-swappable switches'
- Query 8: 'Design a microservices architecture for high-concurrency payment gateway with idempotency'
'''

import os
import sys
import asyncio
import re
import json
import logging
from typing import Dict, Any, List

# Force UTF-8 on standard outputs to avoid Windows cp1252 UnicodeEncodeError
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage.database import DatabaseManager
from agents.orchestrator import MasterOrchestrator
from core.model_router import ModelRouter

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("neuroweave.test_deep_pipeline")

BANNED_FILLER_PHRASES = [
    "Tier-1 Benchmark",
    "Tier-2 Benchmark",
    "Option 1 Core",
    "Option 2 Alternative",
    "Scalable Modular Architecture",
    "Strategic Market & Technology Intelligence"
]

TEST_CASES = [
    {
        "id": "QUERY-1",
        "title": "Backend / BaaS Comparison (Supabase vs Firebase)",
        "query": "Compare Supabase vs Firebase for real-time web apps with latency, pricing, and self-hosting trade-offs",
        "division": "engineering",
        "required_entities": ["Supabase", "Firebase", "PostgreSQL", "Realtime", "Pricing", "Self-Hosting"],
        "min_report_length": 4000
    },
    {
        "id": "QUERY-2",
        "title": "Enterprise Web Frameworks (Next.js vs Remix vs SvelteKit)",
        "query": "Compare Next.js vs Remix vs SvelteKit for enterprise web applications",
        "division": "engineering",
        "required_entities": ["Next.js", "Remix", "SvelteKit", "SSR", "Bundle", "React"],
        "min_report_length": 4000
    },
    {
        "id": "QUERY-3",
        "title": "Algorithmic Trading Bot & Risk Management",
        "query": "How to build an automated algorithmic trading bot in Python with risk management",
        "division": "finance",
        "required_entities": ["Python", "Trading", "Risk", "Stop", "Drawdown", "ATR"],
        "min_report_length": 4000
    },
    {
        "id": "QUERY-4",
        "title": "nanoGPT Parameter Sizing, 128k KV-Cache & MFU",
        "query": "Calculate nanoGPT parameter sizing, KV-cache VRAM footprint for 128k context, and FlashAttention MFU",
        "division": "engineering",
        "required_entities": ["nanoGPT", "KV-Cache", "VRAM", "FlashAttention", "MFU", "Parameter"],
        "min_report_length": 4000
    },
    {
        "id": "QUERY-5",
        "title": "Series A Cap Table & 20% Option Pool Dilution",
        "query": "Series A Cap Table valuation model with 20% option pool and founder dilution",
        "division": "finance",
        "required_entities": ["Cap Table", "Valuation", "Series A", "Option Pool", "Dilution", "Founder"],
        "min_report_length": 4000
    },
    {
        "id": "QUERY-6",
        "title": "Time-Series IoT Telemetry (TimescaleDB vs MongoDB)",
        "query": "PostgreSQL TimescaleDB vs MongoDB TimeSeries for 50k events/sec IoT telemetry",
        "division": "engineering",
        "required_entities": ["PostgreSQL", "TimescaleDB", "MongoDB", "TimeSeries", "IoT", "Telemetry"],
        "min_report_length": 4000
    },
    {
        "id": "QUERY-7",
        "title": "Mechanical Keyboards Under 4000 in India",
        "query": "Best mechanical keyboards under 4000 in India with hot-swappable switches",
        "division": "product",
        "required_entities": ["Mechanical", "Keyboard", "Hot-Swappable", "Switch", "India", "Redragon"],
        "min_report_length": 4000
    },
    {
        "id": "QUERY-8",
        "title": "High-Concurrency Payment Gateway Microservices",
        "query": "Design a microservices architecture for high-concurrency payment gateway with idempotency",
        "division": "engineering",
        "required_entities": ["Microservices", "Payment", "Gateway", "Idempotency", "Concurrency", "Saga"],
        "min_report_length": 4000
    }
]


async def run_single_test(test_case: Dict[str, Any], db_mgr: DatabaseManager) -> Dict[str, Any]:
    test_id = test_case["id"]
    title = test_case["title"]
    query = test_case["query"]
    division = test_case["division"]
    required_entities = test_case["required_entities"]
    min_len = test_case.get("min_report_length", 4000)
    
    print("\n" + "=" * 80)
    print(f">> EXECUTING {test_id}: {title}")
    print(f"   Query: '{query}'")
    print("=" * 80)
    
    session_id = f"test_{test_id.lower().replace('-', '_')}_{int(asyncio.get_event_loop().time() * 1000)}"
    orchestrator = MasterOrchestrator(session_id=session_id, db_manager=db_mgr)
    
    start_time = asyncio.get_event_loop().time()
    await orchestrator.execute_workflow(query=query, division=division)
    duration = asyncio.get_event_loop().time() - start_time
    
    state_dict = await orchestrator.state.get_state_dict()
    final_report = orchestrator.state.working_memory.get("final_report", "")
    tasks = state_dict.get("tasks", {})
    confidence_history = state_dict.get("confidence_history", [])
    
    assertions = {}
    
    # 1. Report existence and length check (> 4,000 characters)
    has_valid_length = len(final_report) >= min_len
    assertions["Report Length >= 4,000 Chars"] = {
        "passed": has_valid_length,
        "detail": f"Report length: {len(final_report)} chars (min required: {min_len})"
    }
    
    # 2. Check for required named entities
    missing_entities = []
    for ent in required_entities:
        if not re.search(r'\b' + re.escape(ent) + r'\b', final_report, re.IGNORECASE):
            if ent.lower() not in final_report.lower():
                missing_entities.append(ent)
                
    assertions["Required Named Entities Present"] = {
        "passed": len(missing_entities) == 0,
        "detail": f"Missing: {missing_entities}" if missing_entities else f"All {len(required_entities)} entities verified"
    }
    
    # 3. Check for absence of banned generic filler phrases
    found_banned = []
    for banned in BANNED_FILLER_PHRASES:
        if banned.lower() in final_report.lower():
            found_banned.append(banned)
            
    assertions["Zero Generic Filler Phrases"] = {
        "passed": len(found_banned) == 0,
        "detail": f"Violations found: {found_banned}" if found_banned else "Clean: 0 generic placeholders found"
    }
    
    # 4. Check for Markdown Comparison Tables
    has_table = bool(re.search(r'\|.*?\|.*?\|\n\|(?:\s*:?-+:?\s*\|)+\n\|.*?\|', final_report))
    assertions["Comparison Tables Present"] = {
        "passed": has_table,
        "detail": "Structured Markdown Comparison Table verified" if has_table else "No Markdown Table found"
    }
    
    # 5. Check for Chart.js Visualization Block and valid JSON
    chart_matches = re.findall(r'```json\s+chart\s*\n(.*?)\n```', final_report, re.DOTALL)
    valid_chart_json = False
    chart_detail = "Missing Chart.js block"
    if chart_matches:
        try:
            parsed_chart = json.loads(chart_matches[0].strip())
            if isinstance(parsed_chart, dict) and "type" in parsed_chart and "data" in parsed_chart:
                valid_chart_json = True
                chart_detail = f"Valid Chart.js JSON (type='{parsed_chart['type']}', datasets={len(parsed_chart['data'].get('datasets', []))})"
            else:
                chart_detail = "Chart JSON missing 'type' or 'data' field"
        except Exception as e:
            chart_detail = f"Chart JSON parse error: {e}"
            
    assertions["Chart.js JSON Valid"] = {
        "passed": valid_chart_json,
        "detail": chart_detail
    }
    
    # 6. Check for APA Citations in Text and Bibliography
    has_inline_citations = bool(re.search(r'\[\^\d+\]', final_report))
    has_biblio_section = "## Sources & Evidence Citations" in final_report or "## References" in final_report or "[^1]:" in final_report
    assertions["APA Citations & Bibliography Present"] = {
        "passed": has_inline_citations and has_biblio_section,
        "detail": f"Inline citations: {has_inline_citations}, Bibliography: {has_biblio_section}"
    }

    # 7. Check Code Blocks Formatted
    code_blocks = re.findall(r'```([a-zA-Z0-9_-]+)?\n.*?\n```', final_report, re.DOTALL)
    has_code_blocks = len(code_blocks) > 0
    assertions["Code / Blueprint Blocks Present"] = {
        "passed": has_code_blocks,
        "detail": f"{len(code_blocks)} code/spec block(s) detected and verified"
    }
    
    # 8. Check All DAG Subtasks Complete Successfully
    task_count = len(tasks)
    all_tasks_completed = task_count >= 2 and all(
        isinstance(t, dict) and t.get("status") in ["completed", "success"]
        for t in tasks.values()
    )
    assertions["All DAG Subtasks Completed"] = {
        "passed": all_tasks_completed,
        "detail": f"{task_count} subtasks executed and completed in DAG"
    }
    
    # Compute overall status
    all_passed = all(a["passed"] for a in assertions.values())
    
    print("\n--- TEST ASSERTION RESULTS ---")
    for k, v in assertions.items():
        icon = "[PASS]" if v["passed"] else "[FAIL]"
        print(f"  {icon} | {k}: {v['detail']}")
        
    print(f"\nExecution Duration: {duration:.2f}s | Confidence Score: {sum(confidence_history)/max(len(confidence_history),1):.2f}")
    print(f"Report Length: {len(final_report)} characters")
    
    return {
        "test_id": test_id,
        "title": title,
        "query": query,
        "status_code": 200,
        "passed": all_passed,
        "duration": duration,
        "report_length": len(final_report),
        "task_count": task_count,
        "assertions": assertions,
        "final_report": final_report
    }


async def main():
    print("=" * 80)
    print("NEUROWEAVE MULTI-AGENT COMPREHENSIVE END-TO-END STRESS TEST SUITE (8 QUERIES)")
    print("=" * 80)
    
    db_mgr = DatabaseManager()
    await db_mgr.initialize_tables()
    
    results = []
    for tc in TEST_CASES:
        res = await run_single_test(tc, db_mgr)
        results.append(res)
        
    print("\n" + "=" * 80)
    print("OVERALL TEST SCORECARD & SUMMARY")
    print("=" * 80)
    
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r["passed"])
    
    print(f"\n| Query ID | Domain / Title | Status | Duration | Report Size | Subtasks | Chart Valid | Result |")
    print(f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for r in results:
        status_str = "PASSED" if r["passed"] else "FAILED"
        chart_ok = "YES" if r["assertions"]["Chart.js JSON Valid"]["passed"] else "NO"
        print(f"| **{r['test_id']}** | {r['title']} | 200 OK | {r['duration']:.2f}s | {r['report_length']} chars | {r['task_count']} | {chart_ok} | **{status_str}** |")
        
    print(f"\nTotal Queries Tested: {total_tests} | Passed: {passed_tests} | Failed: {total_tests - passed_tests}")
    
    # Write results to test log files
    log_json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_stress_suite_results.json")
    log_txt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_stress_suite.log")
    
    with open(log_json_path, "w", encoding="utf-8") as f:
        # Save JSON without huge final_report string for readability
        clean_results = []
        for r in results:
            item = dict(r)
            item["final_report_snippet"] = item["final_report"][:400] + "..."
            del item["final_report"]
            clean_results.append(item)
        json.dump(clean_results, f, indent=2)
        
    with open(log_txt_path, "w", encoding="utf-8") as f:
        f.write("NEUROWEAVE END-TO-END COMPREHENSIVE STRESS TEST SUITE LOG\n")
        f.write("=" * 80 + "\n\n")
        for r in results:
            f.write(f"[{r['test_id']}] {r['title']}\n")
            f.write(f"Query: {r['query']}\n")
            f.write(f"Status: 200 OK | Duration: {r['duration']:.2f}s | Report Length: {r['report_length']} chars\n")
            f.write("Assertions:\n")
            for k, v in r["assertions"].items():
                icon = "[PASS]" if v["passed"] else "[FAIL]"
                f.write(f"  {icon} {k}: {v['detail']}\n")
            f.write("-" * 80 + "\n\n")
            
    print(f"\n[INFO] Test results successfully written to:\n  - {log_json_path}\n  - {log_txt_path}\n")
    
    if passed_tests == total_tests:
        print("ALL 8 DIVERSE REAL-WORLD STRESS TEST QUERIES PASSED WITH 100% SUCCESS!\n")
        return 0
    else:
        print("SOME ASSERTIONS FAILED. REVIEW DETAILS ABOVE.\n")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

