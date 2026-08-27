from datetime import datetime, timezone
import json
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from core.db import Base

def now_utc():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime, default=now_utc)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc)
    
    conversations = relationship("Conversation", back_populates="user")
    memories = relationship("Memory", back_populates="user")
    documents = relationship("Document", back_populates="user")

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=now_utc)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc)
    
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    id = Column(String, primary_key=True, index=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String, nullable=False) # user, assistant, tool, system
    content = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=now_utc, index=True)
    metadata_json = Column(Text, default="{}")
    
    conversation = relationship("Conversation", back_populates="messages")

class Memory(Base):
    __tablename__ = "memories"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    category = Column(String, index=True) # preference, fact, project, decision, goal, workflow
    key = Column(String, index=True)
    value = Column(Text, nullable=False)
    importance = Column(Float, default=1.0)
    confidence = Column(Float, default=1.0)
    source = Column(String, nullable=True)
    created_at = Column(DateTime, default=now_utc)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc)
    
    user = relationship("User", back_populates="memories")

class Task(Base):
    __tablename__ = "tasks"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    state = Column(Text, default="{}")
    created_at = Column(DateTime, default=now_utc)

class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    source = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    size = Column(Integer, default=0)
    hash = Column(String, nullable=False, index=True) # SHA-256 for deduplication per user
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=now_utc)
    updated_at = Column(DateTime, default=now_utc, onupdate=now_utc)
    
    user = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_doc_user_hash', 'user_id', 'hash'),
    )

class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id = Column(String, primary_key=True, index=True)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, default="{}")
    
    document = relationship("Document", back_populates="chunks")

class AgentRun(Base):
    __tablename__ = "agent_runs"
    id = Column(String, primary_key=True, index=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, default=now_utc)
