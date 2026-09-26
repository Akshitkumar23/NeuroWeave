"""
NeuroWeave Dynamic Task Planner Agent.

This module houses the PlannerAgent which constructs and manages Directed Acyclic Graphs (DAGs)
of execution tasks. It uses Pydantic validations (v2) to enforce strict topological structures
without circular dependencies, prevents dangling/broken references during initial generation and
autonomous goal expansions, and ensures robust validation of dynamic tasks.
"""

import re
import yaml
import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field, model_validator, field_validator
from core.model_router import ModelRouter
from core.structured_output import StructuredOutputParser

logger = logging.getLogger("neuroweave.agents.planner")

class TaskItem(BaseModel):
    """
    Pydantic schema representing a single atomic task in the execution plan.
    Dynamic validation ensures that IDs are clean, unique, and assigned agents are allowed.
    """
    id: str = Field(description="Unique string identifier (e.g. task_01)")
    title: str = Field(description="Short name of this subtask")
    description: str = Field(description="Step-by-step instruction on what to analyze or research")
    assigned_agent: str = Field(description="Assigned subagent: 'researcher', 'analyzer', or 'critic'")
    dependencies: List[str] = Field(default=[], description="List of task ID strings that must complete before this task can run")

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """
        Validates that the task ID is non-empty, stripped of surrounding whitespaces,
        and conforms to standard alphanumeric/hyphen/underscore naming (no spaces).
        """
        v = v.strip()
        if not v:
            raise ValueError("Task ID cannot be empty.")
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError(f"Task ID '{v}' must contain only alphanumeric characters, underscores, or hyphens (no spaces).")
        return v

    @field_validator("assigned_agent")
    @classmethod
    def validate_assigned_agent(cls, v: str) -> str:
        """
        Enforces strict RBAC for assigned subagents. Validates that the target agent is allowed.
        """
        v = v.strip().lower()
        allowed = {"researcher", "analyzer", "critic"}
        if v not in allowed:
            raise ValueError(f"Assigned agent '{v}' is invalid. Must be one of: {allowed}")
        return v


class TaskPlan(BaseModel):
    """
    Pydantic schema representing the complete task graph (DAG).
    Contains a model validator to detect circular dependencies/cycles at the schema level.
    """
    tasks: List[TaskItem] = Field(description="Collection of tasks forming a Directed Acyclic Graph (DAG)")

    @model_validator(mode="after")
    def validate_dag(self) -> "TaskPlan":
        """
        Validates that the collection of tasks represents a valid Directed Acyclic Graph (DAG).
        Checks for duplicate task IDs and circular dependencies.
        """
        # 1. Check for duplicate task IDs
        seen = set()
        for task in self.tasks:
            if task.id in seen:
                raise ValueError(f"Duplicate task ID detected in plan: '{task.id}'")
            seen.add(task.id)

        # 2. Check for circular dependencies using depth-first search (DFS) with 3-color coloring
        adj = {t.id: t.dependencies for t in self.tasks}
        visited = {}  # 0: unvisited, 1: visiting, 2: visited

        def dfs(node: str) -> bool:
            if visited.get(node, 0) == 1:
                return True  # Found recursion cycle
            if visited.get(node, 0) == 2:
                return False

            visited[node] = 1
            for dep in adj.get(node, []):
                # We only traverse nodes inside this plan set to avoid raising errors for external dependencies
                # which are handled during post-parsing phase.
                if dep in adj:
                    if dfs(dep):
                        return True
            visited[node] = 2
            return False

        for task in self.tasks:
            if visited.get(task.id, 0) == 0:
                if dfs(task.id):
                    raise ValueError(f"Circular dependency detected in task plan! A cycle exists involving task '{task.id}'.")

        return self


