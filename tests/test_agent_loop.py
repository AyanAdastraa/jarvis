import pytest
import json
from unittest.mock import MagicMock
from app.agent import Agent
from tools.registry import ToolRegistry, ToolDefinition
from pydantic import BaseModel, Field

class DummySchema(BaseModel):
    query: str = Field(...)

def dummy_executor(query: str, user_id: str = None) -> str:
    if query == "fail":
        raise ValueError("Simulated failure")
    return f"Success: {query}"

@pytest.fixture
def test_registry():
    registry = ToolRegistry()
    tool = ToolDefinition("dummy_tool", "desc", DummySchema, dummy_executor)
    registry.register(tool)
    return registry

def test_agent_normal_response(test_registry):
    mock_provider = MagicMock()
    mock_provider.generate.return_value = {
        "content": "Here is your answer.",
        "tool_calls": []
    }
    
    agent = Agent(model_provider=mock_provider)
    
    with pytest.MonkeyPatch.context() as m:
        m.setattr("app.agent.registry", test_registry)
        response = agent.execute_task("Hello")
        
    assert response == "Here is your answer."
    assert mock_provider.generate.call_count == 1

def test_agent_tool_call_flow(test_registry):
    mock_provider = MagicMock()
    
    # First response: call a tool
    call_1 = {
        "content": None,
        "tool_calls": [{
            "id": "call_1",
            "name": "dummy_tool",
            "arguments": '{"query": "hello"}'
        }]
    }
    
    # Second response: final answer
    call_2 = {
        "content": "Tool was called.",
        "tool_calls": []
    }
    
    mock_provider.generate.side_effect = [call_1, call_2]
    
    agent = Agent(model_provider=mock_provider)
    
    with pytest.MonkeyPatch.context() as m:
        m.setattr("app.agent.registry", test_registry)
        response = agent.execute_task("Do it")
        
    assert response == "Tool was called."
    assert mock_provider.generate.call_count == 2
    
    # Verify the tool result was passed back to the model
    # (-1 is the assistant's final response, -2 is the REFLECT prompt, -3 is the TOOL observation)
    messages_sent_to_model_in_call_2 = mock_provider.generate.call_args_list[1][0][0]
    assert messages_sent_to_model_in_call_2[-3]["role"] == "tool"
    assert "Success: hello" in messages_sent_to_model_in_call_2[-3]["content"]

def test_agent_tool_failure_flow(test_registry):
    mock_provider = MagicMock()
    
    call_1 = {
        "content": None,
        "tool_calls": [{
            "id": "call_1",
            "name": "dummy_tool",
            "arguments": '{"query": "fail"}'
        }]
    }
    
    call_2 = {
        "content": "I failed.",
        "tool_calls": []
    }
    
    mock_provider.generate.side_effect = [call_1, call_2]
    
    agent = Agent(model_provider=mock_provider)
    
    with pytest.MonkeyPatch.context() as m:
        m.setattr("app.agent.registry", test_registry)
        response = agent.execute_task("Fail it")
        
    assert response == "I failed."
    assert mock_provider.generate.call_count == 2
    
    messages_sent_to_model_in_call_2 = mock_provider.generate.call_args_list[1][0][0]
    assert messages_sent_to_model_in_call_2[-3]["role"] == "tool"
    assert "Simulated failure" in messages_sent_to_model_in_call_2[-3]["content"]

def test_agent_max_iterations(test_registry):
    mock_provider = MagicMock()
    
    # Infinitely return tool calls
    call_infinite = {
        "content": None,
        "tool_calls": [{
            "id": "call_1",
            "name": "dummy_tool",
            "arguments": '{"query": "loop"}'
        }]
    }
    mock_provider.generate.return_value = call_infinite
    
    agent = Agent(model_provider=mock_provider, max_iterations=3)
    
    with pytest.MonkeyPatch.context() as m:
        m.setattr("app.agent.registry", test_registry)
        response = agent.execute_task("Loop it")
        
    assert "reached my maximum thinking limits" in response
    assert mock_provider.generate.call_count == 3
