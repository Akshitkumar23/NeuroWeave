"""
NeuroWeave Central State Manager & Transaction Coordinator.

This module provides thread-safe in-memory state management, snapshot rollbacks,
SQLite persistence, schema migration verification, and crash-resilient session recovery
aligned with obra/superpowers principles.
"""

import asyncio
import copy
import json
import logging
import time
from typing import Dict, Any, List, Optional

logger = logging.getLogger("neuroweave.state_manager")


class StateManager:
    """
    Thread-safe State Manager coordinating multi-agent execution state, task graph
    status, telemetry, rollbacks, serialization, and SQLite persistence / recovery.
    """

    def __init__(self, session_id: str):
        self.session_id: str = session_id
        self._lock = asyncio.Lock()
        
        # Core State
        self.query: str = ""
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.active_agent: str = "idle"
        self.status: str = "initialized"  # initialized, running, completed, failed, replanning, degraded
        self.active_skills: List[str] = []
        self.assigned_persona: Optional[str] = None
        self.persona_meta: Dict[str, Any] = {}
        
        # Telemetry & Logs
        self.logs: List[Dict[str, Any]] = []
        self.tool_calls: List[Dict[str, Any]] = []
        self.confidence_history: List[float] = []
        
        # Working & Episodic Memory
        self.working_memory: Dict[str, Any] = {}
        self.episodic_references: List[str] = []
        self.semantic_references: List[Dict[str, Any]] = []
        self.evidence_ledger: Dict[str, Any] = {}
        
        # Intercept & Overrides
        self.override_message: Optional[str] = None
        
        # Checkpointing & Snapshots for rollbacks
        self._snapshots: List[Dict[str, Any]] = []

    # =========================================================================
    # TRANSACTION OPERATIONS & CONCURRENCY
    # =========================================================================

    async def set_override(self, msg: str):
        """Sets a high-priority manual override message."""
        async with self._lock:
            self.override_message = msg

    async def initialize_session(self, query: str):
        """Initializes a new session transaction with query and initial snapshot."""
        async with self._lock:
            if self.query and self.query != query:
                history = list(self.working_memory.get("conversation_history", []))
                history.append({
                    "turn": len(history) + 1,
                    "query": self.query,
                    "effective_query": getattr(self, "effective_query", None) or self.query,
                    "final_report": self.working_memory.get("final_report", "")[:1000]
                })
                self.working_memory["conversation_history"] = history
                # Clear previous tasks for fresh execution graph in new turn
                self.tasks = {}
                self.effective_query = None

            self.query = query
            self.status = "running"
            self.logs.append({
                "timestamp": time.time(),
                "agent": "system",
                "message": f"Initialized session for query: '{query}'",
                "type": "info"
            })
            await self._create_snapshot_unlocked()

    async def get_tasks_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """
        Thread-safe snapshot of all active tasks in the state.
        Guarantees safe concurrent iteration without dictionary-changed-size errors.
        """
        async with self._lock:
            return copy.deepcopy(self.tasks)

    async def update_tasks(self, task_list: List[Dict[str, Any]]):
        """
        Populate or update the active task graph.
        Preserves existing task outputs and retries for already completed tasks.
        """
        async with self._lock:
            for task in task_list:
                task_id = str(task["id"])
                existing = self.tasks.get(task_id, {})
                
                # If task already completed, retain its output and status
                if existing.get("status") == "completed":
                    continue

                self.tasks[task_id] = {
                    "id": task_id,
                    "title": task.get("title", task_id),
                    "description": task.get("description", ""),
                    "assigned_agent": task.get("assigned_agent", "researcher"),
                    "dependencies": task.get("dependencies", []),
                    "status": task.get("status", "pending"),
                    "output": existing.get("output", task.get("output", None)),
                    "error": task.get("error", None),
                    "retries": existing.get("retries", task.get("retries", 0)),
                    "max_retries": task.get("max_retries", 3)
                }
                
            self.logs.append({
                "timestamp": time.time(),
                "agent": "planner",
                "message": f"🧭 Planner Agent structured a custom, parallel Directed Acyclic Graph (DAG) containing {len(task_list)} optimized subtasks.",
                "type": "info"
            })
            await self._create_snapshot_unlocked()

    async def set_task_status(
        self,
        task_id: str,
        status: str,
        output: Any = None,
        error: Optional[str] = None
    ):
        """
        Atomically change the status of a specific node in the task graph.
        """
        async with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id]["status"] = status
                if output is not None:
                    self.tasks[task_id]["output"] = output
                if error:
                    self.tasks[task_id]["error"] = error
                
                if status == "failed":
                    self.tasks[task_id]["retries"] = self.tasks[task_id].get("retries", 0) + 1
                
                title = self.tasks[task_id].get("title", task_id)
                agent = self.tasks[task_id].get("assigned_agent", "system").upper()
                
                emoji = (
                    "🔍" if agent == "RESEARCHER"
                    else "🧮" if agent == "ANALYZER"
                    else "⚖️" if agent == "CRITIC"
                    else "🧭" if agent == "PLANNER"
                    else "📄"
                )
                
                if status == "running":
                    msg = f"{emoji} {agent.title()} started execution: '{title}'"
                elif status == "completed":
                    msg = f"✅ {agent.title()} completed: '{title}'"
                elif status == "failed":
                    msg = f"❌ {agent.title()} failed on '{title}'!"
                else:
                    msg = f"Task '{title}' is now {status}."
                
                if error:
                    msg += f" (Error details: {error})"
                    
                self.logs.append({
                    "timestamp": time.time(),
                    "agent": "system",
                    "message": msg,
                    "type": "error" if status == "failed" else "info"
                })
                
                if status in ("completed", "failed"):
                    await self._create_snapshot_unlocked()

    async def set_active_agent(self, agent_name: str):
        """Updates the active agent indicator."""
        async with self._lock:
            self.active_agent = agent_name
            if agent_name not in ["researcher", "analyzer", "critic"]:
                self.logs.append({
                    "timestamp": time.time(),
                    "agent": agent_name,
                    "message": f"🤖 Active Agent changed to {agent_name.upper()}.",
                    "type": "activation"
                })

    async def add_log(self, agent: str, message: str, type_str: str = "thought"):
        """Appends an execution event or thought log."""
        async with self._lock:
            self.logs.append({
                "timestamp": time.time(),
                "agent": agent,
                "message": message,
                "type": type_str
            })

    async def add_tool_call(self, agent: str, tool_name: str, arguments: Dict[str, Any], output: Any):
        """Records tool invocation telemetry."""
        async with self._lock:
            self.tool_calls.append({
                "timestamp": time.time(),
                "agent": agent,
                "tool": tool_name,
                "arguments": arguments,
                "output": str(output)[:1000]
            })

    async def add_confidence_score(self, score: float):
        """Records Critic audit confidence metric."""
        async with self._lock:
            self.confidence_history.append(score)
            self.logs.append({
                "timestamp": time.time(),
                "agent": "critic",
                "message": f"⚖️ Critic audited findings. Score: {score:.2f} / 1.00 (Pass limit: 0.75).",
                "type": "metric"
            })

    async def update_working_memory(self, key: str, value: Any):
        """Updates a key in working memory in a thread-safe manner."""
        async with self._lock:
            self.working_memory[key] = value

    # =========================================================================
    # SNAPSHOT CHECKPOINTING & ROLLBACK
    # =========================================================================

    async def rollback(self) -> bool:
        """
        Restores state to the previous completed task checkpoint.
        Resets any interrupted running tasks to pending status.
        """
        async with self._lock:
            if len(self._snapshots) < 2:
                logger.warning("No snapshot available for rollback.")
                return False
            
            # Pop current snapshot
            self._snapshots.pop()
            previous_snapshot = self._snapshots[-1]
            
            self._restore_from_dict(previous_snapshot)
            self.logs.append({
                "timestamp": time.time(),
                "agent": "system",
                "message": "Orchestrator triggered state rollback to previous transaction checkpoint.",
                "type": "warning"
            })
            return True

    async def _create_snapshot_unlocked(self):
        """Saves a deep copy of execution state (must hold self._lock)."""
        snapshot = {
            "query": self.query,
            "tasks": copy.deepcopy(self.tasks),
            "status": self.status,
            "active_skills": list(self.active_skills),
            "assigned_persona": self.assigned_persona,
            "persona_meta": copy.deepcopy(self.persona_meta),
            "confidence_history": list(self.confidence_history),
            "working_memory": copy.deepcopy(self.working_memory),
            "episodic_references": list(self.episodic_references),
            "semantic_references": copy.deepcopy(self.semantic_references),
            "timestamp": time.time()
        }
        self._snapshots.append(snapshot)
        if len(self._snapshots) > 15:
            self._snapshots.pop(0)

    def _restore_from_dict(self, data: Dict[str, Any]):
        """Restores state variables from an in-memory dictionary."""
        self.query = data.get("query", "")
        self.tasks = copy.deepcopy(data.get("tasks", {}))
        
        # Reset any running tasks to pending to enable re-execution
        for t in self.tasks.values():
            if t.get("status") == "running":
                t["status"] = "pending"
                
        self.status = data.get("status", "running")
        self.active_skills = list(data.get("active_skills", []))
        self.assigned_persona = data.get("assigned_persona", None)
        self.persona_meta = copy.deepcopy(data.get("persona_meta", {}))
        self.confidence_history = list(data.get("confidence_history", []))
        self.working_memory = copy.deepcopy(data.get("working_memory", {}))
        self.episodic_references = list(data.get("episodic_references", []))
        self.semantic_references = copy.deepcopy(data.get("semantic_references", []))

    # =========================================================================
    # STATE SERIALIZATION & DESERIALIZATION
    # =========================================================================

    async def get_state_dict(self) -> Dict[str, Any]:
        """Returns a thread-safe dictionary copy of the active state."""
        async with self._lock:
            return self._to_dict_unlocked()

    def _to_dict_unlocked(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "query": self.query,
            "status": self.status,
            "active_agent": self.active_agent,
            "active_skills": list(self.active_skills),
            "assigned_persona": self.assigned_persona,
            "persona_meta": copy.deepcopy(self.persona_meta),
            "tasks": copy.deepcopy(self.tasks),
            "logs": list(self.logs),
            "tool_calls": list(self.tool_calls),
            "confidence_history": list(self.confidence_history),
            "working_memory": copy.deepcopy(self.working_memory),
            "evidence_ledger": copy.deepcopy(self.evidence_ledger),
            "average_confidence": sum(self.confidence_history) / len(self.confidence_history) if self.confidence_history else 0.0
        }

    def to_json(self) -> str:
        """Serializes current state to a JSON string with safe fallbacks."""
        data = self._to_dict_unlocked()
        return json.dumps(data, default=str, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateManager":
        """Instantiates and populates a StateManager instance from a dictionary."""
        session_id = data.get("session_id", "recovered_session")
        mgr = cls(session_id)
        mgr.query = data.get("query", "")
        mgr.status = data.get("status", "initialized")
        mgr.active_agent = data.get("active_agent", "idle")
        mgr.active_skills = list(data.get("active_skills", []))
        mgr.assigned_persona = data.get("assigned_persona", None)
        mgr.persona_meta = copy.deepcopy(data.get("persona_meta", {}))
        mgr.tasks = copy.deepcopy(data.get("tasks", {}))
        
        # Reset any interrupted running tasks to pending
        for t in mgr.tasks.values():
            if t.get("status") == "running":
                t["status"] = "pending"
                
        mgr.logs = list(data.get("logs", []))
        mgr.tool_calls = list(data.get("tool_calls", []))
        mgr.confidence_history = list(data.get("confidence_history", []))
        mgr.working_memory = copy.deepcopy(data.get("working_memory", {}))
        return mgr

    @classmethod
    def from_json(cls, json_str: str) -> "StateManager":
        """Instantiates StateManager from a JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    # =========================================================================
    # SQLITE PERSISTENCE, RECOVERY & SCHEMA MIGRATIONS
    # =========================================================================

    async def save_checkpoint_to_db(self, db_manager: Any) -> bool:
        """
        Persists the current state snapshot into SQLite `state_checkpoints` table.
        """
        async with self._lock:
            try:
                state_json = json.dumps(self._to_dict_unlocked(), default=str)
                timestamp = time.time()
                async with await db_manager.get_connection() as conn:
                    await conn.execute(
                        """INSERT INTO state_checkpoints (session_id, checkpoint_data, timestamp)
                           VALUES (?, ?, ?)""",
                        (self.session_id, state_json, timestamp)
                    )
                    await conn.commit()
                logger.info(f"State checkpoint saved to database for session '{self.session_id}'.")
                return True
            except Exception as e:
                logger.error(f"Failed to save state checkpoint to database: {e}")
                return False

    @classmethod
    async def recover_session(cls, session_id: str, db_manager: Any) -> Optional["StateManager"]:
        """
        Recovers a session from SQLite checkpoints or task/session tables.
        Resets any interrupted running tasks to pending so the DAG engine can resume.
        """
        logger.info(f"Attempting crash recovery for session '{session_id}' from SQLite database...")
        try:
            async with await db_manager.get_connection() as conn:
                # 1. Try recovering latest state checkpoint
                try:
                    async with conn.execute(
                        "SELECT checkpoint_data FROM state_checkpoints WHERE session_id = ? ORDER BY timestamp DESC LIMIT 1",
                        (session_id,)
                    ) as cursor:
                        row = await cursor.fetchone()
                        if row and row[0]:
                            logger.info(f"Restored session '{session_id}' from checkpoint snapshot.")
                            return cls.from_json(row[0])
                except Exception:
                    # state_checkpoints table might be absent in legacy DBs
                    pass

                # 2. Fallback: Recover from sessions and tasks tables
                async with conn.execute(
                    "SELECT query, status FROM sessions WHERE session_id = ?",
                    (session_id,)
                ) as cursor:
                    sess_row = await cursor.fetchone()
                    if not sess_row:
                        logger.warning(f"No database records found for session '{session_id}'.")
                        return None

                    mgr = cls(session_id)
                    mgr.query = sess_row[0]
                    mgr.status = sess_row[1]

                # Recover tasks
                async with conn.execute(
                    "SELECT task_id, description, assigned_agent, status, output, error, dependencies_json FROM tasks WHERE session_id = ?",
                    (session_id,)
                ) as cursor:
                    task_rows = await cursor.fetchall()
                    for tr in task_rows:
                        tid = tr[0]
                        status = "pending" if tr[3] == "running" else tr[3]
                        mgr.tasks[tid] = {
                            "id": tid,
                            "title": tid,
                            "description": tr[1] or "",
                            "assigned_agent": tr[2] or "researcher",
                            "status": status,
                            "output": tr[4],
                            "error": tr[5],
                            "dependencies": json.loads(tr[6] or "[]"),
                            "retries": 0,
                            "max_retries": 3
                        }

                logger.info(f"Recovered session '{session_id}' with {len(mgr.tasks)} tasks from primary tables.")
                return mgr

        except Exception as e:
            logger.error(f"Error during session recovery for '{session_id}': {e}")
            return None

    @staticmethod
    async def verify_and_run_migrations(db_manager: Any) -> bool:
        """
        Verifies SQLite schema structure, ensures all required tables and columns exist,
        and applies idempotent migrations (including state_checkpoints and new indices).
        """
        logger.info("Running StateManager SQLite schema verification and migrations...")
        try:
            async with await db_manager.get_connection() as conn:
                # 1. Ensure state_checkpoints table exists
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS state_checkpoints (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        checkpoint_data TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                    )
                """)

                # 2. Verify all standard tables exist
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        query TEXT NOT NULL,
                        status TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        metrics_json TEXT
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        description TEXT,
                        assigned_agent TEXT,
                        status TEXT NOT NULL,
                        output TEXT,
                        error TEXT,
                        dependencies_json TEXT,
                        timestamp REAL NOT NULL,
                        FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                    )
                """)

                # 3. Create / verify indices
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_checkpoints_session ON state_checkpoints(session_id);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_timestamp ON sessions(timestamp);")

                await conn.commit()
                logger.info("StateManager schema verification and migrations completed successfully.")
                return True
        except Exception as e:
            logger.error(f"Schema migration error in StateManager: {e}")
            return False
