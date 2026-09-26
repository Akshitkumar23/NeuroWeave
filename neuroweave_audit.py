"""
neuroweave_audit.py
Real-output audit: runs 3 real queries through the NeuroWeave pipeline
and inspects actual data at every stage without accepting logs as proof.
"""
import os, sys, asyncio, json, re, textwrap, time
from typing import Dict, Any

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage.database import DatabaseManager
from core.model_router import ModelRouter
from agents.orchestrator import MasterOrchestrator

# ─── helpers ────────────────────────────────────────────────────────────────

def hr(label=""):
    w = 80
    if label:
        pad = (w - len(label) - 2) // 2
        print("\n" + "─" * pad + f" {label} " + "─" * pad)
    else:
        print("\n" + "─" * w)

def jdump(obj, indent=2):
    try:
        return json.dumps(obj, indent=indent, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)

def truncate(s, n=600):
    s = str(s)
    return s if len(s) <= n else s[:n] + f"\n... [TRUNCATED — {len(s)} chars total]"

# ─── single run ─────────────────────────────────────────────────────────────

async def run_query(query: str, division: str = "auto") -> Dict[str, Any]:
    db = DatabaseManager()
    await db.initialize()
    router = ModelRouter()
    orch = MasterOrchestrator(db_manager=db, model_router=router)
    t0 = time.monotonic()
    result = await orch.execute_research(query=query, session_id=None, division=division)
    elapsed = time.monotonic() - t0
    result["_elapsed_sec"] = round(elapsed, 2)
    return result

# ─── inspection helpers ──────────────────────────────────────────────────────

