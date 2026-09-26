import asyncio
import inspect
import logging
from typing import Dict, Any, List, Callable, Optional, Type
from pydantic import BaseModel, ValidationError

logger = logging.getLogger("neuroweave.tool_registry")

class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        allowed_agents: List[str],
        schema: Optional[Type[BaseModel]],
        func: Callable
    ):
        self.name = name
        self.description = description
        self.allowed_agents = allowed_agents
        self.schema = schema
        self.func = func

class ToolRegistry:
    _instance: Optional['ToolRegistry'] = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ToolRegistry, cls).__new__(cls, *args, **kwargs)
            cls._instance.tools = {}
        return cls._instance

    def register_tool(
        self,
        name: str,
        description: str,
        allowed_agents: List[str],
        schema: Optional[Type[BaseModel]] = None
    ):
        """
        Decorator to register a function as a plug-and-play system tool.
        """
        def decorator(func: Callable):
            tool_obj = Tool(
                name=name,
                description=description,
                allowed_agents=allowed_agents,
                schema=schema,
                func=func
            )
            self.tools[name] = tool_obj
            logger.info(f"Registered tool '{name}' allowing agents: {allowed_agents}")
            return func
        return decorator

    def ensure_builtin_tools_registered(self):
        """
        Phase 6.4: Automatically registers all production tools so that registry.execute()
        never fails due to un-imported modules across any runtime entrypoint.
        """
        required_modules = [
            "tools.web_search",
            "tools.code_executor",
            "tools.public_api_catalog",
            "tools.api_executor"
        ]
        import importlib
        for mod_name in required_modules:
            try:
                importlib.import_module(mod_name)
            except Exception as e:
                logger.error(f"Failed to auto-import tool module '{mod_name}': {e}")

    def __init__(self):
        if not hasattr(self, "tools"):
            self.tools: Dict[str, Tool] = {}
        if not hasattr(self, "telemetry_log"):
            self.telemetry_log: List[Dict[str, Any]] = []

    def get_telemetry(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns recorded tool execution telemetry optionally filtered by session_id."""
        if not session_id:
            return list(self.telemetry_log)
        return [t for t in self.telemetry_log if t.get("session_id") == session_id]

    def clear_telemetry(self, session_id: Optional[str] = None):
        """Clears telemetry records."""
        if session_id:
            self.telemetry_log = [t for t in self.telemetry_log if t.get("session_id") != session_id]
        else:
            self.telemetry_log.clear()

    async def execute(
        self,
        tool_name: str,
        agent_name: str,
        args: Dict[str, Any],
        timeout: float = 10.0,
        persona_id: Optional[str] = None,
        persona_bound_tools: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes a registered tool securely, enforcing RBAC access checks against agent
        and persona privileges, recording full telemetry, and preventing bypass.
        """
        import time
        start_time = time.time()
        
        # Ensure tools are loaded if not found
        if tool_name not in self.tools:
            self.ensure_builtin_tools_registered()

        tool = self.tools.get(tool_name)
        args_summary = str(list(args.keys())) if isinstance(args, dict) else "unknown"

        if not tool:
            err_msg = f"Tool '{tool_name}' not found in registry."
            record = {
                "session_id": session_id,
                "task_id": task_id,
                "agent_name": agent_name,
                "persona_id": persona_id,
                "tool_name": tool_name,
                "args_summary": args_summary,
                "start_time": start_time,
                "end_time": time.time(),
                "duration_ms": 0.0,
                "auth_status": "DENIED",
                "success": False,
                "error": err_msg
            }
            self.telemetry_log.append(record)
            return {
                "success": False,
                "status": "TOOL_NOT_FOUND",
                "error": err_msg
            }

        # 1. Enforce RBAC permission checks across Agent Role
        is_authorized = False
        if agent_name == "system":
            is_authorized = True
        elif agent_name in tool.allowed_agents:
            is_authorized = True

        # 1b. Enforce Persona bound_tools restriction if persona provided
        if is_authorized and persona_bound_tools is not None:
            # Map canonical tool names if needed (e.g. python_sandbox -> code_executor)
            allowed_for_persona = set(persona_bound_tools)
            if "python_sandbox" in allowed_for_persona:
                allowed_for_persona.add("code_executor")
            if "code_executor" in allowed_for_persona:
                allowed_for_persona.add("python_sandbox")
            
            if tool_name not in allowed_for_persona:
                is_authorized = False

        if not is_authorized:
            err_msg = (
                f"Security Violation: Agent '{agent_name}'"
                f"{f' (persona: {persona_id})' if persona_id else ''} "
                f"is not authorized to execute tool '{tool_name}'."
            )
            logger.warning(err_msg)
            denial_record = {
                "session_id": session_id,
                "task_id": task_id,
                "agent_name": agent_name,
                "persona_id": persona_id,
                "tool_name": tool_name,
                "args_summary": args_summary,
                "start_time": start_time,
                "end_time": time.time(),
                "duration_ms": round((time.time() - start_time) * 1000, 2),
                "auth_status": "DENIED",
                "success": False,
                "error": err_msg
            }
            self.telemetry_log.append(denial_record)
            return {
                "success": False,
                "status": "TOOL_ACCESS_DENIED",
                "persona_id": persona_id,
                "agent_name": agent_name,
                "tool_name": tool_name,
                "originating_node": task_id or "unknown",
                "timestamp": start_time,
                "error": err_msg
            }

        # 2. Pydantic validation
        if tool.schema:
            try:
                tool.schema(**args)
            except ValidationError as e:
                err_msg = f"Validation Error in tool '{tool_name}': {e.errors()}"
                logger.warning(err_msg)
                return {
                    "success": False,
                    "status": "VALIDATION_ERROR",
                    "error": err_msg
                }

        # 3. Execution wrapper with timeout protection
        logger.info(f"Agent '{agent_name}' invoking tool '{tool_name}' with args: {args_summary}")
        exec_error = None
        result = None
        success = False

        try:
            if inspect.iscoroutinefunction(tool.func):
                future = tool.func(**args)
                result = await asyncio.wait_for(future, timeout=timeout)
            else:
                loop = asyncio.get_running_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: tool.func(**args)),
                    timeout=timeout
                )
            success = True
        except asyncio.TimeoutError:
            exec_error = f"Timeout Error: Tool '{tool_name}' execution exceeded maximum timeout of {timeout}s."
            logger.error(exec_error)
        except Exception as e:
            exec_error = f"Execution Error in tool '{tool_name}': {str(e)}"
            logger.exception(exec_error)

        end_time = time.time()
        duration_ms = round((end_time - start_time) * 1000, 2)
        telemetry_entry = {
            "session_id": session_id,
            "task_id": task_id,
            "agent_name": agent_name,
            "persona_id": persona_id,
            "tool_name": tool_name,
            "args_summary": args_summary,
            "start_time": start_time,
            "end_time": end_time,
            "duration_ms": duration_ms,
            "auth_status": "AUTHORIZED",
            "success": success,
            "error": exec_error
        }
        self.telemetry_log.append(telemetry_entry)

        if not success:
            return {
                "success": False,
                "status": "EXECUTION_ERROR",
                "error": exec_error
            }

        return {
            "success": True,
            "status": "EXECUTED",
            "result": result
        }

# Global registry singleton
registry = ToolRegistry()
registry.ensure_builtin_tools_registered()

