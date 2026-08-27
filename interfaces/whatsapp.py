"""
WhatsApp Interface — Clean abstraction between WhatsApp transport and JARVIS agent.

This module is the bridge. It translates:
    WhatsApp message → JARVIS request
    JARVIS response  → WhatsApp message

It does NOT contain agent reasoning logic. It does NOT bypass permissions.
WhatsApp input is treated as UNTRUSTED input at all times.
"""

import time
import re
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set
from collections import defaultdict
from threading import Lock

from app.config import settings
from app.logger import get_logger
from app.agent import Agent
from services.conversation import ConversationService
from models.db_models import User, Conversation
from sqlalchemy.orm import Session

from interfaces.whatsapp_client import WhatsAppClient

logger = get_logger(__name__)

# ============================================================
# MESSAGE TYPES
# ============================================================

SUPPORTED_MESSAGE_TYPES = {"text"}

KNOWN_MESSAGE_TYPES = {
    "text", "image", "document", "audio", "video",
    "sticker", "location", "interactive", "contacts",
    "reaction", "button", "order", "system",
}

UNSUPPORTED_RESPONSES = {
    "image": "I can process text messages right now. Image analysis support is coming in a future update.",
    "document": "I received your document. Document processing through WhatsApp is not connected yet — "
                "please use the CLI interface to ingest documents for now.",
    "audio": "I can process text messages right now. Voice message support is not enabled yet.",
    "video": "I can process text messages right now. Video processing support is not enabled yet.",
    "sticker": "I see your sticker! I can only process text messages for now.",
    "location": "I received a location, but location processing is not available yet.",
    "interactive": "I can process text messages right now. Interactive message support is not enabled yet.",
    "contacts": "I can process text messages right now. Contact card processing is not enabled yet.",
    "reaction": None,  # Silently ignore reactions — no response needed
    "button": "I can process text messages right now. Button responses are not supported yet.",
    "order": "I can process text messages right now. Order processing is not enabled yet.",
    "system": None,  # Silently ignore system messages
}


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class WhatsAppMessage:
    """Parsed representation of an incoming WhatsApp message."""
    sender_phone: str
    message_id: str
    message_type: str
    text: Optional[str] = None
    timestamp: Optional[str] = None
    sender_name: Optional[str] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def user_id(self) -> str:
        """Deterministic user ID from phone number."""
        return f"whatsapp:{self.sender_phone}"

    @property
    def conversation_id(self) -> str:
        """Deterministic conversation ID — one persistent conversation per WhatsApp user."""
        return f"whatsapp:{self.sender_phone}"


# ============================================================
# PAYLOAD PARSER
# ============================================================

class WebhookParseError(Exception):
    """Raised when the webhook payload is malformed."""
    pass


def mask_phone(phone: str) -> str:
    """Mask a phone number for safe logging: +12345678901 → +12***8901"""
    if not phone or len(phone) <= 6:
        return "***"
    return phone[:3] + "***" + phone[-4:]


def parse_incoming_message(payload: Dict[str, Any]) -> Optional[WhatsAppMessage]:
    """
    Parse a Meta webhook payload and extract the first message.

    Returns None if the payload doesn't contain a user message
    (e.g., status updates, delivery receipts).

    Raises WebhookParseError for structurally invalid payloads.
    """
    if not isinstance(payload, dict):
        raise WebhookParseError("Payload is not a dictionary.")

    # Meta wraps everything in entry[].changes[].value
    entries = payload.get("entry")
    if not entries or not isinstance(entries, list):
        return None  # Could be a status update or echo

    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})

            # Status updates don't have messages
            if "messages" not in value:
                continue

            messages = value.get("messages", [])
            if not messages:
                continue

            msg = messages[0]  # Process one message at a time

            # Extract sender info
            sender_phone = msg.get("from", "")
            message_id = msg.get("id", "")
            message_type = msg.get("type", "unknown")
            timestamp = msg.get("timestamp", "")

            if not sender_phone or not message_id:
                raise WebhookParseError("Message missing 'from' or 'id' field.")

            # Extract sender name from contacts if available
            sender_name = None
            contacts = value.get("contacts", [])
            if contacts:
                profile = contacts[0].get("profile", {})
                sender_name = profile.get("name")

            # Extract text content
            text = None
            if message_type == "text":
                text_obj = msg.get("text", {})
                text = text_obj.get("body", "")

            return WhatsAppMessage(
                sender_phone=sender_phone,
                message_id=message_id,
                message_type=message_type,
                text=text,
                timestamp=timestamp,
                sender_name=sender_name,
                raw_payload=msg,
            )

    return None  # No message found in payload


# ============================================================
# RATE LIMITER
# ============================================================

class RateLimiter:
    """
    Simple sliding-window rate limiter.
    Thread-safe for use with FastAPI's background tasks.
    """

    def __init__(self, max_per_minute: int = 30):
        self.max_per_minute = max_per_minute
        self._timestamps: Dict[str, List[float]] = defaultdict(list)
        self._lock = Lock()

    def is_allowed(self, user_id: str) -> bool:
        """Check if a user is within rate limits."""
        now = time.time()
        window_start = now - 60.0

        with self._lock:
            # Prune old timestamps
            self._timestamps[user_id] = [
                t for t in self._timestamps[user_id] if t > window_start
            ]

            if len(self._timestamps[user_id]) >= self.max_per_minute:
                return False

            self._timestamps[user_id].append(now)
            return True

    def reset(self, user_id: Optional[str] = None):
        """Reset rate limits. If user_id is None, reset all."""
        with self._lock:
            if user_id:
                self._timestamps.pop(user_id, None)
            else:
                self._timestamps.clear()


# ============================================================
# DEDUPLICATION
# ============================================================

