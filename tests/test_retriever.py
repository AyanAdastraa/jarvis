import pytest
from core.retriever import LexicalRetriever
from models.db_models import Document, DocumentChunk, User
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

def test_lexical_retriever_ranking_and_isolation(db_session):
    u1 = User(id="user1")
    u2 = User(id="user2")
    db_session.add_all([u1, u2])
    
    doc1 = Document(id="d1", user_id="user1", filename="f1", hash="1")
    doc2 = Document(id="d2", user_id="user2", filename="f2", hash="2")
    db_session.add_all([doc1, doc2])
    
    # User 1 chunks
    c1 = DocumentChunk(id="c1", document_id="d1", chunk_index=0, content="apples and oranges")
    c2 = DocumentChunk(id="c2", document_id="d1", chunk_index=1, content="apples apples apples")
    
    # User 2 chunks
    c3 = DocumentChunk(id="c3", document_id="d2", chunk_index=0, content="apples")
    
    db_session.add_all([c1, c2, c3])
    db_session.commit()
    
    retriever = LexicalRetriever()
    
    # User 1 search
    results = retriever.retrieve(db_session, "apples", "user1")
    assert len(results) == 2
    # c2 has 3 apples, c1 has 1 apple, so c2 should be ranked higher
    assert results[0][0].id == "c2"
    assert results[0][1] == 3.0
    assert results[1][0].id == "c1"
    assert results[1][1] == 1.0
    
    # User 2 search
    results2 = retriever.retrieve(db_session, "apples", "user2")
    assert len(results2) == 1
    assert results2[0][0].id == "c3"
    
    # Empty query
    assert retriever.retrieve(db_session, "", "user1") == []
