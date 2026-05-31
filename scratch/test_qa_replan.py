import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
import json

url = "http://127.0.0.1:8000/api/analyze"
query = "Force critic replanning test to evaluate DAG expansion recovery"

print("="*80)
print("TEST CASE: CRITIC REPLANNING & GOAL EXPANSION RECOVERY")
print("="*80)
print(f"Sending request: '{query}'...")

payload = {
    "query": query,
    "api_key": None,
    "provider": "gemini"
}

response = httpx.post(url, json=payload)
assert response.status_code == 200, f"Request failed: {response.text}"

data = response.json()
assert data["success"] is True
session_id = data["session_id"]
print(f"Success! Session ID created: {session_id}")

stream_url = f"http://127.0.0.1:8000/api/stream/{session_id}"
print(f"Connecting to SSE stream at {stream_url}...")

completed = False
replan_triggered = False
debate_triggered = False

with httpx.stream("GET", stream_url, timeout=60.0) as r:
    for line in r.iter_lines():
        if line:
            if line.startswith("data: "):
                event_data = json.loads(line[6:])
                status = event_data.get("status")
                logs = event_data.get("logs", [])
                
                if logs:
                    last_log = logs[-1]
                    msg = last_log.get('message', '')
                    print(f" [{last_log.get('agent', 'system').upper()}]: {msg}")
                    
                    if "replan" in msg.lower() or "rollback" in msg.lower() or "audit" in msg.lower():
                        replan_triggered = True
                    if "debate" in msg.lower() or "consensus" in msg.lower() or "argument" in msg.lower():
                        debate_triggered = True
                    
                if status in ["completed", "failed", "degraded"]:
                    print(f"\nFinal Stream Status: {status.upper()}")
                    completed = (status in ["completed", "degraded"])
                    break

assert completed, "Workflow execution did not complete successfully!"
assert replan_triggered, "Critic Re-planning / rollback loop was not triggered!"
assert debate_triggered, "Consensus Debate engine was not triggered during re-planning!"

print("\n" + "="*80)
print("QA TEST SUCCESS: Critic replanning and goal expansion pipeline successfully executed and validated!")
print("="*80)
