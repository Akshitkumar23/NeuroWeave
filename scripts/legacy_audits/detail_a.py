import sys, asyncio, uuid
sys.path.insert(0,'.')
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
from storage.database import DatabaseManager
from agents.orchestrator import MasterOrchestrator

async def main():
    db = DatabaseManager()
    await db.initialize()
    sid = 'audit_detail_a'
    orch = MasterOrchestrator(session_id=sid, db_manager=db, stream_queue=None)
    QA = 'Compare Supabase and Firebase for a production SaaS startup in 2026.'
    await orch.execute_workflow(query=QA, division='engineering')
    sd = await orch.state.get_state_dict()
    tasks = dict(orch.state.tasks)
    wm = sd.get('working_memory',{})
    
    print('=== TASK TITLES ===')
    for tid, t in tasks.items():
        print(f'[{tid}] {t.get(chr(97)+chr(115)+chr(115)+chr(105)+chr(103)+chr(110)+chr(101)+chr(100)+"_"+chr(97)+chr(103)+chr(101)+chr(110)+chr(116))} : {t.get("title")}')
    
    print('\n=== DEBATE SUMMARY ===')
    print(wm.get('debate_summary','(none)'))
    
    print('\n=== REPORT LINES 1-60 ===')
    rpt = wm.get('final_report','')
    for i,line in enumerate(rpt.split('\n')[:60]):
        print(line)

asyncio.run(main())