def inspect_pipeline(result: Dict, label: str):
    state = result.get("state", {})
    tasks = state.get("tasks", {})
    traces = state.get("traces", [])
    logs   = state.get("logs", [])
    wm     = state.get("working_memory", {})
    report = wm.get("final_report", "") or ""

    hr(f"PIPELINE AUDIT — {label}")
    print(f"Elapsed: {result.get('_elapsed_sec')}s")
    print(f"Session: {state.get('session_id','?')}")
    print(f"Persona: {state.get('assigned_persona','—')}")
    print(f"Avg Confidence: {state.get('average_confidence', '?')}")
    print(f"Report length: {len(report)} chars")
    print(f"Tasks in DAG: {len(tasks)}")
    print(f"Traces: {len(traces)}")
    print(f"Logs: {len(logs)}")

    # ── 1. DAG composition ───────────────────────────────────────────────
    hr("1. DAG TASK BREAKDOWN (actual task objects)")
    for tid, t in tasks.items():
        print(f"\n  [{tid}] {t.get('title','?')}")
        print(f"       agent: {t.get('assigned_agent','?')}  status: {t.get('status','?')}")
        print(f"       deps:  {t.get('dependencies','[]')}")
        desc = t.get('description','')
        print(f"       desc:  {truncate(desc, 180)}")
        tdata = t.get('data', {})
        if tdata:
            print(f"       data_keys: {list(tdata.keys())}")

    # ── 2. Stage data-flow ──────────────────────────────────────────────
    hr("2. STAGE DATA FLOW (output of each stage → consumed by next)")
    stage_names = ["intent", "planner", "researcher", "analyzer", "memory", "critic", "debate_engine", "synthesizer"]
    for t in traces:
        agent = t.get("agent") or t.get("name","?")
        dur   = t.get("duration_sec","?")
        ok    = t.get("success","?")
        print(f"  [{agent:20s}]  duration={dur}s  success={ok}")

    # ── 3. Research claims & citations ──────────────────────────────────
    hr("3. RESEARCH: claims & citations")
    synced_claims = wm.get("synced_claims", [])
    print(f"  synced_claims count: {len(synced_claims)}")
    for i, cl in enumerate(synced_claims[:8]):
        print(f"\n  Claim [{i+1}]: {truncate(cl.get('claim','(no claim text)'), 200)}")
        print(f"           source: {cl.get('source','—')}")
        print(f"           citation_id: {cl.get('citation_id','—')}")
        print(f"           support: {cl.get('support','—')}")

    # also inspect task-level researcher data
    for tid, t in tasks.items():
        if t.get("assigned_agent") == "researcher":
            tdata = t.get("data", {})
            raw_claims = tdata.get("claims", [])
            print(f"\n  Task {tid} researcher raw claims: {len(raw_claims)}")
            for rc in raw_claims[:5]:
                print(f"    - {truncate(str(rc), 200)}")

    # ── 4. Critic verdicts ──────────────────────────────────────────────
    hr("4. CRITIC: claim_verdicts (actual pydantic output)")
    supported = challenged = rejected = 0
    for tid, t in tasks.items():
        if t.get("assigned_agent") == "critic":
            tdata = t.get("data", {})
            verdicts = tdata.get("claim_verdicts", [])
            for v in verdicts:
                verdict_val = v.get("verdict","?").upper()
                if verdict_val == "SUPPORTED":   supported  += 1
                elif verdict_val == "CHALLENGED": challenged += 1
                elif verdict_val == "REJECTED":   rejected   += 1
            print(f"\n  Task {tid} critic claim_verdicts:")
            for v in verdicts[:8]:
                print(f"    [{v.get('verdict','?'):12s}] {truncate(v.get('claim','?'), 140)}")
                print(f"               reason: {truncate(v.get('reason','—'), 100)}")

    print(f"\n  CRITIC VERDICT TALLY: SUPPORTED={supported}  CHALLENGED={challenged}  REJECTED={rejected}")
    if supported > 0 and challenged == 0 and rejected == 0:
        print("  ⚠ WARNING: Everything is SUPPORTED — critic may be auto-approving all claims.")

    # ── 5. Debate output ────────────────────────────────────────────────
    hr("5. DEBATE ENGINE: contradictions, resolutions, rejected claims")
    debate_wm = wm.get("debate_result", {})
    print(f"  consensus_score: {debate_wm.get('consensus_score','—')}")
    resolutions = debate_wm.get("claim_resolutions", [])
    print(f"  claim_resolutions: {len(resolutions)}")
    for r in resolutions[:5]:
        print(f"    claim: {truncate(r.get('claim','?'), 120)}")
        print(f"    resolution: {r.get('resolution','?')}")
    rejected_claims = wm.get("rejected_claims", [])
    print(f"\n  rejected_claims (quarantined from synthesis): {len(rejected_claims)}")
    for rc in rejected_claims[:5]:
        print(f"    - {truncate(rc, 120)}")

    # ── 6. Quantitative analysis ─────────────────────────────────────────
    hr("6. QUANTITATIVE ANALYSIS: sandbox metrics")
    synced_metrics = wm.get("synced_metrics", {})
    print(f"  synced_metrics: {jdump(synced_metrics)[:800]}")
    for tid, t in tasks.items():
        if t.get("assigned_agent") == "analyzer":
            tdata = t.get("data", {})
            print(f"\n  Task {tid} analyzer data:")
            print(f"    formula_used:    {tdata.get('formula_used','—')}")
            print(f"    execution_status:{tdata.get('execution_status','—')}")
            print(f"    calculated_metrics: {jdump(tdata.get('calculated_metrics',{}))[:400]}")
            print(f"    result_snippet:  {truncate(tdata.get('result',''), 300)}")

    # ── 7. Final report structure ────────────────────────────────────────
    hr("7. FINAL REPORT (first 2000 chars)")
    print(truncate(report, 2000))

    # Check for required sections
    required_sections = [
        "executive summary", "key findings", "comparison", "pricing", "risk",
        "recommendation", "source", "citation"
    ]
    report_lower = report.lower()
    print("\n  Required sections check:")
    for sec in required_sections:
        found = sec in report_lower
        print(f"    {'✓' if found else '✗'} {sec}")

    # ── 8. Citation quality ──────────────────────────────────────────────
    hr("8. CITATIONS: inline refs vs bibliography")
    inline_refs = re.findall(r'\[\^(\d+)\]', report)
    bib_entries = re.findall(r'\[\^(\d+)\]:\s*(.+)', report)
    print(f"  Inline citation refs: {sorted(set(int(x) for x in inline_refs))}")
    print(f"  Bibliography entries: {len(bib_entries)}")
    for num, content in bib_entries[:10]:
        print(f"    [^{num}] {truncate(content, 120)}")
    dangling = set(int(x) for x in inline_refs) - set(int(x[0]) for x in bib_entries)
    if dangling:
        print(f"  ⚠ DANGLING refs (cited but no bib entry): {sorted(dangling)}")

    # ── 9. Confidence ────────────────────────────────────────────────────
    hr("9. CONFIDENCE SCORE BREAKDOWN")
    conf_breakdown = state.get("confidence_breakdown", {})
    print(f"  Final average_confidence: {state.get('average_confidence','?')}")
    print(f"  Breakdown: {jdump(conf_breakdown)}")

    return {
        "report_len": len(report),
        "task_count": len(tasks),
        "confidence": state.get("average_confidence", 0),
        "supported": supported,
        "challenged": challenged,
        "rejected": rejected,
        "citations": len(bib_entries),
        "inline_refs": len(set(inline_refs)),
        "synced_claims": len(synced_claims),
        "rejected_claims": len(rejected_claims),
        "synced_metrics": bool(synced_metrics),
    }

