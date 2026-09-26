"""
NeuroWeave Intent Analyzer Agent.

This module defines the IntentAnalysis schema (validated using Pydantic v2)
and the IntentAnalyzerAgent, which parses user query intents, checks for
malicious inputs, and provides robust validation with a safe fallback mechanism.
"""

import re
import logging
from typing import List, Any, Optional, Dict
import yaml

from pydantic import BaseModel, Field, field_validator, model_validator
from core.model_router import ModelRouter
from core.structured_output import StructuredOutputParser
from core.skill_loader import get_skill_catalog
from core.persona_manager import get_persona_registry
from security.guardrails import SecurityGuardrails

logger = logging.getLogger("neuroweave.agents.intent_analyzer")


class IntentAnalysis(BaseModel):
    """
    Pydantic schema representing the structural results of intent analysis.
    This model undergoes robust validation against field constraints.
    """

    intent: str = Field(
        description="Detected domain intent (e.g. Research, Analysis, Mathematics, Financial Analysis)"
    )
    complexity: int = Field(
        description="Complexity score of task from 1 to 10"
    )
    needs_web_search: bool = Field(
        description="True if resolving task needs fresh facts search lookup"
    )
    needs_python_exec: bool = Field(
        description="True if task requires mathematics calculations or script runs"
    )
    routing_policy: str = Field(
        description="Appropriate routing policy (simple_task, reasoning_task, coding_task)"
    )
    capabilities: List[str] = Field(
        description="List of system capabilities needed to resolve this request"
    )
    active_skills: List[str] = Field(
        default_factory=list,
        description="List of active domain skills or playbooks matching the query"
    )
    assigned_persona: Optional[str] = Field(
        default=None,
        description="Assigned Agency Specialist persona (e.g. Growth Hacker, Financial Analyst)"
    )
    analysis_dimensions: List[str] = Field(
        default_factory=list,
        description="Target analytical dimensions to explore (e.g. market_sizing, architecture, financial_model, risk_audit)"
    )
    extracted_entities: List[str] = Field(
        default_factory=list,
        description="Named subjects, products, technologies, or entities explicitly identified in query"
    )
    is_quantitative: bool = Field(
        default=False,
        description="True if query involves quantitative numbers, benchmarks, financial valuation, or math models"
    )
    expected_output_type: str = Field(
        default="strategic_brief",
        description="Expected format: strategic_brief, comparative_matrix, financial_model, or technical_blueprint"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        # Handle camelCase mappings from various LLMs
        for k, target in [
            ("domainCategory", "intent"),
            ("domain_category", "intent"),
            ("domain", "intent"),
            ("complexityScore", "complexity"),
            ("complexity_score", "complexity"),
            ("requiredCapabilities", "capabilities"),
            ("required_capabilities", "capabilities"),
            ("targetRoutingPolicy", "routing_policy")
        ]:
            if k in normalized and target not in normalized:
                normalized[target] = normalized[k]
        if "targetRoutingPolicy" in normalized:
            trp = normalized["targetRoutingPolicy"]
            if isinstance(trp, dict):
                normalized.setdefault("routing_policy", trp.get("policy", "reasoning_task"))
                normalized.setdefault("assigned_persona", trp.get("specialistPersona"))
            elif isinstance(trp, str):
                normalized.setdefault("routing_policy", trp)
        if isinstance(normalized.get("routing_policy"), dict):
            rp_dict = normalized["routing_policy"]
            normalized.setdefault("assigned_persona", rp_dict.get("specialistPersona"))
            normalized["routing_policy"] = "reasoning_task"
        if "capabilities" in normalized and isinstance(normalized["capabilities"], list):
            caps = [str(c).lower() for c in normalized["capabilities"]]
            normalized.setdefault("needs_web_search", any("search" in c or "web" in c or "rag" in c for c in caps))
            normalized.setdefault("needs_python_exec", any("python" in c or "calc" in c or "math" in c for c in caps))
        normalized.setdefault("needs_web_search", True)
        normalized.setdefault("needs_python_exec", False)
        normalized.setdefault("routing_policy", "reasoning_task")
        normalized.setdefault("intent", "Research & Analysis")
        normalized.setdefault("complexity", 5)
        normalized.setdefault("capabilities", ["web_search", "rag_retrieval"])
        return normalized

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, v: str) -> str:
        """
        Ensures intent is non-empty, non-whitespace and stripped.
        """
        if not v or not v.strip():
            return "Research & Analysis"
        return v.strip()

    @field_validator("complexity")
    @classmethod
    def validate_complexity(cls, v: int) -> int:
        """
        Ensures the complexity score falls within the valid range of 1 to 10.
        """
        if not (1 <= v <= 10):
            return max(1, min(10, v))
        return v

    @field_validator("routing_policy")
    @classmethod
    def validate_routing_policy(cls, v: str) -> str:
        """
        Standardizes and validates that the routing policy is one of the supported strategies.
        """
        valid_policies = {"simple_task", "reasoning_task", "coding_task"}
        cleaned_policy = v.strip().lower()
        if cleaned_policy not in valid_policies:
            return "reasoning_task"
        return cleaned_policy

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, v: List[str]) -> List[str]:
        """
        Sanitizes elements in the capabilities list, rejecting empty items,
        and defaults to ['general_reasoning'] if the list is empty.
        """
        if not isinstance(v, list):
            raise ValueError("Capabilities must be a list of strings.")
        cleaned = [cap.strip() for cap in v if cap and cap.strip()]
        if not cleaned:
            return ["general_reasoning"]
        return cleaned

    @field_validator("active_skills", "analysis_dimensions", "extracted_entities", mode="before")
    @classmethod
    def validate_string_lists(cls, v: Any) -> List[str]:
        """
        Sanitizes string list fields into clean lists of strings.
        """
        if v is None:
            return []
        if isinstance(v, str):
            return [v.strip()] if v.strip() else []
        if isinstance(v, list):
            return [str(item).strip() for item in v if item and str(item).strip()]
        return []