class PlannerAgent:
    """
    PlannerAgent is responsible for query analysis and generating/expanding structured research tasks.
    It builds Directed Acyclic Graphs (DAGs) that organize work parallelly or sequentially.
    """
    def __init__(self, router: ModelRouter, prompts_path: str = "config/prompts.yaml"):
        self.router = router
        self.prompts_path = prompts_path
        self.system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        """
        Loads the system prompt from the yaml configuration. Falls back gracefully on failure.
        """
        try:
            with open(self.prompts_path, 'r') as f:
                data = yaml.safe_load(f) or {}
                return data.get("planner", "You are the NeuroWeave Dynamic Task Planner.")
        except Exception as e:
            logger.error(f"Error loading planner prompt: {e}")
            return "You are the NeuroWeave Dynamic Task Planner."

    async def generate_plan(self, query: str, context_summary: str = "") -> TaskPlan:
        """
        Generates a valid TaskPlan containing tasks that can be executed in topological order.
        Guarantees that all tasks are circular-dependency free and cleans up any dangling/broken dependencies.
        """
        logger.info(f"Generating task DAG for query: '{query}'")
        
        prompt = (
            f"Build a clean Directed Acyclic Graph (DAG) for this user request.\n"
            f"Query: \"{query}\"\n"
            f"RAG Context:\n{context_summary}\n\n"
            f"Ensure tasks are split by agent focus. Rely on Researcher for facts gathering, and Analyzer for python math operations."
        )
        
        model_call = lambda p, s: self.router.call_llm(p, s, task_type="reasoning", complexity=6)
        
        # Pydantic schema validation is automatically invoked during structured output parsing.
        # If the Pydantic validator detects cycles or schema violations, it runs automated correction cycles.
        validated_result, _ = await StructuredOutputParser.parse_with_correction(
            llm_call_func=model_call,
            prompt=prompt,
            system_instruction=self.system_prompt,
            schema=TaskPlan
        )
        
        # Post-validation cleanup of dangling dependencies
        task_ids = {t.id for t in validated_result.tasks}
        for task in validated_result.tasks:
            original_deps = task.dependencies
            # Filter and keep only dependencies that are actually within the plan
            task.dependencies = [dep for dep in original_deps if dep in task_ids]
            if len(task.dependencies) != len(original_deps):
                removed = set(original_deps) - set(task.dependencies)
                logger.warning(f"Cleaned up dangling dependencies {removed} from task '{task.id}' in initial plan.")
                
        return validated_result

    async def autonomously_expand_goals(
        self,
        query: str,
        current_tasks: Dict[str, Any],
        critic_feedback: str
    ) -> List[TaskItem]:
        """
        AUTONOMOUS GOAL EXPANSION:
        Scans critic rejection logs, identifies missing competitive / financial dimensions,
        and generates extra tasks on-the-fly to be dynamically injected.
        Ensures new tasks are injected cleanly, resolved of any circular dependencies, and
        pruned of any dangling dependencies.
        """
        logger.info("Scanning for knowledge gaps to trigger autonomous goal expansion.")
        
        prompt = (
            f"The primary query was: \"{query}\"\n"
            f"Here are the tasks executed so far: {list(current_tasks.keys())}\n"
            f"The Critic identified these knowledge gaps / issues: \"{critic_feedback}\"\n"
            f"Autonomously identify what extra details (such as market risks, seed valuations, competitive metrics) "
            f"need follow-up research. Return ONLY a list of new tasks to inject into the graph, linked to existing outputs."
        )
        
        model_call = lambda p, s: self.router.call_llm(p, s, task_type="reasoning", complexity=7)
        
        try:
            validated_result, _ = await StructuredOutputParser.parse_with_correction(
                llm_call_func=model_call,
                prompt=prompt,
                system_instruction=self.system_prompt,
                schema=TaskPlan
            )
            
            # Filter out duplicates and check dependencies
            new_tasks = []
            new_task_ids = {t.id for t in validated_result.tasks}
            valid_task_ids = set(current_tasks.keys()).union(new_task_ids)
            
            for t in validated_result.tasks:
                if t.id not in current_tasks:
                    # Clean up dangling dependencies (external to both current and expanded task sets)
                    original_deps = t.dependencies
                    t.dependencies = [dep for dep in original_deps if dep in valid_task_ids]
                    if len(t.dependencies) != len(original_deps):
                        removed = set(original_deps) - set(t.dependencies)
                        logger.warning(f"Cleaned up dangling dependencies {removed} from expanded task '{t.id}'.")
                    
                    new_tasks.append(t)
            
            # Check for circular dependencies in the unified/combined task graph
            combined_adj = {}
            for tid, tval in current_tasks.items():
                combined_adj[tid] = tval.get("dependencies", [])
            for t in new_tasks:
                combined_adj[t.id] = t.dependencies

            visited = {}  # 0: unvisited, 1: visiting, 2: visited
            cycle_detected = False

            def dfs(node: str) -> bool:
                if visited.get(node, 0) == 1:
                    return True
                if visited.get(node, 0) == 2:
                    return False

                visited[node] = 1
                for dep in combined_adj.get(node, []):
                    if dep in combined_adj:
                        if dfs(dep):
                            return True
                visited[node] = 2
                return False

            for task_id in list(combined_adj.keys()):
                if visited.get(task_id, 0) == 0:
                    if dfs(task_id):
                        cycle_detected = True
                        break

            if cycle_detected:
                logger.error("Circular dependency detected in combined graph after goal expansion! Rejecting expansion tasks to avoid deadlock.")
                return []
            
            logger.info(f"Autonomous Goal Expansion active: Injected {len(new_tasks)} new tasks into graph.")
            return new_tasks
        except Exception as e:
            logger.error(f"Error executing autonomous goal expansion: {e}")
            return []
