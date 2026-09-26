# 🧠 BRAIN.md — NeuroWeave Master Context & Architectural Blueprint

> **System Notice for AI Assistants & LLMs:**
> This document is the authoritative, comprehensive context file for **NeuroWeave**. Any AI agent, LLM (Cursor, Claude, ChatGPT, Gemini, Copilot, etc.), or engineer reading this file can instantly understand the complete architecture, codebase layout, agent orchestration lifecycle, memory hierarchy, security guardrails, API contracts, and engineering conventions of this repository.

---

## 📌 1. Project Identity & Executive Summary

- **Project Name:** NeuroWeave
- **Tagline:** Production-Grade Autonomous Multi-Agent Research & Strategic Decision Engine
- **Primary Language:** Python 3.9+ (Fully Async / `asyncio`)
- **Backend Framework:** FastAPI, Uvicorn, Pydantic v2, HTTPX, aiosqlite
- **Frontend Stack:** Vanilla HTML5, Modern CSS (Glassmorphism design system), Vanilla JavaScript (No heavy frameworks or build steps required)
- **Primary Runtime Target:** Native Windows, macOS, and Linux out-of-the-box (Zero native C++ compiler dependencies)
- **Repository Mission:** NeuroWeave is a self-contained autonomous multi-agent research and reasoning engine built around deterministic planning, evidence retrieval, analysis, verification, memory and synthesis. It transforms complex or ambiguous research objectives into verified, citation-backed, quantitative strategic reports using an autonomous team of specialized agents, a self-correcting Critic reflection loop, state rollbacks, and epistemic contradiction resolution with zero external LLM dependencies.

---

## 🏛️ 2. Core Architectural Overview & Visual Topology

NeuroWeave coordinates a team of specialized subagents operating on a dynamic Directed Acyclic Graph (DAG). It bridges external search tools, safe sandboxed execution, hierarchical memory, and human-in-the-loop overrides through a centralized asynchronous state manager.

```mermaid
graph TD
    UserQuery([User Research Query / Document Upload]) --> SecurityGuardrails[Security Guardrails: Injection & SSRF Shield]
    SecurityGuardrails --> Router[Deterministic Mode Router: Pure Zero-API Engine]
    
    subgraph "Central Orchestration Core"
        Orchestrator[Master Orchestrator (agents/orchestrator.py)]
        StateManager[(Centralized State Manager + Transactional Checkpoints)]
        PermissionRBAC[Agent RBAC Permission Manager]
        ToolRegistry[Decorator-Based Tool Registry]
    end

    Router --> Orchestrator
    Orchestrator <--> StateManager
    Orchestrator --> PermissionRBAC
    Orchestrator --> ToolRegistry

    subgraph "8 Specialized Autonomous Subagents"
        A1[1. Intent Analyzer]
        A2[2. Task Planner]
        A3[3. Researcher Agent]
        A4[4. Data Analyst Agent]
        A5[5. Memory Manager Agent]
        A6[6. Critic & Reflection Agent]
        A7[7. Multi-Agent Debate Engine]
        A8[8. Strategic Synthesizer Agent]
    end

    Orchestrator --> A1
    Orchestrator --> A2
    Orchestrator --> A3
    Orchestrator --> A4
    Orchestrator --> A5
    Orchestrator --> A6
    Orchestrator --> A7
    Orchestrator --> A8

    subgraph "Hierarchical Memory System"
        WM[Working Memory: In-Memory Key-Value]
        EM[(Episodic Memory: aiosqlite SQLite Storage)]
        SM[(Semantic Memory: Pure-Python Cosine Vector Store)]
    end

    A5 <--> WM
    A5 <--> EM
    A5 <--> SM

    subgraph "Sandboxed Tool Integrations"
        DuckSearch[DuckDuckGo Lite Web Search + Clean Snippets]
        SafePyExec[Sandboxed Python Math & Trend Executor]
    end

    ToolRegistry --> DuckSearch
    ToolRegistry --> SafePyExec

    subgraph "Observability & Real-Time Gateway"
        Telemetry[JSON Structured Logger & Latency Tracer]
        SSE[FastAPI Server-Sent Events SSE Stream]
        UI[Glassmorphic Interactive Dashboard (ui/)]
    end

    Orchestrator --> Telemetry
    Orchestrator --> SSE --> UI
```

---

## 🔄 3. Detailed End-to-End Orchestration Flow

When a user submits an objective query, the system executes the following deterministic yet adaptive sequence:

