from abc import ABC, abstractmethod
from typing import List, Tuple
from sqlalchemy.orm import Session
from models.db_models import DocumentChunk
import re

class Retriever(ABC):
    @abstractmethod
    def retrieve(self, db: Session, query: str, user_id: str, limit: int = 5) -> List[Tuple[DocumentChunk, float]]:
        """Returns a list of (DocumentChunk, score) tuples."""
        pass

class LexicalRetriever(Retriever):
    def retrieve(self, db: Session, query: str, user_id: str, limit: int = 5) -> List[Tuple[DocumentChunk, float]]:
        if not query.strip():
            return []
            
        # Very simple normalization: lowercase, extract alphanumeric tokens
        tokens = [t for t in re.split(r'\W+', query.lower()) if t]
        if not tokens:
            return []
            
        # Get all chunks for the user
        chunks = db.query(DocumentChunk).join(DocumentChunk.document).filter(
            DocumentChunk.document.has(user_id=user_id)
        ).all()
        
        results = []
        for chunk in chunks:
            content_lower = chunk.content.lower()
            # Simple TF (Term Frequency) scoring
            score = 0
            for token in tokens:
                # Count occurrences of token
                score += content_lower.count(token)
                
            if score > 0:
                results.append((chunk, float(score)))
                
        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]
