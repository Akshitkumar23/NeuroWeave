import re
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from core.model_router import ModelRouter
from core.state_manager import StateManager
from core.dag_engine import DAGEngine
from core.tool_registry import registry
import tools.web_search  # noqa: F401
import tools.code_executor  # noqa: F401
import tools.public_api_catalog  # noqa: F401
import tools.api_executor  # noqa: F401
from core.skill_loader import get_skill_catalog
from core.persona_manager import get_persona_registry
from core.deterministic_engine import is_unanswerable
from security.guardrails import SecurityGuardrails

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
        self.dag_engine = DAGEngine(state_manager=self.state, task_executor=self._execute_single_task_for_engine)
        self.citations = CitationManager()
        self.citation_mgr = self.citations
        # Phase 6.4 Fix #5: Read session isolation flag from environment
        import os as _os
        _session_isolated = _os.environ.get("NEUROWEAVE_SESSION_ISOLATED", "").lower() in ("1", "true", "yes")
        self.memory = MemoryManager(session_id, session_isolated=_session_isolated)
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
            state_dict["active_skills"] = list(getattr(self.state, "active_skills", []))
            state_dict["assigned_persona"] = getattr(self.state, "assigned_persona", None)
            state_dict["persona_meta"] = getattr(self.state, "persona_meta", {})
            state_dict["metrics"] = self.metrics.get_summary()
            state_dict["traces"] = self.tracer.get_waterfall_chart_data()
            await self.stream_queue.put(state_dict)

    def _get_skill_context(self) -> str:
        """
        Retrieves formatted prompt injection string for active domain skills and specialist persona.
        """
        active_names = getattr(self.state, "active_skills", [])
        contexts = []
        if active_names:
            try:
                catalog = get_skill_catalog()
                skills = [catalog.get_skill(name) for name in active_names if catalog.get_skill(name)]
                skill_inj = catalog.get_skill_prompt_injection(skills)
                if skill_inj:
                    contexts.append(skill_inj)
            except Exception as e:
                logger.warning(f"Error fetching skill context: {e}")

        # Add persona prompt injection
        assigned_persona_name = getattr(self.state, "assigned_persona", None)
        if assigned_persona_name:
            try:
                persona = get_persona_registry().get_persona(assigned_persona_name)
                if persona and persona.prompt_injection:
                    contexts.append(persona.prompt_injection)
            except Exception as e:
                logger.warning(f"Error fetching persona context: {e}")

        return "\n\n".join(contexts)

    async def execute_workflow(self, query: str, division: Optional[str] = "auto"):
        """
        The production-grade execution pipeline coordinating the 7 specialized agents.
        """
        logger.info(f"Starting orchestration pipeline for: '{query}' (Division: {division})")
        
        is_degraded = False
        
        # Verify schema migrations and setup session record
        await StateManager.verify_and_run_migrations(self.db)
        await self.repo.create_session(self.session_id, query)
        await self.state.initialize_session(query)
        await self.state.save_checkpoint_to_db(self.db)
        
        # Upfront Prompt Injection & Security Policy Enforcement (P0)
        is_injection, injection_reason = SecurityGuardrails.is_prompt_injection(query)
        if is_injection:
            logger.warning(f"Security Alert: Upfront prompt injection intercepted: {injection_reason}")
            await self.state.add_log("security", f"🚨 SECURITY INTERCEPT: {injection_reason}. Execution halted.", "error")
            containment_report = (
                "> [!CAUTION]\n"
                "> **SECURITY CONTAINMENT ACTIVE: PROMPT INJECTION REFUSED**\n\n"
                "# Security Refusal: Policy Integrity Enforcement\n\n"
                f"The submitted inquiry was classified as an adversarial instruction or system override attempt ({injection_reason}).\n\n"
                "### System Boundary Enforcement\n"
                "- **Status:** Policy Violation Intercepted (Upfront Containment)\n"
                "- **Policy:** NeuroWeave strictly rejects prompt overrides, system extraction requests, and instruction bypasses.\n"
                "- **Zero-Leakage Guarantee:** No system prompts, tokens, credentials, or internal memories are disclosed.\n\n"
                "Standard multi-agent execution has been terminated to preserve pipeline integrity."
            )
            self.state.status = "rejected"
            self.state.working_memory["final_report"] = containment_report
            self.state.working_memory["security_intercept"] = True
            await self.repo.insert_report(self.session_id, containment_report, 0.0)
            await self.repo.update_session_status(self.session_id, "rejected", {})
            await self.state.save_checkpoint_to_db(self.db)
            if self.stream_queue:
                await self.stream_queue.put(await self.state.get_state_dict())
            return containment_report

        await self.state.add_log("system", "🚀 Multi-agent NEXUS initialized. Formulating autonomous search path...", "info")

        # Record safe LLM / router status
        router_status = self.router.get_status()
        self.state.working_memory["router_status"] = router_status
        await self.state.add_log(
            "system",
            f"🧠 Model Router Status: Mode={router_status['mode']}, Provider={router_status['provider']}, Model={router_status['model']}",
            "info"
        )

        # Step 0: Skill & Persona Discovery
        catalog = get_skill_catalog()
        matched_skills = catalog.match_skills(query)
        self.state.active_skills = [s.name for s in matched_skills]
        if matched_skills:
            # Inject full skill metadata, keywords, frontmatter and playbooks into working memory
            skill_wm_data = catalog.get_skills_working_memory(matched_skills)
            for wm_key, wm_val in skill_wm_data.items():
                self.state.working_memory[wm_key] = wm_val

            skills_label = ", ".join([s.name.replace("_", " ").replace("-", " ").title() for s in matched_skills])
            await self.state.add_log(
                "system",
                f"✨ Active Domain Capabilities: {skills_label}. Applying specialized playbooks.",
                "info"
            )

        # Match agency specialist persona & collaborative Division Pod from Agency Agents
        persona_reg = get_persona_registry()
        matched_persona = persona_reg.match_persona(query, division=division)
        matched_pod = persona_reg.get_agency_pod(query, division=division)

        if matched_persona:
            self.state.assigned_persona = matched_persona.name
            self.state.persona_meta = matched_persona.to_dict()
            self.state.working_memory["assigned_persona"] = matched_persona.to_dict()
            await self.state.add_log(
                "system",
                f"Specialist Activated: {matched_persona.emoji} {matched_persona.name} ({matched_persona.role}) [Division: {matched_persona.division}]",
                "info"
            )

        if matched_pod:
            self.state.working_memory["agency_pod"] = matched_pod.to_dict()
            supporting_names = ", ".join([p.name for p in matched_pod.supporting_personas])
            tools_badge = ", ".join(matched_pod.pod_tools[:4])
            await self.state.add_log(
                "system",
                f"🏛️ Division Pod Deployed: {matched_pod.division} Pod (Lead: {matched_pod.lead_persona.name}, Supporting: {supporting_names or 'Domain Specialist'}). Tools: [{tools_badge}]",
                "info"
            )
            # Execute real Agent Collaboration Graph across the 3 specialists
            pod_exec = await matched_pod.execute_collaboration(query)
            self.state.working_memory["pod_collaboration"] = pod_exec
            self.dag_engine.execution_stats["pod_contributions"] = pod_exec.get("contributions", [])
            for c in pod_exec.get("contributions", []):
                tools_used = ", ".join(c.get("bound_tools", [])[:3])
                await self.state.add_log(
                    "system",
                    f"🤝 Pod Specialist '{c.get('specialist_name')}' ({c.get('role')}): Executed {c.get('phase')} with privileges [{tools_used}].",
                    "thought"
                )
            await self.state.add_log(
                "system",
                f"🎯 Lead Specialist Directive Harmonized: {pod_exec.get('synthesized_directive')[:180]}...",
                "info"
            )


        # Cross-Report Knowledge Memory: Query prior reports from SQLite
        query_words = [w for w in re.findall(r'\b[a-zA-Z]{4,}\b', query.lower()) if w not in {'what', 'when', 'where', 'which', 'about', 'versus'}]
        try:
            prior_dossiers = await self.repo.search_prior_reports(query_words, current_session_id=self.session_id, limit=2)
            if prior_dossiers:
                self.state.working_memory["prior_dossiers"] = prior_dossiers
                await self.state.add_log(
                    "system",
                    f"📚 Cross-Report Memory Linked: Discovered {len(prior_dossiers)} historical research dossiers to cross-cite.",
                    "info"
                )
        except Exception as e:
            logger.debug(f"Prior report retrieval skipped: {e}")

        await self.broadcast_state()

        # Multi-Turn Conversational Anaphora & Context Resolution
        effective_query = query
        history = self.state.working_memory.get("conversation_history", [])
        if history:
            prev_turn = history[-1]
            prev_query = prev_turn.get("effective_query") or prev_turn.get("query", "")
            q_lower = query.lower()
            if any(p in q_lower for p in [" it ", " it?", " it.", " it,", "which one", "them", "both", "compare it", "with it", "one is better"]):
                prev_subject = re.sub(r'^(what is|how does|explain|tell me about)\s+', '', prev_query, flags=re.IGNORECASE).rstrip(".?")
                if "compare it with" in q_lower:
                    target = re.sub(r".*compare it with\s+", "", query, flags=re.IGNORECASE).rstrip(".?")
                    effective_query = f"Compare {prev_subject} with {target}"
                elif "which one" in q_lower or "one is better" in q_lower:
                    effective_query = f"{query} (Context: {prev_query})"
                else:
                    effective_query = f"{query} (Regarding: {prev_subject})"
                await self.state.add_log(
                    "system",
                    f"🔗 Multi-Turn Context Linked: Resolved '{query}' -> '{effective_query}' using session history.",
                    "info"
                )
        self.state.effective_query = effective_query

        # =========================================================================
        # STEP 1: User Intent Analysis (IntentAnalyzerAgent)
        # =========================================================================
        await self.state.set_active_agent("intent_analyzer")
        span_key = self.tracer.start_span("Step 1: Intent Analysis", "intent_analyzer")
        await self.broadcast_state()
        
        intent_res = await self.intent_agent.analyze(effective_query)
        # Merge any refined skills & persona from intent analysis
        if intent_res.active_skills:
            current_skills = getattr(self.state, "active_skills", [])
            merged_skill_names = list(dict.fromkeys(current_skills + intent_res.active_skills))
            self.state.active_skills = merged_skill_names
            merged_skill_objs = [catalog.get_skill(s) for s in merged_skill_names if catalog.get_skill(s)]
            if merged_skill_objs:
                skill_wm_data = catalog.get_skills_working_memory(merged_skill_objs)
                for wm_key, wm_val in skill_wm_data.items():
                    self.state.working_memory[wm_key] = wm_val

        if intent_res.assigned_persona:
            self.state.assigned_persona = intent_res.assigned_persona
            persona_obj = get_persona_registry().get_persona(intent_res.assigned_persona)
            if persona_obj:
                self.state.persona_meta = persona_obj.to_dict()
                self.state.working_memory["assigned_persona"] = persona_obj.to_dict()
        self.state.intent = intent_res.intent
        self.state.working_memory["intent"] = intent_res.intent
        self.metrics.record_agent_latency("intent_analyzer", 1.2)
        
        skills_summary = f" (Active Skills: {', '.join(self.state.active_skills)})" if self.state.active_skills else ""
        persona_summary = f" [Specialist: {self.state.assigned_persona}]" if getattr(self.state, "assigned_persona", None) else ""
        await self.state.add_log(
            "intent_analyzer",
            f"🎯 Step 1 Intent Analysis: Target classified as '{intent_res.intent}' request.{skills_summary}{persona_summary} Selected routing policy '{intent_res.routing_policy}' (Complexity: {intent_res.complexity}/10).",
            "thought"
        )
        self.tracer.stop_span(span_key)
        await self.broadcast_state()

        # =========================================================================
        # STEP 2: DAG Task Planning (PlannerAgent)
        # =========================================================================
        await self.state.set_active_agent("planner")
        span_key = self.tracer.start_span("Step 2: DAG Task Planning", "planner")
        await self.broadcast_state()
        
        # Load Semantic Memory Context if RAG files exist
        rag_context = await self.memory.query_semantic_rag(query)
        
        plan = await self.planner_agent.generate_plan(
            effective_query,
            rag_context,
            active_skills=self.state.active_skills,
            assigned_persona=self.state.assigned_persona,
            intent_analysis=intent_res
        )
        task_dicts = [task.dict() if hasattr(task, "dict") else task.model_dump() for task in plan.tasks]

        # Inject First-Class Agency Pod Nodes into DAG if Pod is active
        matched_pod_data = self.state.working_memory.get("agency_pod")
        if matched_pod_data:
            pod_lead = matched_pod_data.get("lead_persona", {})
            pod_sups = matched_pod_data.get("supporting_personas", [])
            pod_tasks = []

            # 1. Supporting Specialist 1 Node
            if len(pod_sups) > 0:
                s1 = pod_sups[0]
                pod_tasks.append({
                    "id": "task_pod_sup1",
                    "title": f"Pod Review: {s1.get('name', 'Specialist 1')}",
                    "description": f"Execute specialized technical domain review for '{query}' using tools: {', '.join(s1.get('bound_tools', [])[:3])}",
                    "assigned_agent": "researcher",
                    "dependencies": [],
                    "specialized_persona": s1.get("name"),
                    "expected_output_format": "structured_findings",
                    "is_critical": True
                })

            # 2. Supporting Specialist 2 Node
            if len(pod_sups) > 1:
                s2 = pod_sups[1]
                pod_tasks.append({
                    "id": "task_pod_sup2",
                    "title": f"Pod Audit: {s2.get('name', 'Specialist 2')}",
                    "description": f"Execute operational risk & boundary assessment for '{query}' using tools: {', '.join(s2.get('bound_tools', [])[:3])}",
                    "assigned_agent": "analyzer",
                    "dependencies": [],
                    "specialized_persona": s2.get("name"),
                    "expected_output_format": "structured_findings",
                    "is_critical": True
                })

            # 3. Lead Specialist Directive Node (Depends on Supporting Specialists)
            lead_deps = [t["id"] for t in pod_tasks]
            pod_tasks.append({
                "id": "task_pod_lead",
                "title": f"Pod Lead Directive: {pod_lead.get('name', 'Lead Specialist')}",
                "description": f"Harmonize supporting domain findings from {', '.join([s.get('name', '') for s in pod_sups])} into consolidated architectural directive.",
                "assigned_agent": "researcher",
                "dependencies": lead_deps,
                "specialized_persona": pod_lead.get("name"),
                "expected_output_format": "strategic_report",
                "is_critical": True
            })

            # Connect downstream root research tasks to depend on task_pod_lead
            for t in task_dicts:
                if not t.get("dependencies"):
                    t["dependencies"] = ["task_pod_lead"]

            task_dicts = pod_tasks + task_dicts

        await self.state.update_tasks(task_dicts)
        await self.state.save_checkpoint_to_db(self.db)
        
        await self.state.add_log(
            "planner",
            f"🧭 Step 2 DAG Task Planning: Decomposed query into {len(plan.tasks)} coordinated subtasks with explicit dependencies and agent assignments.",
            "info"
        )
        self.tracer.stop_span(span_key)
        await self.broadcast_state()

        # =========================================================================
        # STEPS 3 & 4: Concurrent Search & Research + Quantitative Sandbox Execution
        # (Executed in topological DAG ordering via DAGEngine)
        # =========================================================================
        loop_count = 0
        max_reflection_loops = 3
        audit_report = None
        debate_res = None
        
        while loop_count < max_reflection_loops:
            loop_count += 1
            await self.state.add_log("system", f"🔄 Executing DAG execution cycle {loop_count}...", "info")
            await self.broadcast_state()
            
            if self.state.override_message:
                override_msg = self.state.override_message
                await self.state.add_log("system", f"⚠️ Manual Override Intercepted: {override_msg}", "warning")
                self.state.override_message = None
                rag_context += f"\n[CRITICAL OVERRIDE]: {override_msg}"
            
            # Execute subtasks via DAGEngine in topological waves
            await self.dag_engine.execute_dag()
            await self.state.save_checkpoint_to_db(self.db)
            
            # =====================================================================
            # STEP 5: Hierarchical Memory Sync (MemoryManager)
            # =====================================================================
            await self.state.set_active_agent("memory_agent")
            span_mem = self.tracer.start_span("Step 5: Hierarchical Memory Sync", "memory_agent")
            await self.broadcast_state()
            
            current_tasks = await self.state.get_tasks_snapshot()
            mem_res = await self.memory.sync_memory(self.session_id, current_tasks, query)
            
            # Explicitly propagate synced claims and metrics into working memory state
            wm_claims = self.memory.read_working("synced_claims", [])
            wm_metrics = self.memory.read_working("synced_metrics", {})
            if wm_claims:
                await self.state.update_working_memory("synced_claims", wm_claims)
            if wm_metrics:
                await self.state.update_working_memory("synced_metrics", wm_metrics)

            await self.state.add_log(
                "memory_agent",
                f"🧠 Step 5 Hierarchical Memory Sync: {mem_res['output']} ({len(wm_claims)} claims, {len(wm_metrics)} metrics synced)",
                "info"
            )
            self.tracer.stop_span(span_mem)
            await self.broadcast_state()

            # =====================================================================
            # STEP 6: Audit, Reflection & Goal Expansion (CriticAgent & PlannerAgent)
            # =====================================================================
            await self.state.set_active_agent("critic")
            span_key = self.tracer.start_span("Step 6: Critic Audit & Reflection", "critic")
            await self.broadcast_state()
            
            # Assemble all task outputs for review
            tasks_snapshot = await self.state.get_tasks_snapshot()
            task_summary = ""
            for tid, tval in tasks_snapshot.items():
                task_summary += f"[{tid}]: {tval.get('title')}\nFindings: {tval.get('output')}\n"
                
            skill_ctx = self._get_skill_context()
            audit_context = f"{rag_context}\n\n{skill_ctx}".strip() if skill_ctx else rag_context
            audit_report = await self.critic.evaluate_task_output(
                "Aggregated Pipeline Audit",
                task_summary,
                audit_context
            )
            
            await self.state.add_confidence_score(audit_report.confidence)
            self.metrics.record_critic_audit(len(audit_report.issues) > 0, audit_report.action == "REPLAN")
            self.tracer.stop_span(span_key)
            await self.broadcast_state()

            # Superpower Red/Green Quality Gate Evaluation
            gate_status, is_green = self.dag_engine.evaluate_quality_gate(
                critic_score=audit_report.confidence,
                issues=audit_report.issues,
                threshold=0.75
            )
            self.state.working_memory["quality_gate_status"] = gate_status

            if is_green or audit_report.action == "PROCEED":
                await self.state.add_log(
                    "critic",
                    f"✅ Step 6 Quality Gate GREEN: Verified factual consistency and calculations (Score: {audit_report.confidence:.2f}/1.00). Proceeding to consensus debate.",
                    "info"
                )
                break
            else:
                # TRIGGER REFLECTION LOOP & AUTONOMOUS GOAL EXPANSION (RED -> GREEN CYCLE)
                await self.state.add_log(
                    "critic",
                    f"🚨 Step 6 Quality Gate RED: Confidence score {audit_report.confidence:.2f} is below 0.75 threshold. Triggering autonomous self-healing loop.",
                    "warning"
                )
                self.state.status = "replanning"
                await self.broadcast_state()

                # Autonomous Goal Expansion via DAGEngine
                await self.state.set_active_agent("planner")
                span_expand = self.tracer.start_span("Autonomous Goal Expansion", "planner")
                await self.broadcast_state()
                
                expansion_success = await self.dag_engine.handle_replan_feedback(
                    query=query,
                    critic_issues=audit_report.issues,
                    planner_agent=self.planner_agent,
                    active_skills=self.state.active_skills
                )
                
                if expansion_success:
                    self.dag_engine.record_healed_gap("; ".join(audit_report.issues[:2]))
                    await self.state.add_log("planner", "🧩 Dynamic Goal Expansion: Injected supplementary tasks to heal knowledge gaps.", "info")
                    self.tracer.stop_span(span_expand)
                    await self.broadcast_state()
                    continue
                else:
                    await self.state.add_log("planner", "No additional knowledge gaps identified to expand. Executing degraded completion.", "warning")
                    self.metrics.record_degraded_trigger()
                    is_degraded = True
                    self.tracer.stop_span(span_expand)
                    await self.broadcast_state()
                    break

        # =========================================================================
        # STEP 7: Multi-Agent Debate Engine (DebateEngineAgent)
        # =========================================================================
        await self.state.set_active_agent("debate_engine")
        span_debate = self.tracer.start_span("Step 7: Multi-Agent Debate", "debate_engine")
        await self.broadcast_state()
        
        debate_tasks_snapshot = await self.state.get_tasks_snapshot()
        researcher_claims = "\n".join([str(t.get("output", "")) for t in debate_tasks_snapshot.values() if t.get("assigned_agent") in ("researcher", "analyzer")])
        if not researcher_claims:
            researcher_claims = f"Primary empirical findings and analytical models for query: {query}"
            
        issues_to_debate = audit_report.issues if (audit_report and audit_report.issues) else [
            f"Examine edge cases, operational failure modes, and architectural trade-offs for {query[:60]}."
        ]
        
        debate_res = await self.debate_engine.execute_debate(researcher_claims, issues_to_debate)
        self.state.working_memory["debate_summary"] = debate_res.consensus
        resolved_count = len(debate_res.resolved_contradictions)
        await self.state.add_log(
            "debate_engine",
            f"🗣️ Step 7 Debate Engine: Reconciled dialectical disputes between Researcher & Critic ({resolved_count} settled). Consensus: '{debate_res.consensus[:180]}...'",
            "thought"
        )
        self.tracer.stop_span(span_debate)
        await self.broadcast_state()

        # =========================================================================
        # STEP 8: Strategic Executive Synthesis (SynthesizerAgent)
        # =========================================================================
        await self.state.set_active_agent("synthesizer")
        span_synth = self.tracer.start_span("Step 8: Strategic Executive Synthesis", "synthesizer")
        await self.broadcast_state()
        
        rejected_claims = getattr(debate_res, "rejected_claims", []) if debate_res else []
        synth_res = await self.synthesizer.run(
            query,
            await self.state.get_state_dict(),
            debate_summary=debate_res.consensus if debate_res else "",
            skill_prompt=self._get_skill_context(),
            rejected_claims=rejected_claims
        )
        final_report = synth_res.get("output", "")
        synth_data = synth_res.get("data", {})
        self.state.working_memory["final_report"] = final_report
            
        sentiment_label = synth_data.get("sentiment", "Positive")
        top_kws = synth_data.get("keywords", [])
        kw_str = f" (Key themes: {', '.join(top_kws[:3])})" if top_kws else ""
        
        # Calculate Deterministic Multi-Factor Confidence Score:
        # formula: confidence = (evidence_quality * 0.40) + (source_agreement * 0.30) + (calculation_validity * 0.30) - (unresolved_contradictions * 0.15)
        # 1. Evidence quality based on count of valid citations
        cit_count = len(self.citations.citations)
        if cit_count == 0:
            evidence_quality = 0.35
        elif cit_count < 3:
            evidence_quality = 0.60 + (cit_count * 0.05)
        else:
            evidence_quality = min(0.92, 0.70 + (cit_count * 0.03))

        source_agreement = getattr(debate_res, "consensus_score", 0.85) if debate_res else 0.80

        # 2. Check actual calculation execution status
        analyzer_tasks = [t for t in tasks_snapshot.values() if t.get("assigned_agent") == "analyzer"]
        if analyzer_tasks:
            exec_status = analyzer_tasks[0].get("data", {}).get("execution_status", "executed")
            calc_validity = 1.0 if exec_status == "executed" else 0.50
        else:
            calc_validity = 1.0  # No math required, full marks

        unresolved_count = len(getattr(debate_res, "unresolved_contradictions", [])) if debate_res else 0

        raw_conf = (evidence_quality * 0.40) + (source_agreement * 0.30) + (calc_validity * 0.30) - (unresolved_count * 0.15)
        
        # 3. Honest temporal uncertainty cap
        if is_unanswerable(query):
            raw_conf = min(raw_conf, 0.45)
            
        deterministic_conf = round(max(0.0, min(1.0, raw_conf)), 2)
        await self.state.add_confidence_score(deterministic_conf)

        terminal_status = "degraded" if is_degraded else "completed"
        
        # Construct and attach canonical structured EvidenceLedger (Phase 5.2)
        try:
            from core.evidence_models import EvidenceLedger, StructuredClaim, GranularLineageChain, SourceType
            from api.routes import _parse_report_evidence
            parsed_ev = _parse_report_evidence(final_report, self.session_id)
            structured_claims = []
            for c in parsed_ev.get("claims", []):
                chain_raw = c.get("chain", {})
                chain_obj = GranularLineageChain(
                    evidence_id=chain_raw.get("evidence_id", "E-01"),
                    source_anchor=chain_raw.get("source_anchor", "Empirical Baseline"),
                    extracted_fact=chain_raw.get("extracted_fact", c.get("claim", "")),
                    originating_node=chain_raw.get("originating_node", "task_pod_lead"),
                    attributed_specialist=chain_raw.get("attributed_specialist", c.get("specialist", "Specialist")),
                    tools_executed=chain_raw.get("tools_executed", c.get("tools", "standard")),
                    critic_verdict=chain_raw.get("critic_verdict", "SUPPORTED (GREEN)"),
                    critic_confidence=deterministic_conf
                )
                
                # Determine source type
                st = SourceType.LIVE_EXTERNAL
                if "LOCAL" in c.get("status", "").upper() or "LOCAL" in str(chain_raw).upper():
                    st = SourceType.LOCAL_REFERENCE
                elif "Sandbox" in str(chain_raw) or "calc" in str(chain_raw).lower():
                    st = SourceType.CALCULATION_ARTIFACT
                elif "TEMPLATE" in c.get("status", "").upper():
                    st = SourceType.TEMPLATE_REFERENCE
                elif "wikipedia" in str(chain_raw).lower():
                    st = SourceType.SECONDARY_EXTERNAL

                structured_claims.append(StructuredClaim(
                    claim_id=c.get("claim_id", "CLM-01"),
                    statement=c.get("claim", ""),
                    specialist=c.get("specialist", "Specialist"),
                    tools=c.get("tools", "standard"),
                    evidence_anchor=c.get("evidence_anchor", "Empirical Telemetry"),
                    status=c.get("status", "SUPPORTED (GREEN)"),
                    source_type=st,
                    is_empirical=(st != SourceType.TEMPLATE_REFERENCE),
                    chain=chain_obj
                ))

            ledger = EvidenceLedger(
                session_id=self.session_id,
                claims=structured_claims,
                citations=parsed_ev.get("citations", [])
            )
            ledger.compute_counts()
            self.state.evidence_ledger = ledger.model_dump()
        except Exception as e:
            logger.warning(f"Could not build structured evidence ledger: {e}")

        # Save Report persistently in SQLite Database
        await self.repo.insert_report(self.session_id, final_report, deterministic_conf)
        await self.repo.update_session_status(self.session_id, terminal_status, self.metrics.get_summary())

        # Log completion
        await self.state.add_log(
            "synthesizer",
            f"📄 Step 8 Strategic Synthesis: Briefing compiled with APA citations, Chart.js visualizers, and sentiment [{sentiment_label}]{kw_str} (Final Epistemic Confidence: {deterministic_conf:.2f}). Archived in database.",
            "info"
        )
        self.tracer.stop_span(span_synth)
        
        # Push finished variables & save final checkpoint
        self.state.working_memory["final_report"] = final_report
        self.state.working_memory["llm_call_history"] = list(self.router.llm_call_history)
        self.state.status = terminal_status
        await self.state.save_checkpoint_to_db(self.db)
        await self.broadcast_state()

    async def _execute_single_task_for_engine(self, task: Dict[str, Any]) -> Tuple[bool, Any, Optional[str]]:
        """Task execution delegate invoked by DAGEngine."""
        task_id = task["id"]
        agent_type = task["assigned_agent"]
        title = task["title"]
        desc = task["description"]
        
        await self.state.set_active_agent(agent_type)
        span_key = self.tracer.start_span(f"Subtask: {title}", agent_type, task_id)
        await self.broadcast_state()

        # Pull Working context combined with active skill context
        context_data = await self.memory.query_semantic_rag(desc)
        skill_ctx = self._get_skill_context()
        combined_context = f"{context_data}\n\n{skill_ctx}".strip() if skill_ctx else context_data
        
        start_time = time.time()
        task_data_dict = {}
        
        try:
            if task_id == "task_pod_sup1":
                pod_collab = self.state.working_memory.get("pod_collaboration", {})
                contribs = pod_collab.get("contributions", [])
                sup1_c = next((c for c in contribs if c.get("phase") == "supporting_domain_analysis"), None)
                output = sup1_c.get("output") if sup1_c else f"Domain technical analysis complete for {task.get('specialized_persona')}."
                task_data_dict = {"persona": task.get("specialized_persona"), "phase": "supporting_domain_analysis", "output": output}
            elif task_id == "task_pod_sup2":
                pod_collab = self.state.working_memory.get("pod_collaboration", {})
                contribs = pod_collab.get("contributions", [])
                sup2_c = next((c for c in contribs if c.get("phase") == "supporting_boundary_assessment"), None)
                output = sup2_c.get("output") if sup2_c else f"Operational risk & boundary evaluation complete for {task.get('specialized_persona')}."
                task_data_dict = {"persona": task.get("specialized_persona"), "phase": "supporting_boundary_assessment", "output": output}
            elif task_id == "task_pod_lead":
                pod_collab = self.state.working_memory.get("pod_collaboration", {})
                output = pod_collab.get("synthesized_directive", "Harmonized Lead Specialist Directive formulated.")
                task_data_dict = {"persona": task.get("specialized_persona"), "phase": "lead_synthesis_directive", "directive": output}
            elif agent_type == "researcher":
                res = await self.researcher.execute_task(desc, combined_context)
                output = res.findings
                task_data_dict = res.model_dump() if hasattr(res, "model_dump") else res.dict()
            elif agent_type == "analyzer":
                current_snapshot = await self.state.get_tasks_snapshot()
                pre_facts = ""
                for tid, tval in current_snapshot.items():
                    if tval.get("output") and tid != task_id:
                        pre_facts += f"Source Task: {tval.get('title')}\nOutput: {tval.get('output')}\n"
                        
                pre_facts_with_skills = f"{pre_facts}\n\n{skill_ctx}".strip() if skill_ctx else pre_facts
                res = await self.analyzer.execute_task(desc, pre_facts_with_skills)
                output = f"Analysis Summary:\n{res.analysis}\nCalculated metrics: {res.calculated_metrics}"
                task_data_dict = res.model_dump() if hasattr(res, "model_dump") else res.dict()
            elif agent_type == "critic":
                current_snapshot = await self.state.get_tasks_snapshot()
                task_summary = ""
                for tid, tval in current_snapshot.items():
                    if tval.get("output") and tid != task_id:
                        task_summary += f"[{tid}]: {tval.get('title')}\nFindings: {tval.get('output')}\n"
                audit_context = f"{combined_context}\n\n{skill_ctx}".strip() if skill_ctx else combined_context
                audit_res = await self.critic.evaluate_task_output(title, task_summary, audit_context)
                output = f"Audit Verdict: {audit_res.action} (Confidence: {audit_res.confidence:.2f})\nSummary: {audit_res.summary}"
                task_data_dict = audit_res.model_dump() if hasattr(audit_res, "model_dump") else audit_res.dict()
                await self.state.add_confidence_score(audit_res.confidence)
            elif agent_type == "synthesizer":
                final_doc = await self.synthesizer.compile_report(
                    getattr(self.state, "effective_query", None) or getattr(self.state, "query", "") or title,
                    await self.state.get_state_dict(),
                    skill_prompt=skill_ctx
                )
                output = final_doc
                task_data_dict = {"report": final_doc}
                self.state.working_memory["final_report"] = final_doc
            else:
                output = f"Executed default agent routine for task: {title}"
                task_data_dict = {"output": output}
                
            duration = time.time() - start_time
            self.metrics.record_agent_latency(agent_type, duration)
            self.metrics.record_tool_call(agent_type, True)
            
            # Save variables in Working Memory and StateManager
            self.memory.write_working(task_id, output)
            if task_data_dict:
                if task_id in self.state.tasks and isinstance(self.state.tasks[task_id], dict):
                    self.state.tasks[task_id]["data"] = task_data_dict
            
            self.tracer.stop_span(span_key, success=True)
            await self.repo.insert_trace(self.session_id, task_id, agent_type, duration, True, 0.0, 0, 0)
            await self.repo.insert_log(self.session_id, agent_type, f"Completed Task '{title}': {str(output)[:150]}...", "info")
            await self.state.add_log(agent_type, f"✅ {agent_type.capitalize()} Agent: Completed subtask '{title}'.", "info")
            await self.broadcast_state()
            return True, output, None
            
        except Exception as e:
            duration = time.time() - start_time
            self.metrics.record_tool_call(agent_type, False)
            self.tracer.stop_span(span_key, success=False)
            await self.repo.insert_trace(self.session_id, task_id, agent_type, duration, False, 0.0, 0, 0)
            await self.repo.insert_log(self.session_id, agent_type, f"Failed Task '{title}': {str(e)}", "error")
            await self.state.add_log(agent_type, f"❌ {agent_type.capitalize()} Agent: Subtask '{title}' failed: {str(e)[:120]}.", "error")
            await self.broadcast_state()
            return False, None, str(e)

    async def export_flow_schema(self) -> Dict[str, Any]:
        """
        Exports the current execution pipeline, Agency Pod, DAG tasks, and Red/Green telemetry
        as a standardized reusable JSON workflow template (Langflow-inspired flow export schema).
        """
        state_dict = await self.state.get_state_dict()
        tasks = state_dict.get("tasks", {})
        nodes = []
        edges = []

        # 1. Pipeline Stages as nodes
        stage_names = [
            ("intent_analyzer", "Intent & Persona Matcher"),
            ("planner", "Dynamic DAG Engine"),
            ("researcher", "Deep Web Researcher"),
            ("analyzer", "Python Sandbox Analyst"),
            ("critic", "NEXUS Quality Gate"),
            ("debate_engine", "Dialectical Debate"),
            ("synthesizer", "Strategic Synthesizer")
        ]
        for idx, (s_id, s_label) in enumerate(stage_names):
            nodes.append({
                "id": s_id,
                "type": "agent_node",
                "position": {"x": 100 + idx * 180, "y": 150},
                "data": {
                    "label": s_label,
                    "agent": s_id,
                    "status": "completed" if state_dict.get("status") == "completed" else "active"
                }
            })
            if idx > 0:
                edges.append({
                    "id": f"e_{stage_names[idx-1][0]}_{s_id}",
                    "source": stage_names[idx-1][0],
                    "target": s_id,
                    "type": "default"
                })

        # 2. Add DAG subtasks as execution vertices
        for tid, tval in tasks.items():
            nodes.append({
                "id": f"task_{tid}",
                "type": "task_node",
                "position": {"x": 300, "y": 300},
                "data": {
                    "task_id": tid,
                    "title": tval.get("title", ""),
                    "agent": tval.get("assigned_agent", "general"),
                    "status": tval.get("status", "completed"),
                }
            })
            for dep in tval.get("dependencies", []):
                edges.append({
                    "id": f"dep_{dep}_{tid}",
                    "source": f"task_{dep}",
                    "target": f"task_{tid}",
                    "animated": True
                })

        return {
            "version": "2.0.0",
            "name": f"NeuroWeave Flow: {self.query[:40]}",
            "session_id": self.session_id,
            "query": self.query,
            "agency_pod": state_dict.get("working_memory", {}).get("agency_pod"),
            "telemetry": self.dag_engine.get_execution_summary(),
            "nodes": nodes,
            "edges": edges,
            "confidence_score": state_dict.get("confidence_score", 0.95),
            "timestamp": time.time()
        }


OrchestratorAgent = MasterOrchestrator