```
[User Query]
      │
      ▼
0. Pre-Flight Discovery:
   ├── Match AAS Domain Skills (15 curated playbooks in skills/)
   └── Match Agency Specialist Persona (225+ personas in personas/)
      │
      ▼
1. Intent Analysis (IntentAnalyzerAgent):
   ├── Classify category, complexity score (1-10), and routing policy
   └── Formulate initial strategic orientation
      │
      ▼
2. DAG Task Planning (PlannerAgent):
   ├── Query Semantic Memory (RAG) for uploaded reference documents
   └── Generate topological Task DAG with dependency constraints
      │
      ▼
3. DAG Execution Loop (Concurrent asyncio.gather):
   ├── Identify tasks whose dependencies are satisfied ('pending' -> 'running')
   ├── Researcher Agent: Live web searches (DuckDuckGo Lite) + citation ingestion
   ├── Analyzer Agent: Quantitative computations via sandboxed Python math engine
   └── Store outputs in Working Memory + snapshot state checkpoints
      │
      ▼
4. Critic & Verification Loop (CriticAgent):
   ├── Audit aggregated output against factual correctness and citations
   ├── Compute confidence score (0.0 to 1.0)
   ├── IF confidence >= 0.75 or action == "PROCEED" ──► Jump to Step 5
   └── IF confidence < 0.75 (Reflection & Rollback Triggered):
         ├── State Rollback: Restore tasks to previous valid checkpoint
         ├── Multi-Agent Debate: 2-round debate between Critic & Researcher
         └── Autonomous Goal Expansion: Inject subtasks to resolve gaps -> Re-execute
      │
      ▼
5. Strategic Synthesis (SynthesizerAgent):
   ├── Compile executive report (Executive Summary, Key Findings, Quantitative Models)
   ├── Map APA citations and calculate sentiment / keyphrases
   └── Save report, traces, and metrics persistently in SQLite
      │
      ▼
6. Client Delivery:
   └── Real-time SSE streaming terminates with status 'completed' or 'degraded'
```

---

## 🗂️ 4. Complete Codebase Directory & File Map

