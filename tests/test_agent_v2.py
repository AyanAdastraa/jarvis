import pytest
from app.agent import Agent
from core.context import ContextManager
from services.conversation import ConversationService
from services.memory import MemoryService
from services.rag import RagService
from core.retriever import LexicalRetriever
from models.db_models import User
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.db import Base
from tools.registry import ToolRegistry, ToolDefinition
from core.permissions import PermissionLevel
import json

class MockModel:
    def __init__(self, response_queue):
        self.response_queue = response_queue
    def generate(self, messages, tools=None):
        return self.response_queue.pop(0)

import os
import tempfile
from app.config import settings

@pytest.fixture
def db_session():
    # Use a temp file for SQLite so new sessions can see the same data
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    original_url = settings.database_url
    settings.database_url = f"sqlite:///{path}"
    
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    
    settings.database_url = original_url
    os.remove(path)

def test_agent_v2_memory_tool(db_session):
    user = User(id="u1")
    db_session.add(user)
    db_session.commit()
    
    conv_svc = ConversationService(db_session)
    mem_svc = MemoryService(db_session)
    rag_svc = RagService(db_session, LexicalRetriever())
    
    cm = ContextManager(conv_svc, mem_svc, rag_svc)
    
    conv_id = conv_svc.create_conversation("u1")
    
    responses = [
        # Iteration 1: model wants to save memory
        {
            "content": "",
            "tool_calls": [{
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "save_memory",
                    "arguments": json.dumps({
                        "category": "fact",
                        "key": "color",
                        "value": "blue",
                        "importance": 1.0
                    })
                }
            }]
        },
        # Iteration 2: model sees success and responds
        {
            "content": "I saved it.",
            "tool_calls": []
        }
    ]
    
    from unittest.mock import patch
    agent = Agent(MockModel(responses), cm, max_iterations=3)
    import tools.memory
    
    with patch("tools.memory.SessionLocal", return_value=db_session):
        result = agent.execute_task("my favorite color is blue", "u1", conv_id)
        assert result == "I saved it."
        
        # Check DB
        mems = mem_svc.search_memory("u1", "color")
        assert len(mems) == 1
        assert mems[0].value == "blue"

def test_agent_v2_permission_blocked(db_session):
    user = User(id="u1")
    db_session.add(user)
    db_session.commit()
    
    conv_svc = ConversationService(db_session)
    mem_svc = MemoryService(db_session)
    rag_svc = RagService(db_session, LexicalRetriever())
    
    cm = ContextManager(conv_svc, mem_svc, rag_svc)
    
    conv_id = conv_svc.create_conversation("u1")
    
    responses = [
        # Iteration 1: model calls high permission tool without confirmation
        {
            "content": "",
            "tool_calls": [{
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "delete_memory",
                    "arguments": json.dumps({
                        "memory_id": "fake_id"
                    })
                }
            }]
        },
        # Iteration 2: model sees error and apologizes
        {
            "content": "I don't have permission.",
            "tool_calls": []
        }
    ]
    
    agent = Agent(MockModel(responses), cm, max_iterations=3)
    import tools.memory
    from tools.registry import registry
    tool = registry.get_tool("delete_memory")
    original_level = tool.permission_level
    tool.permission_level = PermissionLevel.HIGH_RISK
    
    try:
        result = agent.execute_task("delete my memory", "u1", conv_id)
        assert result == "I don't have permission."
        history = conv_svc.get_history(conv_id)
        # Check that the tool result was an error
        tool_msgs = [m for m in history if m.role == 'tool']
        assert len(tool_msgs) == 1
        assert "blocked" in tool_msgs[0].content or "PermissionDeniedError" in tool_msgs[0].content
    finally:
        tool.permission_level = original_level