class IntentAnalyzerAgent:
    """
    Agent responsible for analyzing the domain, complexity, and capabilities
    required to fulfill a user query. Integrates security sanitization and fail-safe recovery.
    """

    def __init__(self, router: ModelRouter, prompts_path: str = "config/prompts.yaml"):
        """
        Initializes the IntentAnalyzerAgent with the given router and prompt config path.
        """
        self.router = router
        self.prompts_path = prompts_path
        self.system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        """
        Loads the system prompt for the intent analyzer from config.
        Falls back to a default prompt on failure.
        """
        try:
            with open(self.prompts_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return data.get("intent_analyzer", "You are the NeuroWeave Intent Analyzer.")
        except Exception as e:
            logger.error(f"Error loading intent prompt: {e}")
            return "You are the NeuroWeave Intent Analyzer."

    async def analyze(self, query: str) -> IntentAnalysis:
        """
        Analyzes the given user query to extract structured intent metadata.
        
        Args:
            query: The raw string query from the user.
            
        Returns:
            An IntentAnalysis Pydantic model containing the validated classification results.
            
        Raises:
            ValueError: If the query is empty or not a valid string.
        """
        # Edge Case: Check for empty, whitespace, or invalid types
        if not query or not isinstance(query, str) or not query.strip():
            logger.error("Intent analysis query validation failed: query is empty or not a string.")
            raise ValueError("User query must be a non-empty string.")

        # Security Guardrail check: Sanitize input query to prevent prompt injection
        sanitized_query = SecurityGuardrails.sanitize_user_query(query)
        if sanitized_query != query:
            logger.warning("Query was modified by Security Guardrails to block injection vectors.")

        logger.info(f"Analyzing user query: '{sanitized_query}'")

        # Match skills from catalog
        matched_skill_names: List[str] = []
        try:
            skill_catalog = get_skill_catalog()
            matched_skills = skill_catalog.match_skills(sanitized_query)
            matched_skill_names = [s.name for s in matched_skills]
        except Exception as e:
            logger.warning(f"Error matching skills in intent analyzer: {e}")

        # Match agency specialist persona
        assigned_persona_name: Optional[str] = None
        try:
            persona_reg = get_persona_registry()
            matched_persona = persona_reg.match_persona(sanitized_query)
            if matched_persona:
                assigned_persona_name = matched_persona.name
        except Exception as e:
            logger.warning(f"Error matching persona in intent analyzer: {e}")

        # 100% Deterministic Intent Analysis & Query Decomposition
        from core.deterministic_engine import (
            detect_query_intent,
            QueryIntent,
            _extract_comparison_dimensions,
            _extract_comparison_entities
        )

        detected_raw = detect_query_intent(sanitized_query)
        q_lower = sanitized_query.lower()

        # Determine quantitative requirements
        is_quant = detected_raw == QueryIntent.QUANTITATIVE or any(
            k in q_lower for k in [
                "calculate", "vram", "sizing", "ratio", "percentile", "cagr", "dcf", "valuation",
                "cap table", "dilution", "ltv", "cac", "arr", "flops", "latency", "throughput",
                "pricing", "cost", "under ", "price", "%", "lakh", "crore", "compound", "grow", "growth"
            ]
        )

        # Extract entities
        entities = _extract_comparison_entities(sanitized_query)
        if not entities or len(entities) < 2:
            if " vs " in q_lower or " versus " in q_lower:
                entities = [e.strip() for e in re.split(r'\s+vs\s+|\s+versus\s+', sanitized_query, flags=re.IGNORECASE) if e.strip()]
            elif " or " in q_lower:
                entities = [e.strip() for e in re.split(r'\s+or\s+', sanitized_query, flags=re.IGNORECASE) if e.strip()]

        # Extract dimensions
        dims = _extract_comparison_dimensions(sanitized_query)
        if not dims:
            dims = ["technical_architecture", "empirical_benchmarks", "comparative_tradeoffs", "risk_mitigation"]
        if is_quant and "quantitative_modeling" not in dims:
            dims.insert(1, "quantitative_modeling")

        # Determine web search need
        needs_search = True
        if detected_raw == QueryIntent.QUANTITATIVE and not any(k in q_lower for k in ["market", "competitor", "industry", "saas"]):
            needs_search = False

        # Determine output type
        if is_quant:
            output_type = "financial_model"
        elif detected_raw in (QueryIntent.COMPARISON, QueryIntent.CONCEPTUAL_COMPARISON):
            output_type = "comparative_matrix"
        elif detected_raw == QueryIntent.CONCEPTUAL:
            output_type = "technical_blueprint"
        else:
            output_type = "strategic_brief"

        intent_label = detected_raw.replace("_", " ").title() if isinstance(detected_raw, str) else "Strategic Analysis"

        return IntentAnalysis(
            intent=intent_label,
            complexity=6 if is_quant or len(entities) > 1 else 4,
            needs_web_search=needs_search,
            needs_python_exec=is_quant,
            routing_policy="reasoning_task" if len(entities) > 1 else ("coding_task" if is_quant else "simple_task"),
            capabilities=["research", "data_analysis", "visualization"] if needs_search else ["data_analysis"],
            active_skills=matched_skill_names,
            assigned_persona=assigned_persona_name,
            analysis_dimensions=dims,
            extracted_entities=entities or [],
            is_quantitative=is_quant,
            expected_output_type=output_type
        )

    async def run(self, query: str) -> Dict[str, Any]:
        """Unified agent execution interface returning structured dictionary."""
        res = await self.analyze(query)
        data = res.model_dump() if hasattr(res, "model_dump") else res.dict()
        return {
            "status": "completed",
            "agent_name": "intent_analyzer",
            "output": f"Intent: {res.intent}, Complexity: {res.complexity}/10, Policy: {res.routing_policy}",
            "data": data
        }

    execute = run
