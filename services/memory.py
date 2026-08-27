import uuid
import re
from typing import List, Optional
from sqlalchemy.orm import Session
from models.db_models import Memory

SENSITIVE_PATTERNS = [
    r"api[_\-]?key",
    r"access[_\-]?token",
    r"password",
    r"private[_\-]?key",
    r"secret",
    r"credential",
    r"auth",
]

SENSITIVE_VALUE_REGEX = re.compile(
    r"(sk-[a-zA-Z0-9]{20,})|"  # OpenAI like keys
    r"(Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*)|"  # Bearer tokens
    r"([a-zA-Z0-9]{32,})",  # Generic long hashes that might be keys
    re.IGNORECASE
)

class SecurityViolationError(Exception):
    pass

def is_sensitive(key: str, value: str) -> bool:
    key_lower = key.lower()
    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, key_lower):
            return True
            
    if SENSITIVE_VALUE_REGEX.search(value):
        return True
        
    return False

class MemoryService:
    def __init__(self, db: Session):
        self.db = db
        
    def save_memory(self, user_id: str, category: str, key: str, value: str, importance: float = 1.0, source: str = None) -> Memory:
        if not user_id:
            raise ValueError("user_id is required")
            
        if is_sensitive(key, value):
            raise SecurityViolationError("Cannot store sensitive information as memory")
            
        # Update if exists, else create
        mem = self.db.query(Memory).filter(Memory.user_id == user_id, Memory.key == key, Memory.category == category).first()
        if mem:
            mem.value = value
            mem.importance = importance
            mem.source = source
        else:
            mem = Memory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                category=category,
                key=key,
                value=value,
                importance=importance,
                source=source
            )
            self.db.add(mem)
            
        self.db.commit()
        self.db.refresh(mem)
        return mem
        
    def get_memory(self, user_id: str, memory_id: str) -> Optional[Memory]:
        if not user_id:
            raise ValueError("user_id is required")
        return self.db.query(Memory).filter(Memory.user_id == user_id, Memory.id == memory_id).first()
        
    def search_memory(self, user_id: str, query: str, category: str = None, limit: int = 10) -> List[Memory]:
        if not user_id:
            raise ValueError("user_id is required")
            
        q = self.db.query(Memory).filter(Memory.user_id == user_id)
        if category:
            q = q.filter(Memory.category == category)
            
        # Basic lexical search on key or value
        if query:
            search_term = f"%{query}%"
            q = q.filter(Memory.key.ilike(search_term) | Memory.value.ilike(search_term))
            
        return q.order_by(Memory.importance.desc()).limit(limit).all()
        
    def delete_memory(self, user_id: str, memory_id: str) -> bool:
        if not user_id:
            raise ValueError("user_id is required")
        mem = self.get_memory(user_id, memory_id)
        if mem:
            self.db.delete(mem)
            self.db.commit()
            return True
        return False