```
NeuroWeave/
├── main.py                        # Application entry point; initializes DB, routes, and mounts UI
├── requirements.txt               # Minimal, pure-Python dependencies (FastAPI, aiosqlite, etc.)
├── .env / .env.example            # Environment configurations (API keys, PORT, HOST)
├── README.md                      # Human-facing project overview and quickstart
├── BRAIN.md                       # Master architectural blueprint for AI agents and developers
│
├── agents/                        # Autonomous Subagent Implementations
│   ├── orchestrator.py            # Master Orchestrator coordinating all 7+ subagents and DAG
│   ├── intent_analyzer.py         # Intent classifier, complexity rater, skill/persona matcher
│   ├── planner.py                 # Task DAG generator & dynamic goal expansion engine
│   ├── researcher.py              # Web information scraper & fact extractor
│   ├── analyzer.py                # Data analyzer invoking sandboxed code calculations
│   ├── critic.py                  # Fact audit, confidence scorer, and reflection trigger
│   ├── debate_engine.py           # 2-round debate resolving researcher vs critic disputes
│   └── synthesizer.py             # Final executive report generator with APA citations
│
├── api/                           # FastAPI Router & HTTP Endpoints
│   └── routes.py                  # REST & SSE streaming endpoints (/api/analyze, /api/stream, etc.)
│
├── core/                          # Core Engine Infrastructure
│   ├── model_router.py            # Dynamic multi-LLM router with failover & offline mock fallback
│   ├── state_manager.py           # Thread-safe (asyncio.Lock) state store with rollback checkpoints
│   ├── tool_registry.py           # Decorator-based tool registry with schema & timeout enforcement
│   ├── structured_output.py       # Pydantic schema validation & self-repair prompting loops
│   ├── persona_manager.py         # Catalog parser for 225+ Agency Specialist personas
│   ├── skill_loader.py            # AAS (Agent Architecture Standard) skill loader & injector
│   └── nano_engine.py             # Micro utility routines for local heuristics
│
├── memory/                        # Hierarchical Memory Subsystem
│   ├── memory_manager.py          # Unified gateway for Working, Episodic, and Semantic memory
│   └── vector_store.py            # Pure-Python JSON vector store with cosine similarity & TF-IDF
│
├── tools/                         # Sandboxed Tooling Interfaces
│   ├── web_search.py              # DuckDuckGo Lite scraper, user-agent rotation, uddg unwrapper
│   └── code_executor.py           # Sandboxed Python math & statistics executor (AST-checked)
│
├── security/                      # Security, Sandboxing & RBAC
│   ├── guardrails.py              # Prompt injection shields, SSRF filters, dangerous Python blocker
│   └── permissions.py             # Role-Based Agent Control (RBAC) governing tool execution
│
├── storage/                       # Data Persistence & Repository Pattern
│   ├── database.py                # Asynchronous SQLite connection manager (WAL mode, aiosqlite)
│   ├── repository.py              # SessionRepository with CRUD operations for sessions, traces, reports
│   └── neuroweave.db              # Active SQLite database file
│
├── observability/                 # Telemetry & Monitoring Pipeline
│   ├── logger.py                  # Structured async JSON logging with rotation
│   ├── metrics.py                 # Token meter, cost estimator, agent latency recorder
│   └── traces.py                  # Distributed span tracer for waterfall latency charts
│
├── personas/                      # 225+ Agency Persona YAML definitions (msitarzewski agency standard)
│   ├── financial_analyst.yaml     # Financial valuation & modeling specialist
│   ├── security_architect.yaml    # Infrastructure & threat modeling expert
│   ├── growth_hacker.yaml         # Marketing, viral loops, acquisition specialist
│   └── ... (225+ files across 19 corporate divisions)
│
├── skills/                        # 15 AAS Domain Skill Playbooks
│   ├── market_analysis/           # Market sizing, TAM/SAM/SOM, Porter's Five Forces
│   ├── financial_valuation/       # DCF models, capitalization cap tables, ROI
│   ├── tech_architecture/         # Distributed systems, API design, high-availability
│   ├── api-security/              # OWASP API Top 10, Auth0, OAuth2, Zero-Trust
│   ├── deep-research/             # Academic, deep citation, peer-review methodology
│   └── ... (15 domain directories containing SKILL.md files)
│
├── evaluation/                    # Automated Benchmarking Subsystem
│   └── evaluator.py               # Comparative evaluator: Linear vs Reflective vs Debate & Memory
│
├── utils/                         # Helper Utilities
│   ├── citation_manager.py        # Reference tracker, domain credibility scoring, APA formatter
│   └── ml_utils.py                # Local TextBlob sentiment scoring & keyphrase extraction
│
├── ui/                            # Production Glassmorphic Dashboard
│   ├── index.html                 # Semantic HTML5 single-page application
│   ├── styles.css                 # Vanilla CSS design system (Glassmorphism, dark theme, responsive)
│   └── app.js                     # Real-time SSE consumer, dynamic DAG renderer, Chart.js binder
│
└── scripts/                       # Automation & Sync Scripts
    ├── sync_agentic_skills.py     # Script to synchronize and index AAS skill files
    └── sync_all_agency_agents.py  # Script to download and parse agency agent personas
```

---

## 🧩 5. Deep-Dive: The 8 Specialized Subagents

| # | Agent Name | File Location | Primary Role & Core Logic |
|---|------------|---------------|---------------------------|
| **1** | **Intent Analyzer** | `agents/intent_analyzer.py` | Parses the user objective. Classifies intent (e.g. `market_research`, `code_analysis`), computes complexity (1–10), selects LLM routing policy (`simple_task`, `reasoning_task`, `coding_task`), and matches relevant skills & agency personas. |
| **2** | **Task Planner** | `agents/planner.py` | Decomposes the query into a Directed Acyclic Graph (DAG) with explicit dependency arrays (`dependencies: ["task_01"]`). Performs **Autonomous Goal Expansion** when the Critic reports missing knowledge dimensions. |
| **3** | **Researcher Agent** | `agents/researcher.py` | Executes targeted queries through `tools/web_search.py`. Extracts clean text snippets, strips ads/scripts, un-wraps redirect URLs, evaluates domain credibility, and registers references with `CitationManager`. |
| **4** | **Data Analyst Agent** | `agents/analyzer.py` | Ingests empirical facts from prior tasks, formulates mathematical models, and executes calculations in the safe `code_executor` sandbox to produce concrete numbers, percentages, and growth rates. |
| **5** | **Memory Agent** | `memory/memory_manager.py` | Manages the 3 tiers of memory: Working Memory (active execution variables), Episodic Memory (past session runs in SQLite), and Semantic Memory (RAG document embeddings via `PureVectorStore`). |
| **6** | **Critic & Reflection** | `agents/critic.py` | Audits combined task outputs against user goals, checks for hallucinated or un-cited claims, evaluates numerical consistency, and outputs a confidence score (0.0 to 1.0). If confidence < 0.75, halts execution and triggers rollback. |
| **7** | **Debate Engine** | `agents/debate_engine.py` | Conducts a structured 2-round cross-examination between Critic objections and Researcher assertions to reconcile conflicting claims, eliminate contradictions, and establish a rock-solid consensus. |
| **8** | **Strategic Synthesizer** | `agents/synthesizer.py` | Compiles the final executive intelligence briefing in Markdown, featuring an Executive Summary, Quantitative Assessment, Strategic Roadmaps, APA-formatted bibliography, and local sentiment/keyphrase analysis. |

