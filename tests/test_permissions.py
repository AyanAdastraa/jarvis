import pytest
import json
from unittest.mock import MagicMock
from pydantic import BaseModel, Field
from core.permissions import PermissionLevel, requires_confirmation, check_permission
from tools.registry import ToolRegistry, ToolDefinition, PermissionDeniedError
from app.agent import Agent

class DummySchema(BaseModel):
    query: str = Field(..., description="The query string")

def dummy_executor(query: str, user_id: str = None) -> str:
    return f"Result: {query}"

def test_requires_confirmation():
    assert requires_confirmation(PermissionLevel.HIGH_RISK, "Deleting file") is True
    assert requires_confirmation(PermissionLevel.EXTERNAL_COMM, "Sending email") is True
    assert requires_confirmation(PermissionLevel.READ, "Reading file") is False
    assert requires_confirmation(PermissionLevel.MODIFY, "Writing file") is False

def test_check_permission():
    assert check_permission(PermissionLevel.READ, PermissionLevel.MODIFY) is True
    assert check_permission(PermissionLevel.HIGH_RISK, PermissionLevel.MODIFY) is False

def test_agent_tool_permission_enforcement():
    # Setup mock registry and agent
    registry = ToolRegistry()
    
    safe_tool = ToolDefinition("safe_tool", "desc", DummySchema, dummy_executor, PermissionLevel.READ)
    unsafe_tool = ToolDefinition("unsafe_tool", "desc", DummySchema, dummy_executor, PermissionLevel.HIGH_RISK)
    
    registry.register(safe_tool)
    registry.register(unsafe_tool)
    
    mock_provider = MagicMock()
    
    agent = Agent(model_provider=mock_provider)
    
    # Test safe tool execution via agent's private execution method
    with pytest.MonkeyPatch.context() as m:
        m.setattr("app.agent.registry", registry)
        
        # Execute safe tool
        result = agent._execute_tool("safe_tool", {"query": "hello"})
        assert result == "Result: hello"
        
        # Execute unsafe tool, it should return the blocked error message
        result = agent._execute_tool("unsafe_tool", {"query": "hello"})
        assert "Execution of unsafe_tool blocked" in result
        assert "Explicit user confirmation is required" in result
