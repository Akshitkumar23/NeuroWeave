import yaml
import os
import logging
from typing import Dict, Any, List

logger = logging.getLogger("neuroweave.permissions")

class AgentPermissionManager:
    def __init__(self, config_path: str = "config/settings.yaml"):
        self.config_path = config_path
        self.permissions = self._load_permissions()

    def _load_permissions(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    data = yaml.safe_load(f) or {}
                    return data.get("permissions", {})
        except Exception as e:
            logger.error(f"Error loading permission settings: {e}")
        return {}

    def is_tool_allowed(self, agent_name: str, tool_name: str) -> bool:
        """
        Enforce RBAC checks on tool activation.
        """
        if agent_name == "system":
            return True
            
        agent_rules = self.permissions.get(agent_name, {})
        allowed_tools = agent_rules.get("allowed_tools", [])
        
        # Tool allowed check
        if tool_name in allowed_tools:
            return True
            
        # Specific capability checking fallbacks
        if tool_name == "web_search" and agent_rules.get("allow_web_search", False):
            return True
        if tool_name == "code_executor" and agent_rules.get("allow_code_exec", False):
            return True
            
        return False

    def can_execute_code(self, agent_name: str) -> bool:
        if agent_name == "system":
            return True
        agent_rules = self.permissions.get(agent_name, {})
        return agent_rules.get("allow_code_exec", False)

    def can_search_web(self, agent_name: str) -> bool:
        if agent_name == "system":
            return True
        agent_rules = self.permissions.get(agent_name, {})
        return agent_rules.get("allow_web_search", False)

    def can_mutate_state(self, agent_name: str) -> bool:
        if agent_name == "system":
            return True
        agent_rules = self.permissions.get(agent_name, {})
        return agent_rules.get("allow_state_mutation", False)