---

## 🧠 6. Hierarchical Memory Architecture

NeuroWeave uses a 3-tier memory model designed for rapid retrieval and zero external vector DB bloat:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Working Memory (Ephemeral / In-Memory State)             │
│    • Key-value map residing in `StateManager`               │
│    • Instant O(1) latency for inter-agent context sharing   │
│    • Tracks intermediate subtask outputs and override flags │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ 2. Episodic Memory (Transactional / SQLite via aiosqlite)   │
│    • Table: `sessions`, `tasks`, `execution_logs`, `reports` │
│    • Allows state rollbacks, historical session re-loading  │
│    • Preserves exact DAG lineage and execution traces       │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ 3. Semantic Memory (RAG / Pure-Python Vector Store)          │
│    • Implemented in `memory/vector_store.py` (`PureVectorStore`)
│    • Dual-Mode:                                             │
│      a) Online Mode: Gemini Embeddings + Cosine Similarity  │
│      b) Offline Mode: Token TF-IDF Keyphrase Scoring        │
│    • Persisted locally to `storage/vector_store.json`       │
│    • Ingests user files (.txt, .md, .json) & scraped URLs   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛡️ 7. Security, Sandboxing & RBAC Guardrails

Security is enforced at multiple pipeline stages to prevent jailbreaks, SSRF, and dangerous execution:

1. **Prompt Injection Shield (`security/guardrails.py`):**
   - Scans queries using compiled regex patterns for attack signatures (`ignore previous instructions`, `jailbreak`, `system prompt override`, `dan mode`).
   - Replaces attack vectors with sanitized tokens before reaching the Model Router.

2. **SSRF Domain Protection (`security/guardrails.py`):**
   - Blocks dangerous URL schemes (`file://`, `gopher://`, `ftp://`).
   - Forbids requests to loopback addresses, local network IPs, and cloud metadata services (`localhost`, `127.0.0.1`, `169.254.169.254`, `.local`, `.lan`).

3. **Sandboxed Python Code Execution (`tools/code_executor.py`):**
   - Static AST check intercepts dangerous keywords (`import os`, `import sys`, `subprocess`, `open(`, `eval(`, `exec(`, `__import__`).
   - Runs in an isolated `context` dictionary containing strictly whitelisted mathematical builtins (`abs`, `min`, `max`, `round`, `math.*`) with no filesystem or network access.

4. **Role-Based Agent Control / RBAC (`security/permissions.py`):**
   - Enforces least privilege per agent:
     - `researcher` ➔ Allowed tools: `["web_search"]` (Code execution strictly blocked).
     - `analyzer` ➔ Allowed tools: `["code_executor"]` (Web scraping blocked).
     - `critic` & `synthesizer` ➔ Read-only analysis.

---

## ⚡ 8. Multi-LLM Model Router with Offline Fallback

The engine decouples agent logic from specific AI vendors via `core/model_router.py`:

- **Supported Providers:**
  1. **Google Gemini:** `gemini-1.5-flash`, `gemini-1.5-pro` (Fast, high-context)
  2. **OpenAI:** `gpt-4o-mini`, `gpt-4o`
  3. **Groq:** `llama3-70b-8192`, `mixtral-8x7b-32768` (Ultra-low latency)
  4. **Local Ollama:** `llama3`, `mistral`, `qwen` on `http://localhost:11434`
  5. **Mock / Local Simulation:** Heuristic offline generator when no keys are provided, allowing full offline testing without crashing.

- **Dynamic Routing Policies (`config/settings.yaml`):**
  - `simple_task` ➔ Prioritizes speed and low cost (e.g. Gemini 1.5 Flash).
  - `reasoning_task` ➔ Prioritizes analytical depth (e.g. GPT-4o, Gemini 1.5 Pro).
  - `coding_task` ➔ Prioritizes code generation correctness.

- **Automatic Failover:**
  - If a primary model call fails or times out, the router automatically attempts the configured fallback models in sequence, down to local Ollama or simulated execution.

