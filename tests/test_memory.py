import pytest
from services.memory import MemoryService, SecurityViolationError
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

def test_memory_isolation(db_session):
    u1 = User(id="u1")
    u2 = User(id="u2")
    db_session.add_all([u1, u2])
    db_session.commit()
    
    svc = MemoryService(db_session)
    
    svc.save_memory("u1", "fact", "hidden", "user 1 fact")
    svc.save_memory("u2", "fact", "hidden", "user 2 fact")
    
    m1 = svc.search_memory("u1", "hidden")
    assert len(m1) == 1
    assert m1[0].value == "user 1 fact"
    
    m2 = svc.search_memory("u2", "hidden")
    assert len(m2) == 1
    assert m2[0].value == "user 2 fact"

def test_memory_sensitivity(db_session):
    u1 = User(id="u1")
    db_session.add(u1)
    db_session.commit()
    
    svc = MemoryService(db_session)
    
    with pytest.raises(SecurityViolationError):
        svc.save_memory("u1", "fact", "api_key", "my-openai-key")
        
    with pytest.raises(SecurityViolationError):
        svc.save_memory("u1", "fact", "service", "sk-1234567890123456789012")
        
    with pytest.raises(SecurityViolationError):
        svc.save_memory("u1", "fact", "token", "Bearer abcdefg")
        
    # Valid should pass
    svc.save_memory("u1", "fact", "color", "blue")
    assert len(svc.search_memory("u1", "color")) == 1
