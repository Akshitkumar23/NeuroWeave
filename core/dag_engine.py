"""
NeuroWeave DAG Execution Engine & Superpowers Orchestrator.

This module provides the DAGEngine for executing Directed Acyclic Graphs (DAGs) of tasks
with strict topological ordering, wave-based parallel dispatch, cascade failure isolation,
automatic retries, dynamic task injection for the Critic REPLAN feedback loop,
and Red/Green execution telemetry aligned with obra/superpowers principles.
"""

import asyncio
import copy
import logging
import time
from collections import defaultdict, deque
from enum import Enum
from typing import Dict, Any, List, Optional, Set, Callable, Awaitable, Tuple

logger = logging.getLogger("neuroweave.core.dag_engine")


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class DAGCycleError(ValueError):
    """Raised when a circular dependency is detected in the DAG."""
    pass


class DAGExecutionError(RuntimeError):
    """Raised when critical DAG execution failures occur."""
    pass


class DAGEngine:
    """
    Robust DAG Execution Engine.
    
    Features:
    - Kahn's Algorithm for topological sorting and cycle detection.
    - Level/Wave-based topological decomposition for maximum concurrency.
    - Dynamic task ready-queue scheduling.
    - Red/Green execution status tracking & metrics.
    - Cascade failure prevention: blocks dependent tasks when prerequisite fails.
    - Retry mechanism with configurable limits.
    - Replanning feedback loop: dynamic task injection and graph expansion upon Critic REPLAN.
    """

    def __init__(
        self,
        state_manager: Optional[Any] = None,
        task_executor: Optional[Callable[[Dict[str, Any]], Awaitable[Tuple[bool, Any, Optional[str]]]]] = None,
        max_concurrency: int = 10
    ):
        self.state = state_manager
        self.task_executor = task_executor
        self.max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)
        
        # Telemetry & Red/Green tracking
        self.execution_stats = {
            "total_tasks": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "retries": 0,
            "waves_executed": 0,
            "duration_seconds": 0.0,
            "quality_gate_status": "PENDING",  # RED / GREEN
            "quality_score": 1.0,
            "quality_cycles": 0,
            "healed_gaps": 0,
        }

    # =========================================================================
    # TOPOLOGICAL SORTING & GRAPH VALIDATION
    # =========================================================================

    @staticmethod
    def topological_sort(tasks: Dict[str, Dict[str, Any]]) -> List[str]:
        """
        Performs topological sorting using Kahn's algorithm (in-degree resolution).
        Returns an ordered list of task IDs.
        Raises DAGCycleError if a cycle or self-dependency exists.
        """
        if not tasks:
            return []

        # Build in-degree map and adjacency list (parent -> children)
        in_degree: Dict[str, int] = {tid: 0 for tid in tasks}
        children: Dict[str, List[str]] = defaultdict(list)
        all_task_ids = set(tasks.keys())

        for tid, tval in tasks.items():
            deps = tval.get("dependencies", [])
            for dep in deps:
                if dep == tid:
                    raise DAGCycleError(f"Self-dependency detected on task '{tid}'.")
                if dep in all_task_ids:
                    in_degree[tid] += 1
                    children[dep].append(tid)
                else:
                    logger.warning(f"Task '{tid}' has dangling dependency '{dep}' which is not in task set. Ignoring.")

        # Queue of nodes with in-degree 0 (no prerequisites)
        queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
        ordered: List[str] = []

        while queue:
            node = queue.popleft()
            ordered.append(node)
            for child in children[node]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(ordered) != len(tasks):
            cyclic_nodes = [tid for tid, deg in in_degree.items() if deg > 0]
            raise DAGCycleError(
                f"Circular dependency detected in DAG! Unresolvable cyclic nodes: {cyclic_nodes}"
            )

        return ordered

    @staticmethod
    def get_execution_waves(tasks: Dict[str, Dict[str, Any]]) -> List[List[str]]:
        """
        Partitions tasks into parallel execution waves (levels).
        Wave 0 contains all root tasks (no dependencies).
        Wave N contains tasks whose dependencies are all in waves < N.
        """
        if not tasks:
            return []

        # Validate acyclicity first
        DAGEngine.topological_sort(tasks)

        all_task_ids = set(tasks.keys())
        task_level: Dict[str, int] = {}
        
        # Calculate level for each task (memoized depth)
        def get_level(tid: str, visiting: Set[str]) -> int:
            if tid in task_level:
                return task_level[tid]
            if tid in visiting:
                raise DAGCycleError(f"Cycle detected involving task '{tid}'.")
            
            visiting.add(tid)
            deps = [d for d in tasks[tid].get("dependencies", []) if d in all_task_ids]
            
            if not deps:
                level = 0
            else:
                level = 1 + max(get_level(dep, visiting) for dep in deps)
            
            visiting.remove(tid)
            task_level[tid] = level
            return level

        for tid in tasks:
            if tid not in task_level:
                get_level(tid, set())

        # Group tasks by level
        max_level = max(task_level.values()) if task_level else 0
        waves: List[List[str]] = [[] for _ in range(max_level + 1)]
        for tid, lvl in task_level.items():
            waves[lvl].append(tid)

        return waves

    @staticmethod
    def validate_graph(tasks: Dict[str, Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
        """
        Validates the task graph for cycles, self-loops, and structural integrity.
        Returns (is_valid, error_message).
        """
        try:
            DAGEngine.topological_sort(tasks)
            return True, None
        except DAGCycleError as e:
            return False, str(e)
        except Exception as e:
            return False, f"DAG validation error: {str(e)}"

    # =========================================================================
    # EXECUTION PIPELINE (RED/GREEN TDD ENGINE)
    # =========================================================================

    async def execute_dag(
        self,
        tasks_override: Optional[Dict[str, Dict[str, Any]]] = None,
        task_executor: Optional[Callable[[Dict[str, Any]], Awaitable[Tuple[bool, Any, Optional[str]]]]] = None,
        on_task_start: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
        on_task_complete: Optional[Callable[[str, Dict[str, Any], Any], Awaitable[None]]] = None,
        on_task_failed: Optional[Callable[[str, Dict[str, Any], str], Awaitable[None]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Executes ready tasks in topological waves until all tasks reach a terminal state.
        
        Guarantees:
        1. Ready tasks (all dependencies completed) run concurrently up to max_concurrency.
        2. If a prerequisite task fails, downstream dependent tasks are automatically failed (blocked)
           to prevent deadlocks (cascade failure isolation).
        3. Automatic retry for tasks with retries < max_retries.
        4. StateManager is updated atomically on every status change.
        5. Red/Green execution telemetry is recorded.
        """
        start_time = time.time()
        executor = task_executor or self.task_executor

        if not executor and not self.state:
            raise DAGExecutionError("No task executor or state manager provided for DAG execution.")

        logger.info("Starting DAG execution pipeline.")
        waves_count = 0

        while True:
            # 1. Fetch latest task snapshot
            if self.state:
                tasks_snapshot = await self.state.get_tasks_snapshot()
            elif tasks_override is not None:
                tasks_snapshot = tasks_override
            else:
                break

            ready_tasks = []
            has_pending = False
            has_running = any(t.get("status") == TaskStatus.RUNNING.value for t in tasks_snapshot.values())

            # 2. Identify ready tasks and block cascade failures
            for tid, tval in tasks_snapshot.items():
                status = tval.get("status", TaskStatus.PENDING.value)
                
                if status == TaskStatus.PENDING.value:
                    has_pending = True
                    deps = tval.get("dependencies", [])
                    deps_satisfied = True
                    failed_dep = None

                    for dep in deps:
                        dep_task = tasks_snapshot.get(dep)
                        if not dep_task or dep_task.get("status") != TaskStatus.COMPLETED.value:
                            deps_satisfied = False
                            if dep_task and dep_task.get("status") in (
                                TaskStatus.FAILED.value,
                                TaskStatus.CANCELLED.value
                            ):
                                failed_dep = dep
                            break

                    if deps_satisfied:
                        ready_tasks.append(tval)
                    elif failed_dep:
                        # Cascade Failure Isolation: Block downstream task immediately
                        err_msg = f"Prerequisite task '{failed_dep}' failed or was cancelled."
                        logger.warning(f"Blocking task '{tid}': {err_msg}")
                        if self.state:
                            await self.state.set_task_status(tid, TaskStatus.FAILED.value, error=err_msg)
                        if tasks_override is not None:
                            tasks_override[tid]["status"] = TaskStatus.FAILED.value
                            tasks_override[tid]["error"] = err_msg

            # 3. If no ready tasks exist:
            if not ready_tasks:
                if has_running:
                    # Some tasks are currently executing; wait briefly and check again
                    await asyncio.sleep(0.05)
                    continue
                else:
                    # Fetch fresh snapshot to verify if any genuinely pending tasks remain
                    if self.state:
                        fresh_snapshot = await self.state.get_tasks_snapshot()
                    elif tasks_override is not None:
                        fresh_snapshot = tasks_override
                    else:
                        fresh_snapshot = {}

                    remaining_pending = [tid for tid, tval in fresh_snapshot.items() if tval.get("status") == TaskStatus.PENDING.value]
                    if remaining_pending:
                        logger.error(f"Deadlock detected in DAG: unresolvable pending tasks remaining: {remaining_pending}")
                        for tid in remaining_pending:
                            err_msg = "Dependency deadlocked or unresolvable."
                            if self.state:
                                await self.state.set_task_status(tid, TaskStatus.FAILED.value, error=err_msg)
                            if tasks_override is not None:
                                tasks_override[tid]["status"] = TaskStatus.FAILED.value
                                tasks_override[tid]["error"] = err_msg
                    break

            # 4. Execute all ready tasks concurrently
            waves_count += 1
            logger.info(f"Dispatching execution wave {waves_count} with {len(ready_tasks)} concurrent task(s).")
            
            async def _run_wrapped(task_data: Dict[str, Any]):
                async with self._semaphore:
                    task_id = task_data["id"]
                    retries = task_data.get("retries", 0)
                    max_retries = task_data.get("max_retries", 2)

                    # Update status to running
                    if self.state:
                        await self.state.set_task_status(task_id, TaskStatus.RUNNING.value)
                    if tasks_override is not None:
                        tasks_override[task_id]["status"] = TaskStatus.RUNNING.value

                    if on_task_start:
                        try:
                            await on_task_start(task_id, task_data)
                        except Exception as ex:
                            logger.error(f"Error in on_task_start hook for '{task_id}': {ex}")

                    # Execute task with retries
                    success = False
                    output = None
                    error = None

                    while retries <= max_retries:
                        try:
                            if executor:
                                success, output, error = await executor(task_data)
                            else:
                                success = True
                                output = f"Executed default routine for '{task_id}'"
                                error = None

                            if success:
                                break
                            else:
                                retries += 1
                                self.execution_stats["retries"] += 1
                                if retries <= max_retries:
                                    logger.warning(
                                        f"Task '{task_id}' failed (attempt {retries}/{max_retries+1}): {error}. Retrying..."
                                    )
                                    await asyncio.sleep(0.05 * (2 ** (retries - 1)))
                        except Exception as e:
                            retries += 1
                            self.execution_stats["retries"] += 1
                            error = str(e)
                            if retries <= max_retries:
                                logger.warning(
                                    f"Exception in task '{task_id}' (attempt {retries}/{max_retries+1}): {e}. Retrying..."
                                )
                                await asyncio.sleep(0.05 * (2 ** (retries - 1)))

                    # Update final status
                    final_status = TaskStatus.COMPLETED.value if success else TaskStatus.FAILED.value
                    if self.state:
                        await self.state.set_task_status(
                            task_id,
                            final_status,
                            output=output,
                            error=error
                        )
                    if tasks_override is not None:
                        tasks_override[task_id]["status"] = final_status
                        tasks_override[task_id]["output"] = output
                        tasks_override[task_id]["error"] = error
                        tasks_override[task_id]["retries"] = retries

                    if success:
                        self.execution_stats["completed"] += 1
                        if on_task_complete:
                            try:
                                await on_task_complete(task_id, task_data, output)
                            except Exception as ex:
                                logger.error(f"Error in on_task_complete hook for '{task_id}': {ex}")
                    else:
                        self.execution_stats["failed"] += 1
                        if on_task_failed:
                            try:
                                await on_task_failed(task_id, task_data, error or "Execution failed")
                            except Exception as ex:
                                logger.error(f"Error in on_task_failed hook for '{task_id}': {ex}")

            # Run batch
            await asyncio.gather(*[_run_wrapped(t) for t in ready_tasks])

        # Record final stats
        self.execution_stats["waves_executed"] = waves_count
        self.execution_stats["duration_seconds"] = round(time.time() - start_time, 3)
        
        if self.state:
            final_snapshot = await self.state.get_tasks_snapshot()
        else:
            final_snapshot = tasks_override or {}

        self.execution_stats["total_tasks"] = len(final_snapshot)
        self.execution_stats["completed"] = sum(1 for t in final_snapshot.values() if t.get("status") == TaskStatus.COMPLETED.value)
        self.execution_stats["failed"] = sum(1 for t in final_snapshot.values() if t.get("status") == TaskStatus.FAILED.value)
        self.execution_stats["cancelled"] = sum(1 for t in final_snapshot.values() if t.get("status") == TaskStatus.CANCELLED.value)
        return final_snapshot

    # =========================================================================
    # REPLANNING FEEDBACK LOOP & DYNAMIC TASK INJECTION
    # =========================================================================

    async def inject_tasks(self, new_tasks: List[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
        """
        Dynamically injects new tasks into the active DAG during a replan feedback loop.
        
        Validates:
        1. Non-empty tasks.
        2. No cycle creation when combined with existing tasks.
        3. Existing completed tasks retain their status and outputs.
        4. Injected tasks start in 'pending' status.
        """
        if not new_tasks:
            return True, "No tasks to inject."

        if not self.state:
            return False, "StateManager required for dynamic task injection."

        current_tasks = await self.state.get_tasks_snapshot()
        
        # Build candidate combined graph
        combined: Dict[str, Dict[str, Any]] = copy.deepcopy(current_tasks)
        
        for task in new_tasks:
            tid = task["id"]
            if tid in combined and combined[tid].get("status") == TaskStatus.COMPLETED.value:
                logger.info(f"Task '{tid}' already completed in state; retaining output.")
                continue
            
            combined[tid] = {
                "id": tid,
                "title": task.get("title", tid),
                "description": task.get("description", ""),
                "assigned_agent": task.get("assigned_agent", "researcher"),
                "dependencies": task.get("dependencies", []),
                "status": TaskStatus.PENDING.value,
                "output": None,
                "error": None,
                "retries": 0,
                "max_retries": task.get("max_retries", 3)
            }

        # Check for cycles in combined graph
        is_valid, err = self.validate_graph(combined)
        if not is_valid:
            logger.error(f"Dynamic injection rejected: Cycle detected in candidate graph: {err}")
            return False, f"Cycle detected in candidate graph: {err}"

        # Apply to state
        await self.state.update_tasks(new_tasks)
        logger.info(f"Successfully injected {len(new_tasks)} new task(s) into active DAG.")
        return True, None

    async def handle_replan_feedback(
        self,
        query: str,
        critic_issues: List[str],
        planner_agent: Any,
        active_skills: Optional[List[str]] = None
    ) -> bool:
        """
        Handles the Critic REPLAN feedback loop gracefully:
        1. Scans critic rejection logs and identified knowledge gaps.
        2. Calls PlannerAgent's autonomously_expand_goals to produce refined subtasks.
        3. Dynamically injects tasks into the DAG without circular deadlocks.
        4. Re-executes the DAG for the new tasks while preserving prior completed outputs.
        
        Returns True if new tasks were generated and injected, False otherwise.
        """
        logger.info("Executing Critic REPLAN refinement feedback loop...")
        
        if not self.state:
            logger.error("StateManager is required for replan feedback handling.")
            return False

        current_tasks = await self.state.get_tasks_snapshot()
        feedback_text = "; ".join(critic_issues) if critic_issues else "General quality refinement requested."

        expansion_tasks = await planner_agent.autonomously_expand_goals(
            query=query,
            current_tasks=current_tasks,
            critic_feedback=feedback_text,
            active_skills=active_skills
        )

        if not expansion_tasks:
            logger.warning("Planner generated no additional expansion tasks during replan.")
            return False

        # Convert to dict format
        task_dicts = [t.dict() if hasattr(t, "dict") else (t.model_dump() if hasattr(t, "model_dump") else t) for t in expansion_tasks]
        
        success, err = await self.inject_tasks(task_dicts)
        if not success:
            logger.error(f"Failed to inject expansion tasks during replan: {err}")
            return False

        return True

    def evaluate_quality_gate(self, critic_score: float, issues: Optional[List[str]] = None, threshold: float = 0.80) -> Tuple[str, bool]:
        """
        Evaluates the Red/Green quality gate based on Obra/Jesse Vincent Superpowers principles.
        Status is GREEN if critic_score >= threshold and no critical issues exist;
        otherwise status is RED, signaling that self-healing replanning is required.
        """
        self.execution_stats["quality_score"] = float(critic_score)
        critical_issues = [i for i in (issues or []) if any(w in str(i).lower() for w in ["unverified", "contradiction", "missing", "inaccurate", "unsupported"])]
        
        is_green = (critic_score >= threshold) and (len(critical_issues) == 0)
        status = "GREEN" if is_green else "RED"
        self.execution_stats["quality_gate_status"] = status
        
        if status == "RED":
            self.execution_stats["quality_cycles"] += 1
            logger.warning(f"🚨 Quality Gate RED (Score: {critic_score:.2f}, Critical Issues: {len(critical_issues)}). Triggering self-healing.")
        else:
            logger.info(f"✅ Quality Gate GREEN (Score: {critic_score:.2f}). Certified publication-ready.")
            
        return status, is_green

    def record_healed_gap(self, gap_description: str = "") -> None:
        """Records a successfully resolved gap turning a previous RED state towards GREEN."""
        self.execution_stats["healed_gaps"] += 1
        logger.info(f"🌿 Superpower Telemetry: Healed gap '{gap_description}'. Total healed: {self.execution_stats['healed_gaps']}")

    def get_execution_summary(self) -> Dict[str, Any]:
        """Returns Red/Green execution telemetry and performance metrics."""
        stats = dict(self.execution_stats)
        total = stats.get("total_tasks", 0)
        completed = stats.get("completed", 0)
        failed = stats.get("failed", 0)
        
        stats["success_rate"] = (completed / total * 100) if total > 0 else 0.0
        stats["is_green"] = (failed == 0 and completed > 0 and stats.get("quality_gate_status") != "RED")
        return stats
