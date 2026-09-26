import os
import time
import yaml
import logging
import httpx
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("neuroweave.model_router")

class ModelRouter:
    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self.models_registry = self.config.get("models", {})
        self.policies = self.config.get("routing_policies", {})

    def _load_config(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    return yaml.safe_load(f) or {}
            logger.warning(f"Config path {self.config_path} not found. Using default structure.")
        except Exception as e:
            logger.error(f"Error loading settings config: {e}")
        return {}

    def get_api_key(self, provider: str) -> Optional[str]:
        env_var = f"{provider.upper()}_API_KEY"
        key = os.getenv(env_var)
        if not key:
            key = os.getenv("GEMINI_API_KEY") if provider == "gemini" else None
        return key

    def select_best_model(self, task_type: str, complexity: int, latency_sensitive: bool = False) -> Tuple[str, str]:
        """
        Dynamically selects the best model and returns its name and provider.
        Selection factors: task complexity, routing policy, and key availability.
        """
        policy_key = "simple_task"
        if task_type == "coding":
            policy_key = "coding_task"
        elif task_type == "reasoning" or complexity >= 7:
            policy_key = "reasoning_task"

        policy = self.policies.get(policy_key, {})
        primary = policy.get("primary", "mock-local-router")
        fallbacks = policy.get("fallbacks", ["mock-local-router"])

        candidates = [primary] + fallbacks

        for candidate in candidates:
            candidate_info = self.models_registry.get(candidate, {})
            provider = candidate_info.get("provider", "mock")

            if provider in ["mock", "ollama"]:
                return candidate, provider

            api_key = self.get_api_key(provider)
            if api_key:
                logger.info(f"Routed task to {candidate} (Provider: {provider}) based on key availability.")
                return candidate, provider

        logger.info("No active external API keys found. Defaulting to local Ollama fallback.")
        return "ollama-llama3", "ollama"

    async def call_llm(
        self,
        prompt: str,
        system_instruction: str = "",
        task_type: str = "reasoning",
        complexity: int = 5,
        response_schema: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes a call to the best LLM with fallback/retry capabilities.
        """
        selected_model, provider = self.select_best_model(task_type, complexity)
        model_info = self.models_registry.get(selected_model, {})

        cost_in = model_info.get("cost_1k_input", 0.0)
        cost_out = model_info.get("cost_1k_output", 0.0)

        start_time = time.time()

        try:
            if provider == "gemini":
                content = await self._call_gemini_api(selected_model, prompt, system_instruction)
            elif provider == "openai":
                content = await self._call_openai_api(selected_model, prompt, system_instruction)
            elif provider == "groq":
                content = await self._call_groq_api(selected_model, prompt, system_instruction)
            elif provider == "ollama":
                content = await self._call_ollama_api(selected_model, prompt, system_instruction)
            else:
                content = await self._call_ollama_api("ollama-llama3", prompt, system_instruction)

            latency = time.time() - start_time
            prompt_tokens = len(prompt.split()) * 1.3
            resp_tokens = len(content.split()) * 1.3
            est_cost = ((prompt_tokens / 1000) * cost_in) + ((resp_tokens / 1000) * cost_out)

            return {
                "success": True,
                "content": content,
                "metadata": {
                    "model": selected_model,
                    "provider": provider,
                    "latency_sec": latency,
                    "estimated_cost": est_cost,
                    "tokens_input": int(prompt_tokens),
                    "tokens_output": int(resp_tokens),
                    "reason": f"Completed using dynamic capability scoring policy for task: {task_type}"
                }
            }
        except Exception as e:
            logger.error(f"Error calling primary model {selected_model}: {e}. Triggering fallback list.")
            fallback_model = "ollama-llama3"
            fallback_start = time.time()
            content = await self._call_ollama_api(fallback_model, prompt, system_instruction)
            latency = time.time() - fallback_start

            return {
                "success": True,
                "content": content,
                "metadata": {
                    "model": fallback_model,
                    "provider": "ollama",
                    "latency_sec": latency,
                    "estimated_cost": 0.0,
                    "tokens_input": 0,
                    "tokens_output": 0,
                    "reason": f"Fallback triggered due to error: {str(e)}"
                }
            }

    async def _call_gemini_api(self, model: str, prompt: str, system: str) -> str:
        api_key = self.get_api_key("gemini")
        gemini_model_code = model if model else "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model_code}:generateContent?key={api_key}"

        headers = {"Content-Type": "application/json"}
        contents = []
        if system:
            contents.append({"role": "user", "parts": [{"text": f"System Guidelines: {system}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will strictly follow all system constraints and schemas."}]})

        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 4096
            }
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    async def _call_openai_api(self, model: str, prompt: str, system: str) -> str:
        api_key = self.get_api_key("openai")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model if model else "gpt-4o-mini",
            "messages": messages,
            "temperature": 0.2
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def _call_groq_api(self, model: str, prompt: str, system: str) -> str:
        api_key = self.get_api_key("groq")
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "llama3-8b-8192",
            "messages": messages,
            "temperature": 0.2
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]


    async def _call_ollama_api(self, model: str, prompt: str, system: str) -> str:
        url = "http://localhost:11434/api/chat"
        headers = {"Content-Type": "application/json"}
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        actual_model = model.replace("ollama-", "") if model.startswith("ollama-") else model

        payload = {
            "model": actual_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.2
            }
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"]