class MessageDeduplicator:
    """
    In-memory message ID deduplication to prevent processing
    the same webhook delivery more than once.

    Uses a bounded set to prevent unbounded memory growth.
    """

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._seen: Dict[str, float] = {}
        self._lock = Lock()

    def is_duplicate(self, message_id: str) -> bool:
        """Returns True if this message_id was already seen."""
        with self._lock:
            if message_id in self._seen:
                return True

            # Evict oldest entries if at capacity
            if len(self._seen) >= self.max_size:
                oldest_keys = sorted(self._seen, key=self._seen.get)[:self.max_size // 4]
                for k in oldest_keys:
                    del self._seen[k]

            self._seen[message_id] = time.time()
            return False

    def reset(self):
        with self._lock:
            self._seen.clear()


# ============================================================
# WHATSAPP INTERFACE
# ============================================================

class WhatsAppInterface:
    """
    The main WhatsApp interface for JARVIS.

    This class orchestrates the full message lifecycle:
    1. Validate and parse incoming message
    2. Apply security checks (rate limit, dedup, size)
    3. Ensure user/conversation exist in DB
    4. Route to the existing JARVIS Agent
    5. Send the response back via WhatsApp

    It does NOT contain agent logic. It does NOT bypass permissions.
    """

    def __init__(
        self,
        agent: Agent,
        db_session: Session,
        whatsapp_client: Optional[WhatsAppClient] = None,
        rate_limiter: Optional[RateLimiter] = None,
        deduplicator: Optional[MessageDeduplicator] = None,
    ):
        self.agent = agent
        self.db = db_session
        self.client = whatsapp_client or WhatsAppClient()
        self.rate_limiter = rate_limiter or RateLimiter(
            max_per_minute=settings.whatsapp_rate_limit_per_minute
        )
        self.deduplicator = deduplicator or MessageDeduplicator()
        self.conv_service = ConversationService(db_session)

    def _ensure_user_exists(self, user_id: str) -> None:
        """Create the User row if it doesn't exist yet."""
        existing = self.db.query(User).filter(User.id == user_id).first()
        if not existing:
            user = User(id=user_id)
            self.db.add(user)
            self.db.commit()
            logger.info(f"Created new WhatsApp user: {mask_phone(user_id)}")

    def _ensure_conversation_exists(self, user_id: str, conversation_id: str) -> str:
        """
        Ensure a conversation exists for this WhatsApp user.
        Returns the conversation_id.

        WhatsApp users get ONE persistent conversation (not session-based).
        """
        existing = self.db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()

        if not existing:
            conv = Conversation(
                id=conversation_id,
                user_id=user_id,
                metadata_json='{"source": "whatsapp"}',
            )
            self.db.add(conv)
            self.db.commit()
            logger.info(f"Created new WhatsApp conversation for {mask_phone(user_id)}")

        return conversation_id

    def handle_message(self, message: WhatsAppMessage) -> str:
        """
        Process an incoming WhatsApp message through the full JARVIS pipeline.

        Returns the text response that was sent (or would be sent in mock mode).
        """
        masked_phone = mask_phone(message.sender_phone)

        # --- DEDUPLICATION ---
        if self.deduplicator.is_duplicate(message.message_id):
            logger.info(f"Duplicate message {message.message_id} from {masked_phone}, skipping.")
            return ""

        # --- UNSUPPORTED MESSAGE TYPES ---
        if message.message_type not in SUPPORTED_MESSAGE_TYPES:
            response_text = UNSUPPORTED_RESPONSES.get(message.message_type)

            if message.message_type not in KNOWN_MESSAGE_TYPES:
                response_text = "I received a message type I don't recognize yet. I can currently process text messages."
                logger.warning(f"Unknown message type '{message.message_type}' from {masked_phone}")

            if response_text is None:
                # Silently ignore (e.g., reactions, system messages)
                return ""

            self.client.send_text_message(message.sender_phone, response_text)
            return response_text

        # --- RATE LIMITING ---
        if not self.rate_limiter.is_allowed(message.user_id):
            response_text = "You're sending messages too quickly. Please wait a moment before trying again."
            logger.warning(f"Rate limit exceeded for {masked_phone}")
            self.client.send_text_message(message.sender_phone, response_text)
            return response_text

        # --- INPUT SIZE VALIDATION ---
        text = message.text or ""
        if len(text) > settings.whatsapp_max_message_length:
            response_text = (
                f"Your message is too long ({len(text)} characters). "
                f"Please keep messages under {settings.whatsapp_max_message_length} characters."
            )
            self.client.send_text_message(message.sender_phone, response_text)
            return response_text

        if not text.strip():
            response_text = "I received an empty message. Please send me some text."
            self.client.send_text_message(message.sender_phone, response_text)
            return response_text

        # --- ENSURE USER & CONVERSATION IN DB ---
        user_id = message.user_id
        conversation_id = message.conversation_id

        self._ensure_user_exists(user_id)
        self._ensure_conversation_exists(user_id, conversation_id)

        # --- MARK AS READ ---
        self.client.mark_as_read(message.message_id)

        # --- EXECUTE THROUGH JARVIS AGENT ---
        logger.info(
            f"Processing WhatsApp message from {masked_phone}",
            extra={"message_type": message.message_type, "text_length": len(text)},
        )

        try:
            response_text = self.agent.execute_task(
                user_request=text,
                user_id=user_id,
                conversation_id=conversation_id,
            )
        except Exception as e:
            logger.error(f"Agent error processing WhatsApp message from {masked_phone}", exc_info=True)
            response_text = "I encountered an error processing your request. Please try again."

        # --- SEND RESPONSE ---
        if response_text:
            self.client.send_text_message(message.sender_phone, response_text)

        return response_text or ""
