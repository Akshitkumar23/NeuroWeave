import logging
import math
import sys
from typing import Dict, Any
from security.guardrails import SecurityGuardrails
from core.tool_registry import registry

logger = logging.getLogger("neuroweave.code_executor")

@registry.register_tool(
    name="code_executor",
    description="Safely executes Python math scripts or trend calculations in an isolated context.",
    allowed_agents=["analyzer"]
)
def code_executor(code: str, variables: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Safely executes simple math formulas or Python data operations.
    Enforces strict static safety checks and isolates local contexts.
    """
    logger.info("Executing safe code sandbox evaluation.")
    
    # 1. Enforce guardrails block checks
    if not SecurityGuardrails.is_code_safe(code):
        return {
            "success": False,
            "error": "Security Alert: Restricted keywords, import statements, or file IO blocks intercepted."
        }
        
    # Enforce safe local environment variables and limit builtins.
    # To fix Python's exec() scoping behavior where inner functions cannot access module-level
    # variables or imported libraries when globals and locals are separate dictionaries,
    # we merge safe_globals and local variables into a unified execution context dictionary.
    context = {
        "__builtins__": {
            "abs": abs,
            "all": all,
            "any": any,
            "bin": bin,
            "bool": bool,
            "dict": dict,
            "divmod": divmod,
            "enumerate": enumerate,
            "float": float,
            "hex": hex,
            "int": int,
            "isinstance": isinstance,
            "issubclass": issubclass,
            "len": len,
            "list": list,
            "map": map,
            "max": max,
            "min": min,
            "oct": oct,
            "pow": pow,
            "print": print,
            "range": range,
            "repr": repr,
            "round": round,
            "set": set,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "zip": zip
        },
        "math": math
    }
    
    if variables:
        context.update(variables)
        
    # Capture standard stdout
    from io import StringIO
    old_stdout = sys.stdout
    sys.stdout = mystdout = StringIO()
    
    try:
        # 2. Executing sandboxed statement in unified context
        exec(code, context)
        
        output = mystdout.getvalue()
        
        # Clean context of non-serializable variables (e.g. math module, builtins)
        serializable_vars = {}
        for k, v in context.items():
            if k in ("math", "__builtins__") or k.startswith("__"):
                continue
            try:
                # Test serializability
                import json
                json.dumps({k: v})
                serializable_vars[k] = v
            except:
                pass
                
        return {
            "success": True,
            "stdout": output.strip(),
            "variables": serializable_vars,
            "result": context.get("result", None)
        }
        
    except Exception as e:
        err_msg = f"Runtime Sandbox Error: {str(e)}"
        logger.error(err_msg)
        return {
            "success": False,
            "error": err_msg
        }
    finally:
        # Guarantee that standard stdout is always restored safely
        sys.stdout = old_stdout
