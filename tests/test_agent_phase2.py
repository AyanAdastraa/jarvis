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

def test_phase2_simple_request_bypasses_loop():
    mock_provider = MagicMock()
    mock_provider.generate.return_value = {
        "content": "Just a simple hello.",
        "tool_calls": []
    }
    
    agent = Agent(model_provider=mock_provider)
    result = agent.execute_task("hi")
    
    assert result == "Just a simple hello."
    # Should only call generate once
    assert mock_provider.generate.call_count == 1

def test_phase2_one_tool_task_success(test_registry):
    mock_provider = MagicMock()
    
    plan_block = '```json\n{"goal": "do it", "steps": [{"id": 1, "description": "dummy", "status": "pending"}]}\n```'
    tool_block = {
        "content": "",
        "tool_calls": [{"id": "1", "type": "function", "function": {"name": "dummy_tool", "arguments": '{"query": "hello"}'}}]
    }
    reflect_block = '```json\n{"goal_achieved": true, "continue": false}\n```'
    final_response = "All done!"
    
    mock_provider.generate.side_effect = [
        {"content": plan_block, "tool_calls": []},
        tool_block,
        {"content": reflect_block, "tool_calls": []},
        {"content": final_response, "tool_calls": []}
    ]
    
    agent = Agent(model_provider=mock_provider)
    with pytest.MonkeyPatch.context() as m:
        m.setattr("app.agent.registry", test_registry)
        result = agent.execute_task("Do the thing")
        
    assert result == final_response
    assert mock_provider.generate.call_count == 4

def test_phase2_tool_failure_replan(test_registry):
    mock_provider = MagicMock()
    
    plan_block = '```json\n{"goal": "fail it", "steps": [{"id": 1, "description": "dummy", "status": "pending"}]}\n```'
    tool_block = {
        "content": "",
        "tool_calls": [{"id": "1", "type": "function", "function": {"name": "dummy_tool", "arguments": '{"query": "fail"}'}}]
    }
    reflect_block_fail = '```json\n{"goal_achieved": false, "continue": false}\n```'
    replan_block = '```json\n{"goal": "retry", "steps": [{"id": 1, "description": "dummy", "status": "pending"}]}\n```'
    
    mock_provider.generate.side_effect = [
        {"content": plan_block, "tool_calls": []},
        tool_block,
        {"content": reflect_block_fail, "tool_calls": []},
        {"content": replan_block, "tool_calls": []}
    ]
    
    agent = Agent(model_provider=mock_provider, max_iterations=4)
    with pytest.MonkeyPatch.context() as m:
        m.setattr("app.agent.registry", test_registry)
        result = agent.execute_task("Fail it")
        
    assert "thinking limits" in result
    
    calls = mock_provider.generate.call_args_list
    messages = calls[3][0][0]
    
    # Because messages is mutated in place, check if any message has the replan prompt
    assert any("Please output a new PLAN" in m.get("content", "") for m in messages)

def test_phase2_max_replans(test_registry):
    mock_provider = MagicMock()
    
    plan_block = '```json\n{"goal": "fail it", "steps": [{"id": 1, "description": "dummy", "status": "pending"}]}\n```'
    tool_block = {
        "content": "",
        "tool_calls": [{"id": "1", "type": "function", "function": {"name": "dummy_tool", "arguments": '{"query": "fail"}'}}]
    }
    reflect_block_fail = '```json\n{"goal_achieved": false, "continue": false}\n```'
    
    # We want it to hit the replan limit, so we keep giving it a fail reflection
    # 1 plan, 3 replans = 4 reflections + 4 tool calls + 1 initial plan?
    # Actually, we can just return reflect_block_fail over and over, because Agent only checks replans when it sees a reflect block with continue=false.
    # Wait, the Agent expects a PLAN block after a replan!
    # Let's just give it a cycle:
    # 1. PLAN
    # 2. TOOL
    # 3. REFLECT (continue=false) -> Replans (1)
    # 4. PLAN
    # 5. TOOL
    # 6. REFLECT (continue=false) -> Replans (2)
    # 7. PLAN
    # 8. TOOL
    # 9. REFLECT (continue=false) -> Replans (3) -> reaches max!
    
    mock_provider.generate.side_effect = [
        {"content": plan_block, "tool_calls": []},
        tool_block,
        {"content": reflect_block_fail, "tool_calls": []}, # replan 1
        {"content": plan_block, "tool_calls": []},
        tool_block,
        {"content": reflect_block_fail, "tool_calls": []}, # replan 2
        {"content": plan_block, "tool_calls": []},
        tool_block,
        {"content": reflect_block_fail, "tool_calls": []}, # replan 3 -> abort
    ]
    
    agent = Agent(model_provider=mock_provider, max_iterations=20)
    agent.max_replans = 2
    
    result = agent.execute_task("Fail infinitely")
    
    assert "too many issues" in result
