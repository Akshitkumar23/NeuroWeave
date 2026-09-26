import os
import json
import glob
import sys

# Force UTF-8 for stdout and stderr
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

brain_dir = r"C:\Users\Mr\.gemini\antigravity\brain\d0767d36-a568-4508-9962-5472c3ff6985"
messages_dir = os.path.join(brain_dir, ".system_generated", "messages")

print(f"Reading messages from: {messages_dir}")
files = glob.glob(os.path.join(messages_dir, "*.json"))

subagents = {
    "91ed7789-28a7-4130-9c67-4d2a8afd23ff": "Senior Codebase Auditor",
    "a63f37d2-ebe2-4da4-9667-335ee5f8e9f4": "Intent Analyst Auditor",
    "dcc1c3da-4fdb-44f4-bfe2-a05a1ca10ced": "DAG Planner Auditor",
    "434953ce-695e-45e4-b4c0-51ca8ad76bda": "Web Researcher Auditor",
    "b127433c-ef81-406b-b744-7612685ac41a": "Python Sandbox Auditor",
    "f1ee733b-eb80-4d54-acf0-ef58a03bcbd6": "Vector Memory Auditor",
    "2854d4ad-7b3b-4b17-89b2-9eeff8d0e675": "Critic Reflection Auditor",
    "3481978d-1b5a-42b1-a858-3ddaa57ed26d": "Debate Engine Auditor",
    "3d7101a0-4277-41f4-83f8-3fce6d92e545": "Strategic Synthesizer Auditor",
    "bc510c50-0e7b-4e14-a7b4-391971d07eea": "QA Auditor - India Startups",
    "f6af34db-77fc-4ccd-94ec-daaace7ac01a": "QA Auditor - Valuation Finance",
    "794a9605-552d-484a-b9c7-5da51f55e6a5": "QA Auditor - Critic & Re-planning",
    "f222b0ad-9ab6-4dcf-9796-817b9bf3e695": "QA Auditor - Security Boundary"
}

for f in files:
    try:
        with open(f, 'r', encoding='utf-8') as file:
            data = json.load(file)
            sender = data.get("sender")
            if sender in subagents:
                print("\n" + "="*80)
                print(f"SUBAGENT: {subagents[sender]} ({sender})")
                print("="*80)
                content = data.get("content", "")
                # print the first 1500 characters of the content
                print(content[:2500] + ("\n... [TRUNCATED] ..." if len(content) > 2500 else ""))
    except Exception as e:
        print(f"Error reading {f}: {e}")
