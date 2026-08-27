import pytest
from services.conversation import ConversationService
from models.db_models import User
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

def test_conversation_history(db_session):
    u1 = User(id="u1")
    db_session.add(u1)
    db_session.commit()
    
    svc = ConversationService(db_session)
    c1 = svc.create_conversation("u1")
    
    svc.save_message(c1, "user", "msg1")
    svc.save_message(c1, "assistant", "msg2")
    
    history = svc.get_history(c1)
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[0].content == "msg1"
    assert history[1].role == "assistant"
    assert history[1].content == "msg2"
    
def test_conversation_ownership(db_session):
    u1 = User(id="u1")
    u2 = User(id="u2")
    db_session.add_all([u1, u2])
    db_session.commit()
    
    svc = ConversationService(db_session)
    c1 = svc.create_conversation("u1")
    
    assert svc.verify_ownership("u1", c1) is True
    assert svc.verify_ownership("u2", c1) is False
