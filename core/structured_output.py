import json
import logging
import re
from typing import Type, Any, Dict, Optional, Callable, Awaitable, Tuple
from pydantic import BaseModel, ValidationError

logger = logging.getLogger("neuroweave.structured_output")

class StructuredOutputParser:
    @staticmethod
    def clean_json_string(raw_text: str) -> str:
        """
        Cleans markdown wrappers like ```json and extract pure JSON contents.
        Handles both object {} and array [] top-level responses from LLM.
        """
        # Remove potential markdown wraps
        cleaned = re.sub(r"^```json\s*", "", raw_text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"^```\s*", "", cleaned.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.IGNORECASE)
        cleaned = cleaned.strip()
        
        # Try to extract a JSON object {}
        start_obj = cleaned.find('{')
        end_obj = cleaned.rfind('}')
        
        # Try to extract a JSON array []
        start_arr = cleaned.find('[')
        end_arr = cleaned.rfind(']')
        
        # Prefer whichever appears first (object or array)
        has_obj = start_obj != -1 and end_obj != -1 and end_obj > start_obj
        has_arr = start_arr != -1 and end_arr != -1 and end_arr > start_arr
        
        if has_obj and has_arr:
            # Take the one that appears first
            if start_obj < start_arr:
                return cleaned[start_obj:end_obj + 1]
            else:
                return cleaned[start_arr:end_arr + 1]
        elif has_obj:
            return cleaned[start_obj:end_obj + 1]
        elif has_arr:
            return cleaned[start_arr:end_arr + 1]
            
        return cleaned

    @classmethod
    async def parse_with_correction(
        cls,
        llm_call_func: Callable[[str, str], Awaitable[Dict[str, Any]]],
        prompt: str,
        system_instruction: str,
        schema: Type[BaseModel],
        max_retries: int = 3
    ) -> Tuple[BaseModel, Dict[str, Any]]:
        """
        Calls LLM, extracts JSON, validates against Pydantic schema, and
        initiates an automated correction cycle on failure.
        """
        current_prompt = prompt
        feedback_notes = ""
        last_metadata = {}

        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                logger.info(f"Structured correction loop attempt {attempt} for schema '{schema.__name__}'.")
                # Append correction instruction to prompt
                current_prompt = (
                    f"{prompt}\n\n"
                    f"### VALIDATION ERROR ON PREVIOUS ATTEMPT:\n{feedback_notes}\n"
                    f"Please correct the output and return a clean, valid JSON block matching the schema strictly."
                )

            # Call Model Router
            response = await llm_call_func(current_prompt, system_instruction)
            if not response.get("success", False):
                # Critical provider fail
                feedback_notes = "API Provider request failed."
                continue

            raw_text = response.get("content", "")
            last_metadata = response.get("metadata", {})
            
            cleaned_json = cls.clean_json_string(raw_text)
            
            try:
                # 1. Parse JSON
                data = json.loads(cleaned_json)
                
                # 2. Validate Pydantic Schema
                validated_model = schema(**data)
                logger.info(f"Successfully validated model '{schema.__name__}' on attempt {attempt}.")
                return validated_model, last_metadata
                
            except json.JSONDecodeError as je:
                feedback_notes = f"Invalid JSON syntax: {str(je)}. Text returned was:\n{raw_text}"
                logger.warning(f"JSONDecodeError on attempt {attempt}: {je}")
            except ValidationError as ve:
                feedback_notes = f"Schema Validation Failures:\n{ve.errors()}"
                logger.warning(f"ValidationError on attempt {attempt}: {ve}")
            except Exception as e:
                feedback_notes = f"Unknown parsing failure: {str(e)}"
                logger.warning(f"Unexpected parsing failure: {e}")

        # Final fallback - instantiate a default empty or partial schema if possible
        logger.error(f"Structured output correction loop exhausted after {max_retries} attempts. Raising error.")
        raise ValueError(f"Failed to generate structured output for {schema.__name__}: {feedback_notes}")

