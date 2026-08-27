import pytest
from core.context import ContextManager
from services.conversation import ConversationService
from services.memory import MemoryService
from services.rag import RagService
from core.retriever import LexicalRetriever
from models.db_models import User, Message
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.db import Base

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_context_limits_and_ordering(db_session):
    user = User(id="u1")
    db_session.add(user)
    db_session.commit()
    
    conv_svc = ConversationService(db_session)
    mem_svc = MemoryService(db_session)
    rag_svc = RagService(db_session, LexicalRetriever())
    
    conv_id = conv_svc.create_conversation("u1")
    
    cm = ContextManager(conv_svc, mem_svc, rag_svc, max_messages=2, max_context_chars=100)
    
    # Add 3 messages
    conv_svc.save_message(conv_id, "user", "msg1")
    conv_svc.save_message(conv_id, "assistant", "msg2")
    conv_svc.save_message(conv_id, "user", "msg3")
    
    messages = cm.assemble_context("u1", conv_id, "latest", system_prompt="System rules")
    
    # Expected: System prompt, then 2 messages (max_messages=2)
    assert len(messages) == 3
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "System rules"
    
    assert messages[1]["content"] == "msg2"
    assert messages[2]["content"] == "msg3"
    
def test_context_char_limit(db_session):
    user = User(id="u1")
    db_session.add(user)
    db_session.commit()
    
    conv_svc = ConversationService(db_session)
    mem_svc = MemoryService(db_session)
    rag_svc = RagService(db_session, LexicalRetriever())
    
    conv_id = conv_svc.create_conversation("u1")
    
    # Max chars 20. 
    cm = ContextManager(conv_svc, mem_svc, rag_svc, max_messages=5, max_context_chars=20)
    
    conv_svc.save_message(conv_id, "user", "short") # 5 chars
    conv_svc.save_message(conv_id, "assistant", "this is way too long to fit") # 27 chars
    conv_svc.save_message(conv_id, "user", "hi") # 2 chars
    
    messages = cm.assemble_context("u1", conv_id, "latest", system_prompt="Sys")
    
    # Sys is 3 chars. "hi" is 2 chars. total 5. Next is 27, skips it.
    assert len(messages) == 2
    assert messages[0]["content"] == "Sys"
    assert messages[1]["content"] == "hi"
