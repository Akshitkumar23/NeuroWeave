"""
NeuroWeave Critic Agent & Hallucination Auditor.

This module defines the CriticReport schema (validated with Pydantic v2)
and the CriticAgent, which audits execution results of subtasks for logical
consistency, calculations coherence, source reference credibility, and errors.
"""

import re
import yaml
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from core.model_router import ModelRouter
from core.structured_output import StructuredOutputParser

logger = logging.getLogger("neuroweave.agents.critic")


class CriticReport(BaseModel):
    """
    Structured Critic Report containing findings from the task execution audit,
    confidence metrics, and subsequent reflection loop directives.
    Accepts both canonical field names and common Gemini alternate names.
    """
    summary: str = Field(
        default="Audit completed.",
        description="Critical review summary auditing logic, mathematical coherence, and factual consistency."
    )
    confidence: float = Field(
        default=0.80,
        description="Calculated confidence score between 0.0 and 1.0 based on findings, errors, and citations."
    )
    issues: List[str] = Field(
        default_factory=list,
        description="Collection of specific gaps, mathematical errors, hallucinations, or contradictions identified."
    )
    action: str = Field(
        default="PROCEED",
        description="Strategic action to take. Must be 'PROCEED' if confidence >= 0.75, otherwise 'REPLAN'."
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_field_names(cls, values: Any) -> Any:
        """Normalize alternate field names that Gemini live model may return."""
        if not isinstance(values, dict):
            return values
        # Normalize confidence
        for alt in ["confidence_score", "score", "confidence_rating", "quality_score"]:
            if alt in values and "confidence" not in values:
                values["confidence"] = values[alt]
                break
        # Normalize summary
        for alt in ["critique_summary", "audit_summary", "review", "evaluation", "critique"]:
            if alt in values and "summary" not in values:
                values["summary"] = values[alt]
                break
        # Normalize issues - also handle list of dicts
        for alt in ["issues_found", "critical_issues", "problems", "errors", "findings", "issues_list"]:
            if alt in values and "issues" not in values:
                values["issues"] = values[alt]
                break
        # If issues is a list of dicts, extract string representations
        if "issues" in values and isinstance(values["issues"], list):
            cleaned_issues = []
            for item in values["issues"]:
                if isinstance(item, str):
                    cleaned_issues.append(item)
                elif isinstance(item, dict):
                    # Extract description/text from dict item
                    for key in ["issue", "description", "problem", "text", "message", "detail"]:
                        if key in item:
                            cleaned_issues.append(str(item[key]))
                            break
                    else:
                        cleaned_issues.append(str(item))
                else:
                    cleaned_issues.append(str(item))
            values["issues"] = cleaned_issues
        # Normalize action
        for alt in ["recommended_action", "next_action", "recommendation"]:
            if alt in values and "action" not in values:
                values["action"] = values[alt]
                break
        return values

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: Any) -> float:
        """
        Dynamically validates that the confidence score is a float strictly bounded within [0.0, 1.0].
        """
        try:
            val = float(v)
        except (ValueError, TypeError):
            raise ValueError(f"Confidence score must be a valid float, got: {v}")
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"Confidence score must be strictly between 0.0 and 1.0, got: {val}")
        return val

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        """
        Validates that the strategic reflection action is standardized and belongs to the allowed options.
        """
        if not isinstance(v, str):
            raise ValueError(f"Action must be a string, got: {type(v)}")
        cleaned = v.strip().upper()
        if cleaned not in ("PROCEED", "REPLAN"):
            raise ValueError(f"Action must be either 'PROCEED' or 'REPLAN', got: '{v}'")
        return cleaned

    @model_validator(mode="after")
    def enforce_reflection_loop_consistency(self) -> "CriticReport":
        """
        Enforces strict logical consistency between confidence score, issues, and action.
        - confidence >= 0.75 MUST trigger action='PROCEED'
        - confidence < 0.75 MUST trigger action='REPLAN'
        - issues present MUST NOT allow perfect confidence 1.0
        - 3 or more issues MUST require confidence < 0.75 (REPLAN)
        """
        expected_action = "PROCEED" if self.confidence >= 0.75 else "REPLAN"
        if self.action != expected_action:
            raise ValueError(
                f"Action and Confidence mismatch: For a confidence score of {self.confidence:.2f}, "
                f"the action MUST be '{expected_action}', but '{self.action}' was provided."
            )

        # Dynamic check: Issues present but confidence is perfect 1.0
        if len(self.issues) > 0 and self.confidence >= 1.0:
            raise ValueError(
                f"Logical conflict: Confidence score cannot be 1.0 when issues are identified. "
                f"Issues found: {self.issues}."
            )

        # Dynamic check: High issue count requires REPLAN
        if len(self.issues) >= 3 and self.confidence >= 0.75:
            raise ValueError(
                f"Logical conflict: High volume of issues ({len(self.issues)} issues) requires a "
                f"confidence score below 0.75 and action='REPLAN'. Current confidence is {self.confidence:.2f}."
            )

        return self


