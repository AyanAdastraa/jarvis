from typing import Dict, Any, Callable, Type
from pydantic import BaseModel
from core.permissions import PermissionLevel, requires_confirmation
from app.logger import get_logger

logger = get_logger(__name__)

class PermissionDeniedError(Exception):
    pass

class ToolDefinition:
    def __init__(
        self,
        name: str,
        description: str,
        schema: Type[BaseModel],
        executor: Callable,
        permission_level: PermissionLevel = PermissionLevel.READ,
        timeout: int = 30
    ):
        self.name = name
        self.description = description
        self.schema = schema
        self.permission_level = permission_level
        self.timeout = timeout
        
        # Wrap the executor to strictly enforce permissions
        def secure_executor(**kwargs):
            if requires_confirmation(self.permission_level, action_details=self.name):
                logger.warning(f"Tool {self.name} blocked: Requires explicit user confirmation.")
                raise PermissionDeniedError(f"Execution of {self.name} blocked. Explicit user confirmation is required.")
            return executor(**kwargs)
            
        self.executor = secure_executor

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition):
        if tool.name in self._tools:
            logger.warning(f"Tool {tool.name} is already registered. Overwriting.")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get_tool(self, name: str) -> ToolDefinition:
        return self._tools.get(name)

    def list_tools(self) -> Dict[str, ToolDefinition]:
        return self._tools.copy()
        
    def get_openai_tools(self) -> list:
        """
        Export tools into OpenAI's function calling schema format.
        """
        openai_tools = []
        for name, definition in self._tools.items():
            schema_dict = definition.schema.model_json_schema()
            
            # Optional cleanup of Pydantic schema for strict OpenAI compatibility if needed
            if "$defs" in schema_dict:
                # Some models might not support $defs out of the box, but Nemotron should be okay
                pass
                
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": definition.description,
                    "parameters": schema_dict
                }
            })
        return openai_tools

# Global registry instance
registry = ToolRegistry()
