import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
import json

url = "http://127.0.0.1:8000/api/analyze"
query = "i want to buy shoes under 10k"

print("="*80)
print("TEST CASE: CUSTOM SHOE SEARCH UNDER 10K")
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
task_titles = []

with httpx.stream("GET", stream_url, timeout=60.0) as r:
    for line in r.iter_lines():
        if line:
            if line.startswith("data: "):
                event_data = json.loads(line[6:])
                status = event_data.get("status")
                logs = event_data.get("logs", [])
                tasks = event_data.get("tasks", {})
                
                if tasks:
                    task_titles = [t["title"] for t in tasks.values()]
                
                if logs:
                    last_log = logs[-1]
                    print(f" [{last_log.get('agent', 'system').upper()}]: {last_log.get('message')}")
                    
                if status in ["completed", "failed", "degraded"]:
                    print(f"\nFinal Stream Status: {status.upper()}")
                    completed = (status in ["completed", "degraded"])
                    break

assert completed, "Workflow did not complete!"

print("\nRegistered Task Titles:")
for title in task_titles:
    print(f" - {title}")

# Verify that titles are dynamic and not the hardcoded Indian AI Startups parameters
assert any("Explore" in t or "shoes" in t.lower() for t in task_titles), "Task titles are not dynamic!"

# Fetch the strategic report
print("\nFetching strategic report...")
db_check_url = f"http://127.0.0.1:8000/api/report/{session_id}"
session_data_res = httpx.get(db_check_url)
assert session_data_res.status_code == 200

session_data = session_data_res.json()
report_content = session_data.get("content", "")
print("\n--- REPORT PREVIEW ---")
print("\n".join(report_content.split("\n")[:15]))
print("----------------------")

assert "STRATEGIC FEASIBILITY REPORT: I WANT TO BUY SHOES UNDER 10K" in report_content, "Report is not dynamic!"
assert "shoes" in report_content.lower(), "Report doesn't discuss the shoes!"

print("\n" + "="*80)
print("QA TEST SUCCESS: Custom Shoe Search under 10k generated successfully and verified!")
print("="*80)
