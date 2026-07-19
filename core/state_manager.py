import asyncio
import copy
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("neuroweave.state_manager")

class StateManager:
    def __init__(self, session_id: str):
        self.session_id: str = session_id
        # Concurrent access locks
        self._lock = asyncio.Lock()
        
        # State values
        self.query: str = ""
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.active_agent: str = "idle"
        self.status: str = "initialized"  # initialized, running, completed, failed, replanning, degraded
        self.logs: List[Dict[str, Any]] = []
        self.tool_calls: List[Dict[str, Any]] = []
        self.confidence_history: List[float] = []
        
        # Memory variables
        self.working_memory: Dict[str, Any] = {}
        self.episodic_references: List[str] = []
        self.semantic_references: List[Dict[str, Any]] = []
        
        self.override_message: Optional[str] = None
        
        # Snapshots for rollbacks & checkpointing
        self._snapshots: List[Dict[str, Any]] = []

    async def set_override(self, msg: str):
        async with self._lock:
            self.override_message = msg

    async def initialize_session(self, query: str):
        async with self._lock:
            self.query = query
            self.status = "running"
            self.logs.append({
                "timestamp": asyncio.get_event_loop().time(),
                "agent": "system",
                "message": f"Initialized session for query: '{query}'",
                "type": "info"
            })
            await self._create_snapshot_unlocked()

    async def update_tasks(self, task_list: List[Dict[str, Any]]):
        """
        Populate or update the active task graph.
        """
        async with self._lock:
            for task in task_list:
                task_id = task["id"]
                self.tasks[task_id] = {
                    "id": task_id,
                    "title": task.get("title", ""),
                    "description": task.get("description", ""),
                    "assigned_agent": task.get("assigned_agent", "researcher"),
                    "dependencies": task.get("dependencies", []),
                    "status": "pending",  # pending, running, completed, failed
                    "output": None,
                    "retries": 0,
                    "max_retries": 3
                }
            self.logs.append({
                "timestamp": asyncio.get_event_loop().time(),
                "agent": "planner",
                "message": f"🧭 Planner Agent structured a custom, parallel Directed Acyclic Graph (DAG) containing {len(task_list)} optimized subtasks.",
                "type": "info"
            })
            await self._create_snapshot_unlocked()

    async def set_task_status(self, task_id: str, status: str, output: Any = None, error: Optional[str] = None):
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
                
                # Check for retry count modifications
                if status == "failed":
                    self.tasks[task_id]["retries"] += 1
                
                title = self.tasks[task_id].get("title", task_id)
                agent = self.tasks[task_id].get("assigned_agent", "system").upper()
                
                emoji = "🔍" if agent == "RESEARCHER" else "🧮" if agent == "ANALYZER" else "⚖️" if agent == "CRITIC" else "🧭"
                
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
                    "timestamp": asyncio.get_event_loop().time(),
                    "agent": "system",
                    "message": msg,
                    "type": "error" if status == "failed" else "info"
                })
                
                await self._create_snapshot_unlocked()

    async def set_active_agent(self, agent_name: str):
        async with self._lock:
            self.active_agent = agent_name
            # Avoid duplicating agent activations if already logged by task status
            if agent_name not in ["researcher", "analyzer", "critic"]:
                self.logs.append({
                    "timestamp": asyncio.get_event_loop().time(),
                    "agent": agent_name,
                    "message": f"🤖 Active Agent changed to {agent_name.upper()}.",
                    "type": "activation"
                })

    async def add_log(self, agent: str, message: str, type_str: str = "thought"):
        async with self._lock:
            self.logs.append({
                "timestamp": asyncio.get_event_loop().time(),
                "agent": agent,
                "message": message,
                "type": type_str
            })

    async def add_tool_call(self, agent: str, tool_name: str, arguments: Dict[str, Any], output: Any):
        async with self._lock:
            self.tool_calls.append({
                "timestamp": asyncio.get_event_loop().time(),
                "agent": agent,
                "tool": tool_name,
                "arguments": arguments,
                "output": str(output)[:1000]  # truncate huge buffers
            })

    async def add_confidence_score(self, score: float):
        async with self._lock:
            self.confidence_history.append(score)
            self.logs.append({
                "timestamp": asyncio.get_event_loop().time(),
                "agent": "critic",
                "message": f"⚖️ Critic audited findings. Score: {score:.2f} / 1.00 (Pass limit: 0.75).",
                "type": "metric"
            })

    async def rollback(self) -> bool:
        """
        Restores state to the previous completed task checkpoint.
        """
        async with self._lock:
            if len(self._snapshots) < 2:
                logger.warning("No snapshot available for rollback.")
                return False
            
            # Pop the current snapshot
            self._snapshots.pop()
            # Retrieve the previous snapshot
            previous_snapshot = self._snapshots[-1]
            
            self._restore_from_dict(previous_snapshot)
            self.logs.append({
                "timestamp": asyncio.get_event_loop().time(),
                "agent": "system",
                "message": "Orchestrator triggered state rollback to previous transaction checkpoint.",
                "type": "warning"
            })
            return True

    async def get_state_dict(self) -> Dict[str, Any]:
        """
        Returns a thread-safe copy of the active state.
        """
        async with self._lock:
            return {
                "session_id": self.session_id,
                "query": self.query,
                "status": self.status,
                "active_agent": self.active_agent,
                "tasks": copy.deepcopy(self.tasks),
                "logs": list(self.logs),
                "tool_calls": list(self.tool_calls),
                "confidence_history": list(self.confidence_history),
                "working_memory": dict(self.working_memory),
                "average_confidence": sum(self.confidence_history) / len(self.confidence_history) if self.confidence_history else 0.0
            }

    async def _create_snapshot_unlocked(self):
        """
        Saves a deep copy of the execution variables (called while holding the lock).
        """
        snapshot = {
            "query": self.query,
            "tasks": copy.deepcopy(self.tasks),
            "status": self.status,
            "confidence_history": list(self.confidence_history),
            "working_memory": copy.deepcopy(self.working_memory),
            "episodic_references": list(self.episodic_references),
            "semantic_references": copy.deepcopy(self.semantic_references)
        }
        self._snapshots.append(snapshot)
        if len(self._snapshots) > 10:
            self._snapshots.pop(0)  # limit stack size

    def _restore_from_dict(self, data: Dict[str, Any]):
        self.query = data["query"]
        self.tasks = copy.deepcopy(data["tasks"])
        self.status = data["status"]
        self.confidence_history = list(data["confidence_history"])
        self.working_memory = copy.deepcopy(data["working_memory"])
        self.episodic_references = list(data["episodic_references"])
        self.semantic_references = copy.deepcopy(data["semantic_references"])
