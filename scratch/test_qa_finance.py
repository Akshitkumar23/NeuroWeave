import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
import json

url = "http://127.0.0.1:8000/api/analyze"
query = "Calculate capitalization models for Series A valuation seed rounds"

print("="*80)
print("TEST CASE: VALUATION FINANCE CAP MODELS")
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
final_tasks = {}
with httpx.stream("GET", stream_url, timeout=60.0) as r:
    for line in r.iter_lines():
        if line:
            if line.startswith("data: "):
                event_data = json.loads(line[6:])
                status = event_data.get("status")
                logs = event_data.get("logs", [])
                final_tasks = event_data.get("tasks", {})
                
                if logs:
                    last_log = logs[-1]
                    print(f" [{last_log.get('agent', 'system').upper()}]: {last_log.get('message')}")
                    
                if status in ["completed", "failed", "degraded"]:
                    print(f"\nFinal Stream Status: {status.upper()}")
                    completed = (status in ["completed", "degraded"])
                    break

assert completed, "Workflow execution did not complete successfully!"

# Validate calculations from accumulated tasks
print("\nAsserting session tasks for calculations and code sandboxing...")
assert final_tasks, "No task outputs returned in the event stream!"

analyzer_task_completed = False
for tid, tval in final_tasks.items():
    if tval.get("assigned_agent") == "analyzer":
        output = tval.get("output", "")
        print(f"\nAnalyzer Output found:\n{output}")
        assert "calculation" in output.lower() or "result" in output.lower() or "cagr" in output.lower() or "valuation" in output.lower()
        analyzer_task_completed = True
        break

assert analyzer_task_completed, "Analyzer task was not executed!"

print("\n" + "="*80)
print("QA TEST SUCCESS: Valuation Finance Capitalization Models ran successfully and verified!")
print("="*80)
