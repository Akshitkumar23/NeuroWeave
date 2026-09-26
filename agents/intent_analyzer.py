"""
NeuroWeave Intent Analyzer Agent.

This module defines the IntentAnalysis schema (validated using Pydantic v2)
and the IntentAnalyzerAgent, which parses user query intents, checks for
malicious inputs, and provides robust validation with a safe fallback mechanism.
"""

import logging
from typing import List
import yaml

from pydantic import BaseModel, Field, field_validator
from core.model_router import ModelRouter
from core.structured_output import StructuredOutputParser
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

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, v: str) -> str:
        """
        Ensures intent is non-empty, non-whitespace and stripped.
        """
        if not v or not v.strip():
            raise ValueError("Intent description cannot be empty or only whitespace.")
        return v.strip()

    @field_validator("complexity")
    @classmethod
    def validate_complexity(cls, v: int) -> int:
        """
        Ensures the complexity score falls within the valid range of 1 to 10.
        """
        if not (1 <= v <= 10):
            raise ValueError(f"Complexity must be between 1 and 10 inclusive, got {v}")
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
            raise ValueError(f"Routing policy must be one of {valid_policies}, got '{v}'")
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

        prompt = (
            f"Please analyze this user query deeply and fill out the validation schema fields:\n"
            f"Query: \"{sanitized_query}\"\n"
        )

        # Router call using the parser self-correction loops
        model_call = lambda p, s: self.router.call_llm(p, s, task_type="simple_task", complexity=3)

        try:
            validated_result, _ = await StructuredOutputParser.parse_with_correction(
                llm_call_func=model_call,
                prompt=prompt,
                system_instruction=self.system_prompt,
                schema=IntentAnalysis
            )
            return validated_result
        except Exception as e:
            logger.error(
                f"Structured intent parser exhausted retries or failed with error: {e}. "
                "Resorting to robust fallback IntentAnalysis metadata to ensure system uptime."
            )
            # Safe production-grade fallback to prevent pipeline crashes
            return IntentAnalysis(
                intent="General Query",
                complexity=5,
                needs_web_search=True,
                needs_python_exec=False,
                routing_policy="reasoning_task",
                capabilities=["research", "general_reasoning"]
            )