class CriticAgent:
    """
    Critic Agent responsible for auditing intermediate task results, validating
    calculations, checking citation credibility, and providing structural reflection directives.
    """
    def __init__(self, router: ModelRouter, prompts_path: str = "config/prompts.yaml"):
        """
        Initializes the CriticAgent with model router and path to prompt configurations.
        """
        self.router = router
        self.prompts_path = prompts_path
        self.system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        """
        Loads the critic system prompt from the YAML repository, falling back gracefully if missing.
        """
        try:
            with open(self.prompts_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                return data.get("critic", "You are the NeuroWeave Critic Agent.")
        except Exception as e:
            logger.error(f"Error loading critic prompt from '{self.prompts_path}': {e}")
            return "You are the NeuroWeave Critic Agent."

    def _run_programmatic_audits(self, task_output: str, source_references: str, report: CriticReport) -> CriticReport:
        """
        Executes robust programmatic checks on task output to ensure correctness, error detection,
        and citation credibility, dynamically adjusting confidence and reflection action.
        """
        adjusted_confidence = report.confidence
        additional_issues = []

        # Check 1: Empty task output verification
        if not task_output or not task_output.strip():
            additional_issues.append("Prior task execution output was completely empty or null.")
            adjusted_confidence = 0.0

        # Check 2: Code/System Execution Error and Failure Spotting
        error_keywords = [
            "exception", "traceback", "syntaxerror", "nan", "null", "undefined",
            "failed to execute", "runtimeerror", "zerodivisionerror"
        ]
        found_errors = []
        for kw in error_keywords:
            if re.search(rf"\b{re.escape(kw)}\b", task_output.lower()):
                found_errors.append(kw)

        if found_errors:
            additional_issues.append(
                f"Task execution outputs contain explicit error keywords or failure indicators: {found_errors}"
            )
            adjusted_confidence -= 0.30

        # Check 3: Citation Verification
        has_url = bool(re.search(r"https?://\S+", task_output + source_references))
        has_citation = bool(re.search(r"\[\^\d+\]|\[\d+\]", task_output))
        
        if not has_url and not has_citation:
            additional_issues.append(
                "Source credibility warning: No external citations, URL links, or APA reference footnotes "
                "were found in the findings or source references."
            )
            adjusted_confidence -= 0.15

        # Consolidate and deduplicate issues
        final_issues = list(report.issues)
        for issue in additional_issues:
            if issue not in final_issues:
                final_issues.append(issue)

        # Dynamic check and capping:
        # Cap confidence at 0.90 if any issues exist
        if len(final_issues) > 0 and adjusted_confidence >= 1.0:
            adjusted_confidence = 0.90

        # Cap confidence below 0.75 (forcing a REPLAN) if 3 or more issues are found
        if len(final_issues) >= 3 and adjusted_confidence >= 0.75:
            adjusted_confidence = 0.70

        # Clamp between 0.0 and 1.0
        adjusted_confidence = max(0.0, min(1.0, adjusted_confidence))
        final_action = "PROCEED" if adjusted_confidence >= 0.75 else "REPLAN"

        return CriticReport(
            summary=report.summary,
            confidence=round(adjusted_confidence, 2),
            issues=final_issues,
            action=final_action
        )

    async def evaluate_task_output(self, task_title: str, task_output: str, source_references: str = "") -> CriticReport:
        """
        Audits execution results for the given task title by calling LLM reasoning models with
        self-correcting structured output parses, and applying deterministic code-level guardrails.
        """
        logger.info(f"Critic auditing task: '{task_title}'")
        
        prompt = (
            f"Please audit the following execution results for the task: \"{task_title}\"\n\n"
            f"=== EXECUTION OUTPUTS ===\n{task_output}\n\n"
            f"=== SOURCE REFERENCES CITATIONS ===\n{source_references}\n\n"
            f"Audit guidelines:\n"
            f"- Verify calculations are mathematically coherent.\n"
            f"- Spot conversational contradictions or hallucinated assertions.\n"
            f"- Grade source reliability. Deduct score if no credible citations are found.\n"
            f"- Enforce a threshold ceiling: If score < 0.75, action MUST be 'REPLAN'.\n"
            f"- If confidence >= 0.75, action MUST be 'PROCEED'. Do not contradict this."
        )
        
        model_call = lambda p, s: self.router.call_llm(p, s, task_type="reasoning", complexity=7)
        
        try:
            validated_result, _ = await StructuredOutputParser.parse_with_correction(
                llm_call_func=model_call,
                prompt=prompt,
                system_instruction=self.system_prompt,
                schema=CriticReport
            )
            # Apply dynamic code-level post-audits for maximum thoroughness
            final_report = self._run_programmatic_audits(task_output, source_references, validated_result)
            return final_report

        except Exception as e:
            logger.error(
                f"Structured critic parser failed or exhausted retries: {e}. "
                "Evaluating task programmatically to provide a robust fallback report."
            )
            
            # Formulate fallback findings using deterministic checks
            fallback_issues = []
            if not task_output or not task_output.strip():
                fallback_issues.append("Prior task execution output was completely empty or null.")
                fallback_confidence = 0.0
            else:
                # Basic error and citation scans for fallback
                error_keywords = ["exception", "traceback", "syntaxerror", "nan", "null", "undefined", "failed to execute"]
                found_errors = [kw for kw in error_keywords if kw in task_output.lower()]
                if found_errors:
                    fallback_issues.append(f"Task output contains execution error indicators: {found_errors}")
                
                has_url = bool(re.search(r"https?://\S+", task_output + source_references))
                has_cit = bool(re.search(r"\[\^\d+\]|\[\d+\]", task_output))
                if not has_url and not has_cit:
                    fallback_issues.append("Task output lacks credible citations or reference links.")
                
                # Assign deterministic fallback confidence
                if len(fallback_issues) >= 2:
                    fallback_confidence = 0.40
                elif len(fallback_issues) == 1:
                    fallback_confidence = 0.60
                else:
                    fallback_confidence = 0.80

            fallback_action = "PROCEED" if fallback_confidence >= 0.75 else "REPLAN"
            
            return CriticReport(
                summary="Fallback programmatic audit triggered due to structured parser recovery.",
                confidence=fallback_confidence,
                issues=fallback_issues,
                action=fallback_action
            )

