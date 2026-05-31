import os
import json
import glob
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

brain_dir = r"C:\Users\Mr\.gemini\antigravity\brain\d0767d36-a568-4508-9962-5472c3ff6985"
messages_dir = os.path.join(brain_dir, ".system_generated", "messages")

files = glob.glob(os.path.join(messages_dir, "*.json"))

qa_agents = {
    "bc510c50-0e7b-4e14-a7b4-391971d07eea": "QA Auditor - India Startups",
    "f6af34db-77fc-4ccd-94ec-daaace7ac01a": "QA Auditor - Valuation Finance",
    "794a9605-552d-484a-b9c7-5da51f55e6a5": "QA Auditor - Critic & Re-planning",
    "f222b0ad-9ab6-4dcf-9796-817b9bf3e695": "QA Auditor - Security Boundary"
}

print("Searching for messages sent by the 4 QA Testing subagents...")
found = 0

for f in files:
    try:
        with open(f, 'r', encoding='utf-8') as file:
            data = json.load(file)
            sender = data.get("sender")
            if sender in qa_agents:
                found += 1
                print("\n" + "="*100)
                print(f"QA AGENT: {qa_agents[sender]} ({sender})")
                print("="*100)
                content = data.get("content", "")
                print(content)
    except Exception as e:
        print(f"Error reading {f}: {e}")

if found == 0:
    print("No messages found from the 4 QA Testing subagents. They might still be running or haven't sent reports yet.")
