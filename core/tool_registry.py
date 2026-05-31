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

    async def execute(
        self,
        tool_name: str,
        agent_name: str,
        args: Dict[str, Any],
        timeout: float = 10.0
    ) -> Dict[str, Any]:
        """
        Executes a registered tool securely, enforcing RBAC access checks,
        Pydantic parameter validation, and timeout limits.
        """
        tool = self.tools.get(tool_name)
        if not tool:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' not found in registry."
            }

        # 1. Enforce RBAC permission checks
        if agent_name != "system" and agent_name not in tool.allowed_agents:
            err_msg = f"Security Violation: Agent '{agent_name}' is not authorized to use tool '{tool_name}'."
            logger.warning(err_msg)
            return {
                "success": False,
                "error": err_msg
            }

        # 2. Pydantic validation
        if tool.schema:
            try:
                # Validate inputs
                tool.schema(**args)
            except ValidationError as e:
                err_msg = f"Validation Error in tool '{tool_name}': {e.errors()}"
                logger.warning(err_msg)
                return {
                    "success": False,
                    "error": err_msg
                }

        # 3. Execution wrapper with timeout protection
        logger.info(f"Agent '{agent_name}' invoking tool '{tool_name}' with args: {args}")
        try:
            if inspect.iscoroutinefunction(tool.func):
                future = tool.func(**args)
                result = await asyncio.wait_for(future, timeout=timeout)
            else:
                # Wrap synchronous functions in executor
                loop = asyncio.get_running_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: tool.func(**args)),
                    timeout=timeout
                )
            
            return {
                "success": True,
                "result": result
            }
        except asyncio.TimeoutError:
            err_msg = f"Timeout Error: Tool '{tool_name}' execution exceeded maximum timeout of {timeout}s."
            logger.error(err_msg)
            return {
                "success": False,
                "error": err_msg
            }
        except Exception as e:
            err_msg = f"Execution Error in tool '{tool_name}': {str(e)}"
            logger.exception(err_msg)
            return {
                "success": False,
                "error": err_msg
            }

# Global registry singleton
registry = ToolRegistry()
