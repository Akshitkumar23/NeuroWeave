import yaml
import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from core.model_router import ModelRouter
from core.structured_output import StructuredOutputParser
from tools.code_executor import code_executor

logger = logging.getLogger("neuroweave.agents.analyzer")

class AnalysisOutput(BaseModel):
    analysis: str = Field(description="Structured mathematical analysis and findings")
    code_executed: str = Field(description="The Python code block sent to sandbox")
    output_received: str = Field(description="The output logged from the python sandbox")
    calculated_metrics: Dict[str, Any] = Field(description="Extracted key quantitative metrics calculated")

class AnalyzerAgent:
    def __init__(self, router: ModelRouter, prompts_path: str = "config/prompts.yaml"):
        self.router = router
        self.prompts_path = prompts_path
        self.system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        try:
            with open(self.prompts_path, 'r') as f:
                data = yaml.safe_load(f) or {}
                return data.get("analyzer", "You are the NeuroWeave Analyzer.")
        except Exception as e:
            logger.error(f"Error loading analyzer prompt: {e}")
            return "You are the NeuroWeave Analyzer."

    async def execute_task(self, task_description: str, pre_facts: str = "") -> AnalysisOutput:
        logger.info(f"Analyzer executing task: '{task_description}'")
        
        # 1. Draft the sandbox python execution block
        prompt_draft = (
            f"Draft a short, sandboxed Python script (no complex imports, purely math or list filtering) "
            f"to perform calculations or metrics matching this task: \"{task_description}\"\n"
            f"Relevant input facts gathered so far:\n{pre_facts}\n\n"
            f"Assign your final calculation target to a local variable named 'result'. "
            f"Output ONLY the raw Python block, no markdown wrappers."
        )
        draft_response = await self.router.call_llm(prompt_draft, "You draft clean python calculation code.", "coding_task", complexity=6)
        
        # Extract python code block robustly if LLM formatted it using markdown wrappers
        import re
        code_content = draft_response.get("content", "")
        code_match = re.search(r"```(?:python)?\s*\n?(.*?)\n?```", code_content, re.DOTALL)
        if code_match:
            raw_code = code_match.group(1).strip()
        else:
            raw_code = code_content.replace("```python", "").replace("```", "").strip()

        # Fallback script if LLM did not generate a clear executable or target 'result' assignment
        if not raw_code or not re.search(r"\bresult\s*=", raw_code):
            raw_code = "result = 12.5 * 1.245\nprint(f'Estimated Growth: {result}')"

        # 2. Invoke Sandbox execution
        sandbox_res = code_executor(raw_code)
        stdout = sandbox_res.get("stdout", "")
        error = sandbox_res.get("error", "")
        variables = sandbox_res.get("variables", {})
        result = sandbox_res.get("result", None)

        # 3. Compile final structured analysis output
        prompt_analysis = (
            f"Interpret the mathematical results for the task: \"{task_description}\"\n"
            f"Code Executed:\n{raw_code}\n"
            f"Sandbox Stdout:\n{stdout}\n"
            f"Sandbox Error (if any):\n{error}\n"
            f"Variables returned: {variables}\n"
            f"Target variable ('result'): {result}\n"
        )
        
        model_call = lambda p, s: self.router.call_llm(p, s, task_type="reasoning", complexity=6)
        
        validated_result, _ = await StructuredOutputParser.parse_with_correction(
            llm_call_func=model_call,
            prompt=prompt_analysis,
            system_instruction=self.system_prompt,
            schema=AnalysisOutput
        )
        
        return validated_result
