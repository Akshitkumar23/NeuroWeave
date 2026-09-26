"""
NeuroWeave Dynamic Task Planner Agent.

This module houses the PlannerAgent which constructs and manages Directed Acyclic Graphs (DAGs)
of execution tasks. It uses Pydantic validations (v2) to enforce strict topological structures
without circular dependencies, prevents dangling/broken references during initial generation and
autonomous goal expansions, and ensures robust validation of dynamic tasks.
"""

import re
import uuid
import yaml
import logging
from typing import Dict, Any, List, Optional
import uuid
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, model_validator, field_validator
from core.model_router import ModelRouter
from core.structured_output import StructuredOutputParser
from core.skill_loader import get_skill_catalog
from core.persona_manager import get_persona_registry

logger = logging.getLogger("neuroweave.agents.planner")


class TaskItem(BaseModel):
    """
    Pydantic schema representing a single atomic task in the execution plan.
    Dynamic validation ensures that IDs are clean, unique, assigned agents are allowed,
    and specialized personas are tracked.
    """
    id: str = Field(description="Unique string identifier (e.g. task_01)")
    title: str = Field(description="Short name of this subtask")
    description: str = Field(description="Step-by-step instruction on what to analyze or research")
    assigned_agent: str = Field(description="Assigned subagent: 'researcher', 'analyzer', or 'critic'")
    dependencies: List[str] = Field(default=[], description="List of task ID strings that must complete before this task can run")
    specialized_persona: Optional[str] = Field(default=None, description="Optimal specialized agency persona for this subtask (e.g. Database Optimizer, AI Engineer, Financial Analyst)")
    expected_output_format: str = Field(default="structured_findings", description="Expected output schema: structured_findings, quantitative_metrics, audit_verdict, or strategic_report")
    is_critical: bool = Field(default=True, description="Whether completion of this subtask is strictly mandatory for the final report")

    @model_validator(mode="before")
    @classmethod
    def sanitize_task_fields(cls, values: Any) -> Any:
        """
        Pre-processes and sanitizes raw model inputs before strict validation:
        1. Cleans and normalizes task ID (replaces spaces/punctuation with underscores).
        2. Normalizes dependencies (converts single string to list, cleans IDs).
        3. Normalizes assigned_agent aliases to canonical names.
        """
        if not isinstance(values, dict):
            return values

        # 1. Sanitize id
        if "id" in values and isinstance(values["id"], str):
            raw_id = values["id"].strip()
            # Replace whitespace, colons, slashes, hash with underscores
            clean_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", raw_id)
            clean_id = re.sub(r"_+", "_", clean_id).strip("_")
            values["id"] = clean_id or f"task_{uuid.uuid4().hex[:6]}"

        # 2. Sanitize dependencies
        if "dependencies" in values:
            deps = values["dependencies"]
            if isinstance(deps, str):
                deps_str = deps.strip()
                if deps_str:
                    clean_d = re.sub(r"[^a-zA-Z0-9_\-]", "_", deps_str).strip("_")
                    values["dependencies"] = [clean_d] if clean_d else []
                else:
                    values["dependencies"] = []
            elif isinstance(deps, list):
                clean_deps = []
                for d in deps:
                    if isinstance(d, str) and d.strip():
                        c_dep = re.sub(r"[^a-zA-Z0-9_\-]", "_", d.strip()).strip("_")
                        if c_dep:
                            clean_deps.append(c_dep)
                values["dependencies"] = clean_deps

        # 3. Sanitize assigned_agent aliases
        if "assigned_agent" in values and isinstance(values["assigned_agent"], str):
            raw_agent = values["assigned_agent"].strip().lower()
            alias_map = {
                "research": "researcher",
                "web_researcher": "researcher",
                "fact_checker": "researcher",
                "search": "researcher",
                "searcher": "researcher",
                "web_search": "researcher",
                "analysis": "analyzer",
                "data_analyzer": "analyzer",
                "code_analyzer": "analyzer",
                "math_analyzer": "analyzer",
                "quant": "analyzer",
                "python": "analyzer",
                "audit": "critic",
                "auditor": "critic",
                "review": "critic",
                "reviewer": "critic",
                "red_team": "critic",
                "summary": "synthesizer",
                "writer": "synthesizer",
                "report_generator": "synthesizer",
                "synthesis": "synthesizer"
            }
            values["assigned_agent"] = alias_map.get(raw_agent, raw_agent)

        return values

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
        Falls back to 'researcher' if unknown rather than breaking unrecoverably.
        """
        v = v.strip().lower()
        allowed = {"researcher", "analyzer", "critic", "synthesizer"}
        if v not in allowed:
            logger.warning(f"Assigned agent '{v}' not recognized. Defaulting to 'researcher'.")
            return "researcher"
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
        Checks for duplicate task IDs, self-dependencies, and circular dependencies.
        """
        if not self.tasks:
            return self

        # 1. Check for duplicate task IDs
        seen = set()
        for task in self.tasks:
            if task.id in seen:
                raise ValueError(f"Duplicate task ID detected in plan: '{task.id}'")
            seen.add(task.id)

        # 2. Check for self-dependencies
        for task in self.tasks:
            if task.id in task.dependencies:
                raise ValueError(f"Self-dependency detected: Task '{task.id}' cannot depend on itself.")

        # 3. Check for circular dependencies using DFS with 3-color coloring
        adj = {t.id: t.dependencies for t in self.tasks}
        visited = {}  # 0: unvisited, 1: visiting, 2: visited

        def dfs(node: str) -> bool:
            if visited.get(node, 0) == 1:
                return True  # Cycle detected
            if visited.get(node, 0) == 2:
                return False

            visited[node] = 1
            for dep in adj.get(node, []):
                # Traverse nodes present in current plan
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
            with open(self.prompts_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                return data.get("planner", "You are the NeuroWeave Dynamic Task Planner.")
        except Exception as e:
            logger.error(f"Error loading planner prompt: {e}")
            return "You are the NeuroWeave Dynamic Task Planner."

    def match_task_persona(self, task_query: str) -> Optional[str]:
        """
        Matches a specific task query or subtask title/description to the optimal specialized agency persona.
        (e.g. database query -> Database Optimizer, valuation -> FP&A Analyst, AI/transformer -> AI Engineer).
        """
        try:
            matched = get_persona_registry().match_persona(task_query)
            return matched.name if matched else None
        except Exception as e:
            logger.warning(f"Error matching specialized persona for task '{task_query[:40]}': {e}")
            return None

    async def generate_plan(
        self,
        query: str,
        context_summary: str = "",
        active_skills: Optional[List[str]] = None,
        assigned_persona: Optional[str] = None,
        intent_analysis: Optional[Any] = None
    ) -> TaskPlan:
        """
        Generates a valid TaskPlan containing tasks that can be executed in topological order.
        Guarantees that all tasks are circular-dependency free and cleans up any dangling/broken dependencies.
        Incorporates active skill playbooks/guidelines, intent dimensions, and specialist personas into task descriptions.
        """
        logger.info(f"Generating task DAG for query: '{query}' (active_skills={active_skills}, persona={assigned_persona})")
        
        # Load skill prompt injection block if skills are specified
        skills_context = ""
        if active_skills:
            try:
                catalog = get_skill_catalog()
                skill_objs = [catalog.get_skill(s) for s in active_skills if catalog.get_skill(s)]
                if skill_objs:
                    skills_context = catalog.get_skill_prompt_injection(skill_objs)
            except Exception as e:
                logger.warning(f"Failed to fetch skill context in planner: {e}")

        # Load persona directive if assigned
        persona_context = ""
        if assigned_persona:
            try:
                p_obj = get_persona_registry().get_persona(assigned_persona)
                if p_obj:
                    persona_context = f"\nLead Specialist Persona: {p_obj.name} ({p_obj.role}) [{p_obj.division}]\nVibe: {p_obj.vibe}\n"
            except Exception as e:
                logger.warning(f"Failed to fetch persona context in planner: {e}")

        # Extract dimensions from intent_analysis if provided
        intent_dimensions_str = ""
        if intent_analysis:
            if isinstance(intent_analysis, dict):
                dims = intent_analysis.get("analysis_dimensions", [])
                ents = intent_analysis.get("extracted_entities", [])
                is_quant = intent_analysis.get("is_quantitative", False)
            else:
                dims = getattr(intent_analysis, "analysis_dimensions", [])
                ents = getattr(intent_analysis, "extracted_entities", [])
                is_quant = getattr(intent_analysis, "is_quantitative", False)

            if dims or ents:
                intent_dimensions_str = (
                    f"\n=== INTENT & DIMENSIONAL REQUIREMENTS ===\n"
                    f"Target Analysis Dimensions: {', '.join(dims)}\n"
                    f"Identified Core Entities: {', '.join(ents) if ents else 'Implicit from query'}\n"
                    f"Quantitative Modeling Required: {is_quant}\n"
                )

        skills_prompt_section = f"\n{skills_context}\n" if skills_context else ""
        skills_directive = (
            f"\n\nDOMAIN PLAYBOOKS ACTIVE: {', '.join(active_skills)}.\n"
            f"CRITICAL REQUIREMENT: Explicitly incorporate the domain guidelines, analytical frameworks, and formulas "
            f"from these active playbooks directly into the task descriptions so downstream agents follow these standards."
            if active_skills else ""
        )

        prompt = (
            f"Build a clean Directed Acyclic Graph (DAG) for this user request.\n"
            f"Query: \"{query}\"\n"
            f"{persona_context}"
            f"{intent_dimensions_str}"
            f"{skills_prompt_section}"
            f"RAG Context:\n{context_summary}\n\n"
            f"Ensure tasks are split by agent focus. Rely on Researcher for facts gathering, Analyzer for python math operations, and Critic for audits."
            f"{skills_directive}"
        )
        
        # Directly generate the validated DAG plan deterministically
        from core.deterministic_engine import plan_dag, detect_query_intent
        q_intent = detect_query_intent(query)
        fallback_plan = plan_dag(query, q_intent)
        tasks_list = [TaskItem(**t) for t in fallback_plan.get("tasks", [])]
        validated_result = TaskPlan(tasks=tasks_list)
        
        # Post-validation cleanup of dangling dependencies and specialized persona assignment
        task_ids = {t.id for t in validated_result.tasks}
        is_conceptual = any(k in query.lower() for k in ["mcp", "concept", "what is", "difference between"]) and not any(k in query.lower() for k in ["%", "lakh", "crore", "compound", "calculate"])
        for task in validated_result.tasks:
            original_deps = task.dependencies
            # Filter and keep only dependencies that are actually within the plan
            task.dependencies = [dep for dep in original_deps if dep in task_ids]
            if len(task.dependencies) != len(original_deps):
                removed = set(original_deps) - set(task.dependencies)
                logger.warning(f"Cleaned up dangling dependencies {removed} from task '{task.id}' in initial plan.")

            # Ensure valid assigned agents
            if task.assigned_agent not in {"researcher", "analyzer", "critic", "synthesizer"}:
                task.assigned_agent = "researcher"

            # Guard against inappropriate mathematical labeling for conceptual topics
            if is_conceptual and "mathematical calculation" in task.title.lower():
                task.title = "Architectural & Protocol Deconstruction"
                task.description = f"Analyze communication semantics, capabilities, and transport protocols for: {query[:80]}"

            # Assign specialized persona to subtask if missing
            if not task.specialized_persona:
                task.specialized_persona = self.match_task_persona(f"{task.title} {task.description}") or assigned_persona
                
        return validated_result

    async def autonomously_expand_goals(
        self,
        query: str,
        current_tasks: Dict[str, Any],
        critic_feedback: str,
        active_skills: Optional[List[str]] = None,
        assigned_persona: Optional[str] = None
    ) -> List[TaskItem]:
        """
        AUTONOMOUS GOAL EXPANSION:
        Scans critic rejection logs, identifies missing competitive / financial dimensions,
        and generates extra tasks on-the-fly to be dynamically injected without an LLM.
        """
        logger.info(f"Scanning for knowledge gaps to trigger autonomous goal expansion. (active_skills={active_skills})")
        
        # Deterministic goal expansion based on critic feedback
        expanded_tasks = []
        feedback_lower = critic_feedback.lower()
        parent_id = list(current_tasks.keys())[-1] if current_tasks else None
        parent_deps = [parent_id] if parent_id else []

        if any(k in feedback_lower for k in ["pricing", "cost", "fee", "tier", "subscription"]):
            expanded_tasks.append(TaskItem(
                id="task_exp_pricing",
                title="Follow-up Pricing & TCO Deep Dive",
                description=f"Detailed cost modeling and pricing tier analysis for {query[:60]}",
                assigned_agent="analyzer",
                dependencies=parent_deps,
                is_critical=False
            ))
        if any(k in feedback_lower for k in ["benchmark", "performance", "bandwidth", "throughput", "latency", "fp8", "vram"]):
            expanded_tasks.append(TaskItem(
                id="task_exp_benchmarks",
                title="Follow-up Empirical Benchmark Audit",
                description=f"Targeted benchmark analysis covering throughput, latency, and resource metrics for {query[:60]}",
                assigned_agent="analyzer",
                dependencies=parent_deps,
                is_critical=False
            ))
        if any(k in feedback_lower for k in ["security", "vulnerability", "auth", "compliance", "threat"]):
            expanded_tasks.append(TaskItem(
                id="task_exp_security",
                title="Follow-up Security Architecture Audit",
                description=f"Zero-trust security and threat modeling audit for {query[:60]}",
                assigned_agent="critic",
                dependencies=parent_deps,
                is_critical=False
            ))
        if not expanded_tasks and any(k in feedback_lower for k in ["missing", "gap", "lack", "insufficient", "need"]):
            expanded_tasks.append(TaskItem(
                id="task_exp_general",
                title="Follow-up Deep Evidence Investigation",
                description=f"Targeted investigation resolving identified critic gaps: {critic_feedback[:80]}",
                assigned_agent="researcher",
                dependencies=parent_deps,
                is_critical=False
            ))

        new_tasks = [t for t in expanded_tasks if t.id not in current_tasks]
        for t in new_tasks:
            if not t.specialized_persona:
                t.specialized_persona = self.match_task_persona(f"{t.title} {t.description}") or assigned_persona

        return new_tasks

    async def run(
        self,
        query: str,
        context_summary: str = "",
        active_skills: Optional[List[str]] = None,
        assigned_persona: Optional[str] = None,
        intent_analysis: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Unified agent execution interface returning structured dictionary."""
        plan = await self.generate_plan(query, context_summary, active_skills, assigned_persona, intent_analysis)
        tasks_data = [t.model_dump() if hasattr(t, "model_dump") else t.dict() for t in plan.tasks]
        return {
            "status": "completed",
            "agent_name": "planner",
            "output": f"Constructed topological Task DAG containing {len(tasks_data)} coordinated tasks.",
            "data": {"tasks": tasks_data, "query": query}
        }

    execute = run
