import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
import json
import time

url = "http://127.0.0.1:8000/api/analyze"
query = "Build me a market analysis for AI automation startups in India"

print("="*80)
print("TEST CASE: STARTUPS MARKET ANALYSIS IN INDIA")
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
# Use httpx.stream to parse the real-time event stream safely
with httpx.stream("GET", stream_url, timeout=60.0) as r:
    for line in r.iter_lines():
        if line:
            if line.startswith("data: "):
                event_data = json.loads(line[6:])
                status = event_data.get("status")
                logs = event_data.get("logs", [])
                tasks = event_data.get("tasks", {})
                
                if logs:
                    last_log = logs[-1]
                    print(f" [{last_log.get('agent', 'system').upper()}]: {last_log.get('message')}")
                    
                if status in ["completed", "failed", "degraded"]:
                    print(f"\nFinal Stream Status: {status.upper()}")
                    completed = (status in ["completed", "degraded"])
                    break

assert completed, "Workflow execution did not complete successfully!"

# Validate from database using `/api/report/{session_id}`
print("\nAsserting database contents for compiled strategic report...")
db_check_url = f"http://127.0.0.1:8000/api/report/{session_id}"
session_data_res = httpx.get(db_check_url)
assert session_data_res.status_code == 200

session_data = session_data_res.json()
report_content = session_data.get("content", "")
assert report_content is not None and len(report_content) > 0, "Strategic Report was not compiled!"

# Verify citations exist in report
assert "[^" in report_content, "Report lacks active superscript citations!"
# Verify table exists in report
assert "|" in report_content and "---" in report_content, "Report lacks strategic table formatting!"

print("\n" + "="*80)
print("QA TEST SUCCESS: Startups Market Analysis ran successfully and verified!")
print("="*80)