# ─── main ────────────────────────────────────────────────────────────────────

async def main():
    QUERY_A = (
        "Compare Supabase and Firebase for a production SaaS startup in 2026. "
        "Analyze pricing, database capabilities, authentication, scalability, "
        "developer experience, vendor lock-in, security, and recommend which one "
        "I should choose for a startup."
    )
    QUERY_B = (
        "If a startup has ₹50 lakh annual revenue and grows 25% annually for 5 years, "
        "calculate the projected revenue each year and total growth."
    )
    QUERY_C = (
        "Predict exactly which AI startup will become India's market leader in 2035."
    )

    summaries = {}

    hr("RUNNING QUERY A — Market/Comparison")
    print(f"Query: {QUERY_A}")
    result_a = await run_query(QUERY_A, division="engineering")
    summaries["A"] = inspect_pipeline(result_a, "QUERY A — Supabase vs Firebase")

    hr("RUNNING QUERY B — Quantitative")
    print(f"Query: {QUERY_B}")
    result_b = await run_query(QUERY_B, division="finance")
    summaries["B"] = inspect_pipeline(result_b, "QUERY B — Revenue Projection")

    hr("RUNNING QUERY C — Weak Evidence / Uncertain Prediction")
    print(f"Query: {QUERY_C}")
    result_c = await run_query(QUERY_C, division="strategy")
    summaries["C"] = inspect_pipeline(result_c, "QUERY C — AI India 2035 Prediction")

    # ─ Final comparison table ─────────────────────────────────────────────
    hr("FINAL COMPARISON ACROSS QUERIES")
    print(f"\n{'Metric':35s}  {'Query A':>10}  {'Query B':>10}  {'Query C':>10}")
    print("─" * 70)
    metrics = ["confidence","report_len","task_count","citations","synced_claims",
               "supported","challenged","rejected","rejected_claims","synced_metrics"]
    for m in metrics:
        va = summaries["A"].get(m,"?")
        vb = summaries["B"].get(m,"?")
        vc = summaries["C"].get(m,"?")
        print(f"  {m:33s}  {str(va):>10}  {str(vb):>10}  {str(vc):>10}")

    # ─ Zero-API mode check ───────────────────────────────────────────────
    hr("ZERO-API MODE CHECK")
    print("  Checking model router status...")
    router = ModelRouter()
    live_models = []
    mock_models = []
    try:
        avail = getattr(router, '_available_models', None) or getattr(router, 'available_models', None)
        if avail:
            for m in avail:
                (live_models if not getattr(m, 'is_mock', False) else mock_models).append(str(m))
    except Exception as e:
        print(f"  Could not introspect models: {e}")

    # check which model was actually used in query A
    state_a = result_a.get("state", {})
    logs_a = state_a.get("logs", [])
    mock_used = any("mock" in str(l.get("message","")).lower() or
                    "adaptive synthesis" in str(l.get("message","")).lower() or
                    "zero-api" in str(l.get("message","")).lower()
                    for l in logs_a)
    ollama_fail = any("ollama" in str(l.get("message","")).lower() and
                      ("fail" in str(l.get("message","")).lower() or
                       "404" in str(l.get("message","")).lower())
                      for l in logs_a)
    cloud_used  = any("gemini" in str(l.get("message","")).lower() or
                      "openai" in str(l.get("message","")).lower() or
                      "groq" in str(l.get("message","")).lower()
                      for l in logs_a)

    print(f"\n  Logs indicate:")
    print(f"    mock/adaptive-synthesis path used: {mock_used}")
    print(f"    Ollama failed: {ollama_fail}")
    print(f"    Cloud model used: {cloud_used}")
    print(f"\n  Zero-API determination:")
    if ollama_fail and not cloud_used:
        print("    → System fell back to mock/deterministic synthesis after LLM failure.")
        print("    → 'Zero-API' means rule-based structured synthesis, NOT LLM-free quality.")
        print("    → The README claim '100% Zero-API Local Synthesis' is TECHNICALLY MISLEADING.")
        print("      Real LLM required for genuine reasoning; fallback produces templated output.")
    elif cloud_used:
        print("    → Cloud LLM API was used. Zero-API claim does NOT apply to this run.")
    else:
        print("    → Could not determine from logs — see full log output.")

if __name__ == "__main__":
    asyncio.run(main())
