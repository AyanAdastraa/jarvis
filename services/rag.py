import uuid
import hashlib
from typing import List, Tuple
from sqlalchemy.orm import Session
from models.db_models import Document, DocumentChunk
from core.parser import parse_document, DocumentParseError
from core.chunker import DeterministicChunker
from core.retriever import Retriever

class RagService:
    def __init__(self, db: Session, retriever: Retriever, chunker: DeterministicChunker = None):
        self.db = db
        self.retriever = retriever
        self.chunker = chunker or DeterministicChunker()
        
    def _compute_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
        
    def ingest_document(self, user_id: str, file_path: str, mime_type: str = None) -> str:
        parsed_doc = parse_document(file_path, mime_type)
        
        doc_hash = self._compute_hash(parsed_doc.content)
        
        # Duplicate detection scoped to user
        existing = self.db.query(Document).filter(Document.user_id == user_id, Document.hash == doc_hash).first()
        if existing:
            return existing.id
            
        doc_id = str(uuid.uuid4())
        doc = Document(
            id=doc_id,
            user_id=user_id,
            filename=parsed_doc.filename,
            mime_type=parsed_doc.mime_type,
            size=len(parsed_doc.content.encode('utf-8')),
            hash=doc_hash,
            metadata_json="{}"
        )
        self.db.add(doc)
        
        # Chunking
        chunks_text = self.chunker.chunk_text(parsed_doc.content)
        for i, text in enumerate(chunks_text):
            chunk = DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=doc_id,
                chunk_index=i,
                content=text
            )
            self.db.add(chunk)
            
        self.db.commit()
        return doc_id
        
    def get_document(self, user_id: str, document_id: str) -> Document:
        return self.db.query(Document).filter(Document.id == document_id, Document.user_id == user_id).first()
        
    def search_documents(self, user_id: str, query: str, limit: int = 10) -> List[Document]:
        search_term = f"%{query}%"
        return self.db.query(Document).filter(
            Document.user_id == user_id,
            Document.filename.ilike(search_term)
        ).limit(limit).all()
        
    def retrieve_relevant_chunks(self, user_id: str, query: str, limit: int = 5) -> List[Tuple[DocumentChunk, float]]:
        return self.retriever.retrieve(self.db, query, user_id, limit)
