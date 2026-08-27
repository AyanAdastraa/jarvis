import uuid
import json
from typing import List, Optional
from sqlalchemy.orm import Session
from models.db_models import Conversation, Message

class ConversationService:
    def __init__(self, db: Session):
        self.db = db
        
    def create_conversation(self, user_id: str, metadata: dict = None) -> str:
        conv_id = str(uuid.uuid4())
        conv = Conversation(
            id=conv_id,
            user_id=user_id,
            metadata_json=json.dumps(metadata or {})
        )
        self.db.add(conv)
        self.db.commit()
        return conv_id
        
    def save_message(self, conversation_id: str, role: str, content: str, metadata: dict = None) -> str:
        msg_id = str(uuid.uuid4())
        msg = Message(
            id=msg_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata_json=json.dumps(metadata or {})
        )
        self.db.add(msg)
        self.db.commit()
        return msg_id
        
    def get_history(self, conversation_id: str, limit: int = 50) -> List[Message]:
        # Return in chronological order
        msgs = self.db.query(Message).filter(Message.conversation_id == conversation_id).order_by(Message.timestamp.desc()).limit(limit).all()
        return msgs[::-1]
        
    def verify_ownership(self, user_id: str, conversation_id: str) -> bool:
        conv = self.db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.user_id == user_id).first()
        return conv is not None