---

## 🎭 9. 225+ Agency Personas & 15 AAS Domain Skills

NeuroWeave includes a deep knowledge and persona specialization system:

### 1. Agency Specialist Personas (`personas/`)
- Based on the industry standard `msitarzewski/agency-agents` taxonomy.
- Categorized across 19 corporate divisions:
  - **Strategy & Exec:** `chief_of_staff`, `business_strategist`, `m_a_integration_manager`
  - **Engineering & Architecture:** `backend_architect`, `system_architect`, `cloud_security_architect`
  - **Finance & Accounting:** `chief_financial_officer`, `financial_analyst`, `fp_a_analyst`
  - **Security & Compliance:** `penetration_tester`, `threat_detection_engineer`, `data_privacy_officer`
  - **Marketing & Growth:** `growth_hacker`, `seo_specialist`, `brand_guardian`
- Parsed via `core/persona_manager.py` and dynamically injected into agent prompts to specialize tone, domain knowledge, and analytical rigor.

### 2. AAS Domain Skills (`skills/`)
- Curated markdown playbooks with YAML frontmatter located in `skills/<skill_name>/SKILL.md`.
- Key skills: `market_analysis`, `financial_valuation`, `tech_architecture`, `api-security`, `competitor-analysis`, `fact_checking`, `deep-research`.
- Automatically matched against user queries by `core/skill_loader.py` and injected into the task context.

---

## 🌐 10. REST API & Real-Time Streaming Specifications

The FastAPI gateway exposes the following HTTP endpoints (`api/routes.py`):

| Method | Endpoint | Description | Payload / Query Params |
|--------|----------|-------------|------------------------|
| `POST` | `/api/analyze` | Initiates autonomous research workflow in background | `{ "query": str, "provider": str, "division": str, "api_key": Optional[str] }` |
| `GET` | `/api/stream/{session_id}` | Real-time Server-Sent Events (SSE) event stream | Session ID path parameter |
| `POST` | `/api/upload` | Uploads `.txt`, `.md`, `.json` to semantic memory | Form-data: `file`, `session_id` |
| `POST` | `/api/ingest-url` | Scrapes web page and indexes in vector store | `{ "url": str, "session_id": str }` |
| `GET` | `/api/sessions` | Lists all historical research sessions | None |
| `DELETE`| `/api/sessions/{id}` | Deletes session and associated logs/reports | Session ID path parameter |
| `GET` | `/api/report/{id}` | Fetches finalized markdown report for session | Session ID path parameter |
| `POST` | `/api/save-key` | Persists API key to process & `.env` file | `{ "api_key": str, "provider": str }` |
| `GET` | `/api/key-status` | Returns list of configured/active providers | None |
| `POST` | `/api/override/{id}` | Injects human-in-the-loop steering message | `{ "message": str }` |
| `GET` | `/api/personas` | Lists all 225+ registered agency personas | None |
| `GET` | `/api/divisions` | Lists 19 agency divisions and member counts | None |
| `GET` | `/api/health` | Service health status check | None |

### SSE Streaming Event Payload Format
The `/api/stream/{session_id}` endpoint emits JSON events at every state transition:
```json
{
  "query": "Analyze AI automation startups in India",
  "status": "running",
  "active_agent": "researcher",
  "assigned_persona": "Financial Analyst",
  "active_skills": ["market_analysis", "financial_valuation"],
  "tasks": {
    "task_01": {
      "id": "task_01",
      "title": "Market Trends Analysis",
      "status": "completed",
      "assigned_agent": "researcher",
      "output": "Found 12 high-growth startups...",
      "dependencies": []
    }
  },
  "logs": [
    { "timestamp": 1725375000.0, "agent": "researcher", "message": "Scraping tech news...", "type": "info" }
  ],
  "confidence_history": [0.65, 0.88],
  "metrics": {
    "total_tokens": 1420,
    "estimated_cost": 0.00028,
    "elapsed_seconds": 3.4
  },
  "traces": [
    { "span": "Subtask: Market Trends", "agent": "researcher", "duration": 1.2, "status": "success" }
  ]
}
```

---

## 🖥️ 11. Frontend Glassmorphic UI Dashboard

