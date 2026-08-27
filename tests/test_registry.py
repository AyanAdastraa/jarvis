import pytest
from pydantic import BaseModel, Field
from tools.registry import ToolRegistry, ToolDefinition, PermissionDeniedError
from core.permissions import PermissionLevel

class DummySchema(BaseModel):
    query: str = Field(..., description="The query string")
    count: int = Field(default=1)

def dummy_executor(query: str, count: int = 1) -> str:
    return f"Result for {query} {count}"

def test_tool_registration_and_duplicate():
    registry = ToolRegistry()
    
    tool = ToolDefinition(
        name="dummy_tool",
        description="A dummy tool",
        schema=DummySchema,
        executor=dummy_executor
    )
    
    registry.register(tool)
    assert registry.get_tool("dummy_tool") is not None
    assert registry.get_tool("unknown_tool") is None
    
    # Registering duplicate shouldn't crash, it overwrites
    registry.register(tool)
    assert len(registry.list_tools()) == 1

def test_schema_generation():
    registry = ToolRegistry()
    tool = ToolDefinition("dummy", "desc", DummySchema, dummy_executor)
    registry.register(tool)
    
    schemas = registry.get_openai_tools()
    assert schemas[0]["function"]["name"] == "dummy"
    assert "query" in schemas[0]["function"]["parameters"]["properties"]
    assert "count" in schemas[0]["function"]["parameters"]["properties"]

def test_argument_validation_and_execution():
    tool = ToolDefinition("dummy", "desc", DummySchema, dummy_executor)
    
    # valid
    args = {"query": "hello", "count": 2}
    validated = tool.schema(**args)
    result = tool.executor(**validated.model_dump())
    assert result == "Result for hello 2"
    
    # invalid
    with pytest.raises(ValueError):
        tool.schema(query="hello", count="not_a_number")

def test_permission_denied_exception():
    tool = ToolDefinition(
        "destructive_tool", 
        "desc", 
        schema=DummySchema,
        executor=dummy_executor,
        permission_level=PermissionLevel.HIGH_RISK
    )
    
    validated = tool.schema(query="delete", count=1)
    with pytest.raises(PermissionDeniedError):
        tool.executor(**validated.model_dump())
