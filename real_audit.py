import os, sys, asyncio, json, re, time, uuid, textwrap
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from storage.database import DatabaseManager
from agents.orchestrator import MasterOrchestrator

def hr(label=""):
    w=76
    if label:
        p=max(0,(w-len(label)-2)//2)
        print("\n"+"="*p+f" {label} "+"="*p)
    else:
        print("\n"+"-"*w)

def trunc(s,n=300):
    s=str(s or "")
    return s if len(s)<=n else s[:n]+f"[+{len(s)-n}]"

async def run_q(query,division="auto"):
    db=DatabaseManager()
    await db.initialize()
    sid=f"audit_{uuid.uuid4().hex[:8]}"
    orch=MasterOrchestrator(session_id=sid,db_manager=db,stream_queue=None)
    t0=time.monotonic()
    await orch.execute_workflow(query=query,division=division)
    el=round(time.monotonic()-t0,2)
    sd=await orch.state.get_state_dict()
    sd["_elapsed"]=el; sd["_session"]=sid
    sd["_cit_count"]=len(orch.citations.citations)
    sd["_raw_tasks"]=dict(orch.state.tasks)
    return sd

def inspect(state,label):
    hr(label)
    tasks=state.get("_raw_tasks",{})
    wm=state.get("working_memory",{})
    report=wm.get("final_report","") or ""
    traces=state.get("traces",[])
    print(f"Session:{state.get('_session')} Elapsed:{state.get('_elapsed')}s Conf:{state.get('average_confidence')} Tasks:{len(tasks)} Cit:{state.get('_cit_count')} ReportLen:{len(report)}")
    
    hr("1.DAG")
    for tid,t in tasks.items():
        print(f"  [{tid}] agent={t.get('assigned_agent')} status={t.get('status')} title={trunc(t.get('title',''),80)}")
        print(f"       deps={t.get('dependencies')} output={trunc(t.get('output',''),180)}")
        data=t.get("data",{})
        if data: print(f"       data_keys={list(data.keys())}")
    
    hr("2.TRACES")
    for tr in traces:
        print(f"  {str(tr.get('agent','?')):22} dur={tr.get('duration_sec','?')}s ok={tr.get('success','?')} {trunc(tr.get('name',''),60)}")
    
    hr("3.RESEARCH CLAIMS")
    sc=wm.get("synced_claims",[])
    print(f"  synced_claims:{len(sc)}")
    for i,cl in enumerate(sc[:5]):
        print(f"  [{i+1}] {trunc(cl.get('claim','?'),140)} | src:{cl.get('source','—')} cit:{cl.get('citation_id','—')}")
    for tid,t in tasks.items():
        if t.get("assigned_agent")=="researcher":
            rc=t.get("data",{}).get("claims",[])
            print(f"  researcher task {tid} raw_claims:{len(rc)}")
            for c in rc[:5]:
                if isinstance(c,dict): print(f"    claim:{trunc(c.get('claim','?'),120)} cit:{c.get('citation_id','—')} src:{trunc(c.get('source','—'),80)}")
    
    inline=re.findall(r"\[\^(\d+)\]",report)
    bib=re.findall(r"\[\^(\d+)\]:\s*(.+)",report)
    print(f"\n  inline_refs:{sorted(set(int(x) for x in inline))} bib_entries:{len(bib)}")
    for num,content in bib: print(f"    [^{num}] {trunc(content,100)}")
    dangling=set(int(x) for x in inline)-set(int(x[0]) for x in bib)
    if dangling: print(f"  DANGLING_REFS:{sorted(dangling)}")
    
    hr("4.CRITIC VERDICTS")
    sup=cha=rej=0
    for tid,t in tasks.items():
        if t.get("assigned_agent")=="critic":
            vd=t.get("data",{}).get("claim_verdicts",[])
            print(f"  Task {tid}: {len(vd)} verdicts")
            for v in vd:
                vt=str(v.get("verdict","?")).upper()
                if vt=="SUPPORTED": sup+=1
                elif vt=="CHALLENGED": cha+=1
                elif vt=="REJECTED": rej+=1
                print(f"    [{vt:12}] {trunc(v.get('claim','?'),110)}")
                print(f"              reason:{trunc(v.get('reason','—'),80)}")
    print(f"\n  TALLY: SUP={sup} CHA={cha} REJ={rej}")
    if sup>0 and cha==0 and rej==0: print("  *** EVERYTHING AUTO-SUPPORTED ***")
    
    hr("5.DEBATE")
    print(f"  debate_summary:{trunc(wm.get('debate_summary',''),300)}")
    rj=wm.get("rejected_claims",[])
    print(f"  rejected_claims:{len(rj)}")
    for r in rj[:3]: print(f"    -{trunc(r,100)}")
    
    hr("6.QUANTITATIVE")
    sm=wm.get("synced_metrics",{})
    print(f"  synced_metrics:{json.dumps(sm,default=str)[:400]}")
    for tid,t in tasks.items():
        if t.get("assigned_agent")=="analyzer":
            d=t.get("data",{})
            print(f"  Task {tid}: formula={d.get('formula_used','—')} exec_status={d.get('execution_status','—')}")
            print(f"    metrics:{trunc(str(d.get('calculated_metrics',{})),250)}")
            print(f"    code:{trunc(d.get('code_executed','(none)'),250)}")
            print(f"    analysis:{trunc(d.get('analysis',''),250)}")
    
    hr("7.FINAL REPORT (first 1800 chars)")
    print(textwrap.indent(trunc(report,1800),"  "))
    rl=report.lower()
    for s in ["executive summary","key findings","comparison","pricing","risk","recommendation","source"]:
        print(f"    {'v' if s in rl else 'X'} {s}")
    
    hr("8.CONFIDENCE")
    print(f"  scores_list:{state.get('confidence_scores',[])} avg:{state.get('average_confidence','?')}")
    
    return {"avg_conf":state.get("average_confidence",0),"report_len":len(report),"tasks":len(tasks),
            "sup":sup,"cha":cha,"rej":rej,"bib":len(bib),"sc":len(sc),"rq":len(rj),
            "cit":state.get("_cit_count",0),"elapsed":state.get("_elapsed",0)}

async def main():
    QA="Compare Supabase and Firebase for a production SaaS startup in 2026. Analyze pricing, database capabilities, authentication, scalability, developer experience, vendor lock-in, security, and recommend which one I should choose for a startup."
    QB="If a startup has Rs 50 lakh annual revenue and grows 25% annually for 5 years, calculate the projected revenue each year and total cumulative growth."
    QC="Predict exactly which AI startup will become India market leader in 2035."
    
    print("=== RUNNING QUERY A ==="); print(QA)
    sa=await run_q(QA,"engineering")
    ra=inspect(sa,"QUERY A")
    
    print("\n\n=== RUNNING QUERY B ==="); print(QB)
    sb=await run_q(QB,"finance")
    rb=inspect(sb,"QUERY B")
    
    print("\n\n=== RUNNING QUERY C ==="); print(QC)
    sc=await run_q(QC,"strategy")
    rc=inspect(sc,"QUERY C")
    
    hr("FINAL TABLE")
    keys=["avg_conf","report_len","tasks","sup","cha","rej","bib","sc","rq","cit","elapsed"]
    print(f"{'Metric':28}  {'Q-A':>10}  {'Q-B':>10}  {'Q-C':>10}")
    for k in keys:
        print(f"  {k:26}  {str(ra.get(k)):>10}  {str(rb.get(k)):>10}  {str(rc.get(k)):>10}")
    
    hr("ZERO-API MODE")
    logs=sa.get("logs",[])
    def chk(t): return any(t in str(l.get("message","")).lower() for l in logs)
    of=chk("ollama") and (chk("404") or chk("fail") or chk("not found"))
    mv=chk("adaptive synthesis") or chk("mock router")
    cv=chk("gemini") or chk("openai") or chk("groq")
    print(f"  ollama_failed={of} mock_path={mv} cloud_used={cv}")
    if of and not cv:
        print("  VERDICT: Fell back to rule-based/deterministic synthesis after LLM failure")
        print("  100% Zero-API claim is MISLEADING — research works without LLM, reasoning does not")
    elif cv: print("  Cloud LLM used — Zero-API claim does not apply")
    else: print("  Cannot determine — check log messages above")

asyncio.run(main())
