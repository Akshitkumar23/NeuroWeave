import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath("."))

from core.deterministic_engine import (
    detect_query_intent,
    plan_dag,
    is_unanswerable,
    extract_calculation_params,
    execute_calculation,
    resolve_contradictions,
    evaluate_claims_deterministically,
    score_source_relevance,
    filter_relevant_sources
)

def run_tests():
    print("=== RUNNING NEUROWEAVE SEMANTIC AUDIT TESTS ===\n")
    
    # -------------------------------------------------------------
    # TEST 1: Supabase vs Firebase DAG Planning (Intent & Tasks)
    # -------------------------------------------------------------
    q1 = "Compare Supabase and Firebase for a production SaaS startup in 2026. Analyze pricing, database capabilities, authentication, scalability, and security."
    intent1 = detect_query_intent(q1)
    dag1 = plan_dag(q1, intent1)
    
    assert intent1 == "comparison", f"Expected comparison intent, got {intent1}"
    task_agents1 = [t["assigned_agent"] for t in dag1["tasks"]]
    assert "researcher" in task_agents1, "Researcher task missing"
    assert "analyzer" in task_agents1, "Analyzer task missing"
    assert "critic" in task_agents1, "Critic task missing"
    assert "synthesizer" in task_agents1, "Synthesizer task missing"
    
    research_titles = [t["title"] for t in dag1["tasks"] if t["assigned_agent"] == "researcher"]
    assert len(research_titles) >= 2, f"Expected multiple domain research tasks, got {len(research_titles)}"
    print("✓ Test 1 Passed: Comparison DAG dynamically planned across real feature dimensions.")

    # -------------------------------------------------------------
    # TEST 2: Revenue Compound Growth - Exact Math & No Latency Benchmark
    # -------------------------------------------------------------
    q2 = "If a startup has Rs 50 lakh annual revenue and grows 25% annually for 5 years, calculate the projected revenue each year and total cumulative growth."
    intent2 = detect_query_intent(q2)
    assert intent2 == "quantitative", f"Expected quantitative intent, got {intent2}"
    
    calc_params = extract_calculation_params(q2, "")
    assert calc_params is not None, "Failed to extract compound growth calculation params"
    assert calc_params["type"] == "compound_growth", f"Expected compound_growth, got {calc_params['type']}"
    assert calc_params["inputs"]["principal"] == 5000000.0, f"Expected 5,000,000 principal, got {calc_params['inputs']['principal']}"
    assert calc_params["inputs"]["annual_growth_rate_pct"] == 25.0
    assert calc_params["inputs"]["periods_years"] == 5
    
    res = execute_calculation(calc_params)
    assert res["success"] is True, f"Calculation execution failed: {res.get('error')}"
    metrics = res["metrics"]
    
    assert metrics["year_0_revenue"] == 5000000.0
    assert metrics["year_1_revenue"] == 6250000.0
    assert abs(metrics["year_5_revenue"] - 15258789.06) < 1.0, f"Expected ~15258789.06, got {metrics['year_5_revenue']}"
    assert "p95" not in str(res["code"]), "Latency benchmark code was incorrectly generated for financial query!"
    print("✓ Test 2 Passed: Quantitative revenue compounding calculated with 100% mathematical precision.")

    # -------------------------------------------------------------
    # TEST 3: Impossible 2035 Prediction - Explicit Uncertainty Capping
    # -------------------------------------------------------------
    q3 = "Predict exactly which AI startup will become India market leader in 2035."
    intent3 = detect_query_intent(q3)
    assert intent3 == "prediction_uncertain"
    assert is_unanswerable(q3) is True, "System failed to detect inherently uncertain future prediction query"
    
    dag3 = plan_dag(q3, intent3)
    task_titles3 = [t["title"] for t in dag3["tasks"]]
    assert any("Uncertainty" in title for title in task_titles3), "Uncertainty assessment task missing from prediction DAG"
    
    dummy_claims = [{"claim": "Company X will lead India in 2035", "source": "Speculative Blog", "url": "", "relevance": 0.4}]
    verdicts, conf = evaluate_claims_deterministically(dummy_claims, [{"title": "Blog", "snippet": "Text", "url": ""}], q3, is_uncertain_query=True)
    assert conf <= 0.45, f"Confidence for unanswerable query must be capped <= 0.45, got {conf}"
    print("✓ Test 3 Passed: 2035 prediction recognized as unanswerable; uncertainty bounds enforced.")

    # -------------------------------------------------------------
    # TEST 4: Conflicting Evidence - Real Contradiction & Quarantining
    # -------------------------------------------------------------
    conflicting_claims = [
        {"claim": "Supabase Pro plan pricing is $25 per month.", "source": "Pricing Docs", "url": "https://supabase.com/pricing", "relevance": 0.8},
        {"claim": "Supabase Pro plan pricing is $50 per month.", "source": "Third-Party Review", "url": "https://review.com", "relevance": 0.5}
    ]
    verdicts, conf = evaluate_claims_deterministically(conflicting_claims, [{"title": "Supabase Pricing", "snippet": "Pricing is $25 or $50", "url": "https://supabase.com"}], "Supabase pricing")
    
    rejected = [v for v in verdicts if v["verdict"] == "REJECTED"]
    assert len(rejected) >= 2, f"Expected conflicting claims to be flagged as REJECTED, got {rejected}"
    
    debate_res = resolve_contradictions(conflicting_claims, verdicts, "Supabase pricing", is_uncertain_query=False)
    assert len(debate_res["rejected_claims"]) >= 2, "Rejected claims were not quarantined during debate"
    assert "H100" not in debate_res["consensus"], "Mock H100 debate text leaked into pricing debate!"
    print("✓ Test 4 Passed: Numerical contradiction flagged and conflicting claims quarantined.")

    # -------------------------------------------------------------
    # TEST 5: Irrelevant Search Results Filtered Out (No Fabricated Citations)
    # -------------------------------------------------------------
    mock_sources = [
        {"title": "Patrick Bet-David - Wikipedia", "snippet": "Patrick Bet-David is an American entrepreneur...", "url": "https://en.wikipedia.org/wiki/PBD"},
        {"title": "Miller columns - Wikipedia", "snippet": "Miller columns are a navigational technique...", "url": "https://en.wikipedia.org/wiki/Miller_columns"},
        {"title": "Supabase Official Documentation", "snippet": "Supabase provides managed PostgreSQL with Row Level Security...", "url": "https://supabase.com/docs"}
    ]
    topic = "Supabase vs Firebase"
    relevant, filtered = filter_relevant_sources(mock_sources, "Compare Supabase and Firebase", topic, min_relevance=0.15)
    
    assert any("Supabase" in s["title"] for s in relevant), "Relevant Supabase doc was dropped"
    assert not any("Miller columns" in s["title"] for s in relevant), "Irrelevant Miller columns was not filtered out"
    assert not any("Patrick Bet-David" in s["title"] for s in relevant), "Irrelevant Patrick Bet-David was not filtered out"
    print("✓ Test 5 Passed: Off-topic sources successfully filtered; phantom citations prevented.")

    # -------------------------------------------------------------
    # TEST 6: Query Requiring No Research Skips Unnecessary Tasks
    # -------------------------------------------------------------
    pure_calc_query = "Calculate 15% compound interest on Rs 100000 for 3 years"
    dag_calc = plan_dag(pure_calc_query, detect_query_intent(pure_calc_query))
    agents_calc = [t["assigned_agent"] for t in dag_calc["tasks"]]
    assert "researcher" not in agents_calc, "Pure calculation query should not spawn web research tasks"
    print("✓ Test 6 Passed: Web research skipped when query is strictly computational.")

    # -------------------------------------------------------------
    # TEST 7: Query Requiring No Calculation Skips Analyzer In Fallback
    # -------------------------------------------------------------
    pure_research_query = "What is the history and architecture overview of the Raft consensus algorithm?"
    calc_check = extract_calculation_params(pure_research_query, "")
    assert calc_check is None, "Non-quantitative query should not generate calculation parameters"
    print("✓ Test 7 Passed: Quantitative calculations correctly skipped for conceptual queries.")

    # -------------------------------------------------------------
    # TEST 8: Honest Deterministic Mode (No Fake H100 LLM Hallucination)
    # -------------------------------------------------------------
    res_debate = resolve_contradictions([], [], "Compare Redis and Postgres")
    assert "H100" not in res_debate["consensus"], "H100 GPU text detected in generic debate!"
    assert "FP8" not in res_debate["consensus"], "FP8 text detected in generic debate!"
    print("✓ Test 8 Passed: Debate consensus reflects actual evidence without fabricated LLM text.")

    # -------------------------------------------------------------
    # TEST 9: Conceptual Query Intent & DAG Planning (Query D)
    # -------------------------------------------------------------
    q4 = "What is MCP and how is it different from an API?"
    intent4 = detect_query_intent(q4)
    assert intent4 in ("conceptual", "conceptual_comparison"), f"Expected conceptual intent, got {intent4}"
    dag4 = plan_dag(q4, intent4)
    dag4_agents = [t["assigned_agent"] for t in dag4["tasks"]]
    assert "researcher" in dag4_agents, "Researcher missing from conceptual DAG"
    assert "analyzer" in dag4_agents, "Analyzer missing from conceptual DAG"
    assert "critic" in dag4_agents, "Critic missing from conceptual DAG"
    assert "synthesizer" in dag4_agents, "Synthesizer missing from conceptual DAG"
    print("✓ Test 9 Passed: Conceptual query (MCP vs API) correctly classified and planned.")

    # -------------------------------------------------------------
    # TEST 10: Strict Computational Report Generation (Query B)
    # -------------------------------------------------------------
    from core.deterministic_engine import build_computational_report
    comp_report = build_computational_report(q2, calc_params, res["metrics"])
    assert "FV = PV" in comp_report, "Missing formula in computational report"
    assert "50,00,000" in comp_report or "5,000,000" in comp_report, "Missing principal in computational report"
    assert "1,52,58,789.06" in comp_report, "Missing Year 5 revenue in computational report"
    assert "1,02,58,789.06" in comp_report, "Missing net expansion in computational report"
    assert "5,12,93,945.31" in comp_report, "Missing cumulative operational revenue in computational report"
    assert "radar" not in comp_report.lower(), "Radar chart incorrectly found in pure math report!"
    assert "supabase" not in comp_report.lower(), "Supabase leaked into financial report!"
    print("✓ Test 10 Passed: Pure computational report formats math, tables, and dual cumulative interpretations.")

    # -------------------------------------------------------------
    # TEST 11: Geographic & Topical Relevance Filtering (Query C)
    # -------------------------------------------------------------
    q_india = "Predict exactly which AI startup will become India's market leader in 2035."
    off_topic_sources = [
        {"title": "Thaksin Shinawatra - Wikipedia", "snippet": "Thaksin Shinawatra is a Thai businessman and politician...", "url": "https://en.wikipedia.org/wiki/Thaksin"},
        {"title": "Climate of Australia - Wikipedia", "snippet": "The climate of Australia is significantly determined by...", "url": "https://en.wikipedia.org/wiki/Climate_of_Australia"},
        {"title": "Sarvam AI: Indic LLMs and Sovereign AI in India", "snippet": "Sarvam AI is developing foundational AI models in India with $41M funding.", "url": "https://techcrunch.com/sarvam-ai-india"}
    ]
    rel_india, filt_india = filter_relevant_sources(off_topic_sources, q_india, q_india, min_relevance=0.20)
    assert len(rel_india) == 1, f"Expected exactly 1 relevant source, got {len(rel_india)}"
    assert "Sarvam" in rel_india[0]["title"], "Sarvam AI was not retained as relevant source"
    assert not any("Thaksin" in s["title"] for s in rel_india), "Thaksin Shinawatra was not filtered out"
    assert not any("Australia" in s["title"] for s in rel_india), "Climate of Australia was not filtered out"
    print("✓ Test 11 Passed: Geographic and topical filters strictly reject off-topic international entries.")

    # -------------------------------------------------------------
    # TEST 12: CitationManager Strictly Rejects Fabricated URLs
    # -------------------------------------------------------------
    from utils.citation_manager import CitationManager
    cm = CitationManager()
    res1 = cm.add_source("https://db-engines.com/en/system/supabase-and-firebase-for-production", "snippet", "Title")
    assert res1 is None, "Synthetic db-engines URL was not rejected by CitationManager!"
    res2 = cm.add_source("https://arxiv.org/abs/nanogpt-kvcache-scaling", "snippet", "Title")
    assert res2 is None, "Synthetic arxiv URL was not rejected by CitationManager!"
    res3 = cm.add_source("https://supabase.com/docs", "Official documentation", "Supabase Docs")
    assert res3 == 1, "Legitimate documentation URL was rejected by CitationManager!"
    print("✓ Test 12 Passed: CitationManager validates and quarantines synthetic/fabricated URLs.")

    print("\n========================================================")
    print("ALL 12 SEMANTIC ROOT-CAUSE TESTS PASSED SUCCESSFULLY! 🎯")
    print("========================================================")

if __name__ == "__main__":
    run_tests()
