import pytest
from core.retriever import LexicalRetriever
from services.rag import RagService
from models.db_models import User, Document, DocumentChunk
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

def test_rag_ingest_and_duplicate(db_session, tmp_path):
    user = User(id="u1")
    db_session.add(user)
    db_session.commit()
    
    p = tmp_path / "test.txt"
    p.write_text("This is a rag document")
    
    retriever = LexicalRetriever()
    service = RagService(db_session, retriever)
    
    doc_id = service.ingest_document("u1", str(p))
    
    # Verify it exists
    doc = service.get_document("u1", doc_id)
    assert doc is not None
    assert doc.filename == "test.txt"
    
    # Test duplicate ingestion
    doc_id2 = service.ingest_document("u1", str(p))
    assert doc_id2 == doc_id # Returns existing
    
    # Should only be one document in DB for u1
    assert db_session.query(Document).filter(Document.user_id == "u1").count() == 1

def test_rag_retrieval(db_session, tmp_path):
    user = User(id="u1")
    db_session.add(user)
    db_session.commit()
    
    p = tmp_path / "rag.txt"
    p.write_text("artificial intelligence is cool")
    
    retriever = LexicalRetriever()
    service = RagService(db_session, retriever)
    service.ingest_document("u1", str(p))
    
    chunks = service.retrieve_relevant_chunks("u1", "intelligence")
    assert len(chunks) == 1
    assert "artificial intelligence" in chunks[0][0].content
