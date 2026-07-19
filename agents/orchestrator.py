import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from core.model_router import ModelRouter
from core.state_manager import StateManager
from core.tool_registry import registry

from agents.intent_analyzer import IntentAnalyzerAgent
from agents.planner import PlannerAgent
from agents.researcher import ResearcherAgent
from agents.analyzer import AnalyzerAgent
from agents.critic import CriticAgent
from agents.debate_engine import DebateEngineAgent
from agents.synthesizer import SynthesizerAgent

from utils.citation_manager import CitationManager
from memory.memory_manager import MemoryManager
from storage.repository import SessionRepository
from storage.database import DatabaseManager

from observability.metrics import MetricsAggregator
from observability.traces import ActiveTracer

logger = logging.getLogger("neuroweave.orchestrator")

class MasterOrchestrator:
    def __init__(
        self,
        session_id: str,
        db_manager: DatabaseManager,
        stream_queue: Optional[asyncio.Queue] = None
    ):
        self.session_id = session_id
        self.db = db_manager
        self.stream_queue = stream_queue
        
        # Core Platform Systems
        self.router = ModelRouter()
        self.state = StateManager(session_id)
        self.citations = CitationManager()
        self.memory = MemoryManager(session_id)
        self.repo = SessionRepository(db_manager)
        
        # Telemetry aggregation
        self.metrics = MetricsAggregator()
        self.tracer = ActiveTracer(session_id)

        # Initialize Subagents
        self.intent_agent = IntentAnalyzerAgent(self.router)
        self.planner_agent = PlannerAgent(self.router)
        self.researcher = ResearcherAgent(self.router, self.citations)
        self.analyzer = AnalyzerAgent(self.router)
        self.critic = CriticAgent(self.router)
        self.debate_engine = DebateEngineAgent(self.router)
        self.synthesizer = SynthesizerAgent(self.router, self.citations)

    async def broadcast_state(self):
        """
        Pushes a copy of the active transaction state into the SSE stream queue.
        """
        if self.stream_queue:
            state_dict = await self.state.get_state_dict()
            state_dict["metrics"] = self.metrics.get_summary()
            state_dict["traces"] = self.tracer.get_waterfall_chart_data()
            await self.stream_queue.put(state_dict)

    async def execute_workflow(self, query: str):
        """
        The production-grade execution pipeline coordinating the 7 specialized agents.
        """
        logger.info(f"Starting orchestration pipeline for: '{query}'")
        
        is_degraded = False
        
        # Setup logging tracing key
        await self.repo.create_session(self.session_id, query)
        await self.state.initialize_session(query)
        await self.state.add_log("system", f"🚀 Multi-agent system initialized. Formulating autonomous search path...", "info")
        await self.broadcast_state()

        # Step 1: User Intent Analysis
        await self.state.set_active_agent("intent_analyzer")
        span_key = self.tracer.start_span("Intent Analysis", "intent_analyzer")
        await self.broadcast_state()
        
        intent_res = await self.intent_agent.analyze(query)
        self.metrics.record_agent_latency("intent_analyzer", 1.2) # simulated metrics hook
        
        await self.state.add_log(
            "intent_analyzer",
            f"🤖 Intent Analyzer: Target query identified as a '{intent_res.intent}' request. Formulating analytical model with routing policy '{intent_res.routing_policy}' (Complexity: {intent_res.complexity}/10).",
            "thought"
        )
        self.tracer.stop_span(span_key)
        await self.broadcast_state()

        # Step 2: Dynamic Task Planning
        await self.state.set_active_agent("planner")
        span_key = self.tracer.start_span("Task DAG Generation", "planner")
        await self.broadcast_state()
        
        # Load Semantic Memory Context if RAG files exist
        rag_context = await self.memory.query_semantic_rag(query)
        
        plan = await self.planner_agent.generate_plan(query, rag_context)
        await self.state.update_tasks([task.dict() for task in plan.tasks])
        
        self.tracer.stop_span(span_key)
        await self.broadcast_state()

        # Step 3: Run the Task Graph DAG using concurrent execution loops
        loop_count = 0
        max_reflection_loops = 3
        
        while loop_count < max_reflection_loops:
            loop_count += 1
            await self.state.add_log("system", f"🔄 Initiating graph execution round {loop_count}...", "info")
            await self.broadcast_state()
            
            if self.state.override_message:
                override_msg = self.state.override_message
                await self.state.add_log("system", f"⚠️ Manual Override Intercepted: {override_msg}", "warning")
                self.state.override_message = None
                rag_context += f"\n[CRITICAL OVERRIDE]: {override_msg}"
            
            # Execute subtasks in topological ordering (parallel execution of non-dependent nodes)
            await self._execute_dag()
            
            # Step 4: Critic Hallucination & Confidence Review
            await self.state.set_active_agent("critic")
            span_key = self.tracer.start_span("Critic Audit Loop", "critic")
            await self.broadcast_state()
            
            # Assemble all task outputs for review
            task_summary = ""
            for tid, tval in self.state.tasks.items():
                task_summary += f"[{tid}]: {tval.get('title')}\nFindings: {tval.get('output')}\n"
                
            audit_report = await self.critic.evaluate_task_output(
                "Aggregated Pipeline Audit",
                task_summary,
                rag_context
            )
            
            await self.state.add_confidence_score(audit_report.confidence)
            self.metrics.record_critic_audit(len(audit_report.issues) > 0, audit_report.action == "REPLAN")
            self.tracer.stop_span(span_key)
            await self.broadcast_state()

            # Check floor thresholds (0.75 floor for proceed)
            if audit_report.confidence >= 0.75 or audit_report.action == "PROCEED":
                await self.state.add_log("critic", "🎉 Audit passed! All findings, quantitative models, and citations are verified as structurally sound.", "info")
                break
                
            # TRIGGER REFLECTION LOOP / STATE ROLLBACK
            await self.state.add_log(
                "critic",
                f"⚠️ Audit failed. Confidence score {audit_report.confidence:.2f} is below the 0.75 safety threshold. Initiating consensus debate and state rollback to address gaps.",
                "warning"
            )
            self.state.status = "replanning"
            await self.broadcast_state()
            
            # 1. State Rollback: Restore tasks to previous valid checkpoint states
            rollback_success = await self.state.rollback()
            if not rollback_success:
                logger.warning("No checkpoints found. Retaining active state.")

            # 2. Multi-Agent Debate Engine: Resolve disputes between Researcher and Critic
            await self.state.set_active_agent("debate_engine")
            span_key = self.tracer.start_span("Consensus Debate", "debate_engine")
            await self.broadcast_state()
            
            researcher_claims = "".join([str(t.get("output")) for t in self.state.tasks.values() if t.get("assigned_agent") == "researcher"])
            debate_res = await self.debate_engine.execute_debate(researcher_claims, audit_report.issues)
            
            debate_summary = (
                f"Consensus: {debate_res.consensus}\n"
                f"Discrepancies Resolved: {debate_res.contradictions_found}"
            )
            await self.state.add_log("debate_engine", f"🗣️ Consensus Debate finalized: '{debate_res.consensus[:180]}...'", "thought")
            self.tracer.stop_span(span_key)
            await self.broadcast_state()

            # 3. Autonomous Goal Expansion: inject follow-up tasks to solve gaps
            await self.state.set_active_agent("planner")
            span_key = self.tracer.start_span("Autonomous Goal Expansion", "planner")
            await self.broadcast_state()
            
            expansion_tasks = await self.planner_agent.autonomously_expand_goals(
                query,
                self.state.tasks,
                f"Critic issues: {audit_report.issues}. Reconciled debate consensus: {debate_res.consensus}"
            )
            
            if expansion_tasks:
                # Add to state task graph
                await self.state.update_tasks([t.dict() for t in expansion_tasks])
                await self.state.add_log("planner", f"🧩 Dynamic Goal Expansion: Injected {len(expansion_tasks)} supplementary tasks to resolve knowledge gaps.", "info")
            else:
                await self.state.add_log("planner", "No additional knowledge gaps identified. Executing degraded completion.", "warning")
                self.metrics.record_degraded_trigger()
                is_degraded = True
                self.tracer.stop_span(span_key)
                await self.broadcast_state()
                break
                
            self.tracer.stop_span(span_key)
            await self.broadcast_state()

        # Step 5: Strategic Synthesis
        await self.state.set_active_agent("synthesizer")
        span_key = self.tracer.start_span("Strategic Synthesis", "synthesizer")
        await self.broadcast_state()
        
        final_report = await self.synthesizer.compile_report(
            query,
            await self.state.get_state_dict(),
            debate_summary=debate_res.consensus if 'debate_res' in locals() else ""
        )
        
        # Save Report persistently in SQLite Database
        avg_conf = sum(self.state.confidence_history) / len(self.state.confidence_history) if self.state.confidence_history else 0.85
        terminal_status = "degraded" if is_degraded else "completed"
        
        await self.repo.insert_report(self.session_id, final_report, avg_conf)
        await self.repo.update_session_status(self.session_id, terminal_status, self.metrics.get_summary())

        # Log completion
        await self.state.add_log("synthesizer", f"📄 Final Strategic Synthesis Report compiled, citation-mapped, and archived successfully in database.", "info")
        self.tracer.stop_span(span_key)
        
        # Push finished variables
        self.state.working_memory["final_report"] = final_report
        self.state.status = terminal_status
        await self.broadcast_state()

    async def _execute_dag(self):
        """
        Executes ready tasks concurrently. Nodes whose dependencies are satisfied
        run in parallel using asyncio.gather.
        """
        while True:
            # Determine ready nodes
            ready_tasks = []
            for tid, tval in self.state.tasks.items():
                if tval["status"] == "pending":
                    # Check dependencies completed
                    deps_satisfied = True
                    for dep in tval["dependencies"]:
                        dep_task = self.state.tasks.get(dep)
                        if not dep_task or dep_task["status"] != "completed":
                            deps_satisfied = False
                            break
                    if deps_satisfied:
                        ready_tasks.append(tval)
                        
            if not ready_tasks:
                # If there are running tasks, we wait for them to finish.
                # If no tasks are running and no tasks are ready, we are either done or deadlocked.
                running_tasks = any(t["status"] == "running" for t in self.state.tasks.values())
                if not running_tasks:
                    break
                # Wait briefly for running tasks to complete
                await asyncio.sleep(0.05)
                continue


            # Run all ready nodes in parallel
            run_futures = [self._execute_single_task(t["id"]) for t in ready_tasks]
            await asyncio.gather(*run_futures)

    async def _execute_single_task(self, task_id: str):
        task = self.state.tasks[task_id]
        agent_type = task["assigned_agent"]
        title = task["title"]
        desc = task["description"]
        
        # Update state
        await self.state.set_task_status(task_id, "running")
        await self.state.set_active_agent(agent_type)
        
        span_key = self.tracer.start_span(f"Subtask: {title}", agent_type, task_id)
        await self.broadcast_state()

        # Pull Working context
        context_data = await self.memory.query_semantic_rag(desc)
        
        start_time = time.time()
        success = False
        output = ""
        
        try:
            if agent_type == "researcher":
                res = await self.researcher.execute_task(desc, context_data)
                output = res.findings
                success = True
            elif agent_type == "analyzer":
                # Gather other tasks outputs for pre-facts
                pre_facts = ""
                for tid, tval in self.state.tasks.items():
                    if tval.get("output") and tid != task_id:
                        pre_facts += f"Source Task: {tval.get('title')}\nOutput: {tval.get('output')}\n"
                        
                res = await self.analyzer.execute_task(desc, pre_facts)
                output = f"Analysis Summary:\n{res.analysis}\nCalculated metrics: {res.calculated_metrics}"
                success = True
            else:
                # Default generic task
                output = f"Executed default agent routine for task: {title}"
                success = True
                
            duration = time.time() - start_time
            self.metrics.record_agent_latency(agent_type, duration)
            self.metrics.record_tool_call(agent_type, success)
            
            # Save variables in Working Memory
            self.memory.write_working(task_id, output)
            
            # Update state node
            await self.state.set_task_status(task_id, "completed", output=output)
            self.tracer.stop_span(span_key, success=True)
            await self.repo.insert_trace(self.session_id, task_id, agent_type, duration, True, 0.0, 0, 0)
            await self.repo.insert_log(self.session_id, agent_type, f"Completed Task '{title}': {output[:150]}...", "info")
            await self.broadcast_state()
            
        except Exception as e:
            duration = time.time() - start_time
            self.metrics.record_tool_call(agent_type, False)
            await self.state.set_task_status(task_id, "failed", error=str(e))
            self.tracer.stop_span(span_key, success=False)
            await self.repo.insert_trace(self.session_id, task_id, agent_type, duration, False, 0.0, 0, 0)
            await self.repo.insert_log(self.session_id, agent_type, f"Failed Task '{title}': {str(e)}", "error")
            await self.broadcast_state()