The UI located in `ui/` is a zero-dependency, ultra-responsive single-page app:
- **`ui/index.html`:** Clean semantic structure featuring top division selector pills, brand header, active session history sidebar, live DAG visualization tree, interactive thought log drawer, and the report viewing modal.
- **`ui/styles.css`:** Custom dark-themed Glassmorphism styling (`backdrop-filter: blur(16px)`, curated HSL gradients, animated status pulses, responsive CSS grid).
- **`ui/app.js`:**
  - Connects to `/api/stream/{session_id}` via `EventSource`.
  - Dynamically updates DAG task cards and state badges.
  - Generates interactive Chart.js bar and pie charts dynamically from table data.
  - Provides Speech-to-Text voice input using the Web Speech API.
  - Supports 1-click PDF report export using `html2pdf.js`.
  - Supports instant Human-in-the-loop steering via the override drawer.

---

## 💾 12. SQLite Database Schema (`storage/database.py`)

All persistent data is stored in `storage/neuroweave.db` via `aiosqlite` with `PRAGMA journal_mode=WAL;`:

1. **`sessions`:** `session_id (PK)`, `query`, `status`, `timestamp`, `metrics_json`
2. **`tasks`:** `id (PK)`, `task_id`, `session_id (FK)`, `description`, `assigned_agent`, `status`, `output`, `error`, `dependencies_json`, `timestamp`
3. **`logs` / `execution_logs`:** `id (PK)`, `session_id (FK)`, `timestamp`, `agent`, `message`, `type`
4. **`metrics`:** `id (PK)`, `session_id (FK)`, `metric_name`, `metric_value`, `metadata_json`, `timestamp`
5. **`traces`:** `id (PK)`, `session_id (FK)`, `task_id`, `agent`, `duration_sec`, `success`, `cost`, `tokens_input`, `tokens_output`, `timestamp`
6. **`documents`:** `id (PK)`, `session_id (FK)`, `document_name`, `content`, `metadata_json`, `timestamp`
7. **`reports`:** `id (PK)`, `session_id (FK)`, `content`, `confidence_score`, `timestamp`
8. **`feedback`:** `id (PK)`, `session_id (FK)`, `user_feedback`, `rating`, `timestamp`

---

## 🚀 13. Setup, Runbook & Development Guide

### 1. Installation
```bash
# Clone or navigate to the workspace
cd NeuroWeave

# Verify Python version (3.9+ recommended)
python --version

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Variables (`.env`)
Create or edit `.env` in the root directory:
```ini
# Optional: Model API Keys (Leave blank to use local Ollama or simulated mode)
GEMINI_API_KEY="your-google-api-key"
OPENAI_API_KEY="your-openai-api-key"
GROQ_API_KEY="your-groq-api-key"

# Server Host & Port
PORT=8000
HOST="127.0.0.1"
```

### 3. Launching the Platform
```bash
# Start server
python main.py
```
Open your browser at **`http://127.0.0.1:8000`** to access the dashboard.

### 4. Running Verification Tests
```bash
# Run the complete integration and regression test suite
python test_deep_pipeline.py
```

---

## 🤖 14. Essential Guidelines for AI Assistants Modifying This Codebase

When any AI assistant is asked to extend, debug, or refactor NeuroWeave, **follow these core engineering principles**:

1. **Maintain Pure-Python / Windows Portability:**
   - Never introduce heavy vector databases (e.g., ChromaDB, Milvus, FAISS) that require native C++ compilers or fail on native Windows. Keep `PureVectorStore` lightweight and pure Python.
2. **Preserve Asynchronous Concurrency:**
   - All I/O operations (database access, network requests, state mutations) must remain fully asynchronous (`async` / `await`). Never use blocking calls like `time.sleep()` or synchronous `sqlite3` inside the event loop.
3. **Respect Agent Permission RBAC:**
   - Any new tool must be registered in `core/tool_registry.py` with explicit `allowed_agents`. Ensure `security/permissions.py` and `security/guardrails.py` rules are updated accordingly.
4. **Preserve State Rollbacks & Checkpoints:**
   - Do not bypass `StateManager._create_snapshot()` or state transitions. The Critic reflection loop relies on atomic task rollbacks.
5. **No Ad-Hoc Styling in UI:**
   - Use the CSS custom properties defined in `ui/styles.css` (`--bg-primary`, `--glass-bg`, `--accent-primary`, etc.). Keep the frontend clean, responsive, and glassmorphic without introducing heavy npm build tooling unless explicitly requested.
6. **Graceful Fallbacks Over Hard Failures:**
   - Always ensure that if third-party APIs (Gemini, OpenAI, DuckDuckGo) are unavailable or rate-limited, the system falls back gracefully to local caches, Ollama, or simulation mode with clear user-facing log messages.
