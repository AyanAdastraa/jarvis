"""
Comprehensive tests for the JARVIS WhatsApp interface.

Covers all 16 required test cases:
 1. Webhook verification success
 2. Webhook verification failure
 3. Parsing text messages
 4. Malformed payloads
 5. Unsupported message types
 6. Mock send_message
 7. Meta client request construction
 8. Missing credentials
 9. Mock mode does not call Meta
10. Agent receives correct user_id
11. Agent receives correct conversation_id
12. Permission system is not bypassed
13. Secrets are not logged
14. Oversized messages are rejected
15. Duplicate message IDs handled
16. API errors handled without crashing

NO real WhatsApp API calls anywhere.
"""

import os
import json
import time
import tempfile
import logging
from io import StringIO
from unittest.mock import patch, MagicMock, PropertyMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from core.db import Base
from models.db_models import User

from interfaces.whatsapp import (
    WhatsAppInterface,
    WhatsAppMessage,
    RateLimiter,
    MessageDeduplicator,
    parse_incoming_message,
    WebhookParseError,
    mask_phone,
    SUPPORTED_MESSAGE_TYPES,
    UNSUPPORTED_RESPONSES,
)
from interfaces.whatsapp_client import WhatsAppClient, WhatsAppAPIError


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def db_session():
    """Create a fresh in-memory database for each test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()
    os.remove(path)


@pytest.fixture
def mock_agent():
    """Mock agent that returns a fixed response."""
    agent = MagicMock()
    agent.execute_task.return_value = "Hello from JARVIS!"
    return agent


@pytest.fixture
def mock_client():
    """WhatsApp client in mock mode."""
    return WhatsAppClient(mock_mode=True)


@pytest.fixture
def whatsapp_interface(db_session, mock_agent, mock_client):
    """Fully assembled WhatsApp interface with mocked agent."""
    # Create the mock user in DB
    user = User(id="whatsapp:+1234567890")
    db_session.add(user)
    db_session.commit()

    return WhatsAppInterface(
        agent=mock_agent,
        db_session=db_session,
        whatsapp_client=mock_client,
    )


def _make_text_message(
    text="Hello JARVIS",
    sender="+1234567890",
    msg_id="wamid.test123",
):
    """Helper to create a WhatsAppMessage for tests."""
    return WhatsAppMessage(
        sender_phone=sender,
        message_id=msg_id,
        message_type="text",
        text=text,
        timestamp="1234567890",
        sender_name="Test User",
    )


def _make_meta_webhook_payload(
    text="Hello JARVIS",
    sender="1234567890",
    msg_id="wamid.test123",
    msg_type="text",
):
    """Build a realistic Meta webhook JSON payload."""
    message_data = {
        "from": sender,
        "id": msg_id,
        "timestamp": "1234567890",
        "type": msg_type,
    }

    if msg_type == "text":
        message_data["text"] = {"body": text}

    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "ENTRY_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "15551234567",
                        "phone_number_id": "PHONE_NUMBER_ID",
                    },
                    "contacts": [{
                        "profile": {"name": "Test User"},
                        "wa_id": sender,
                    }],
                    "messages": [message_data],
                },
                "field": "messages",
            }],
        }],
    }


# ============================================================
# TEST 1: WEBHOOK VERIFICATION SUCCESS
# ============================================================

def test_webhook_verification_success():
    """GET /webhook/whatsapp with correct token returns the challenge."""
    from fastapi.testclient import TestClient

    with patch.object(settings, "whatsapp_verify_token", "my_secret_token"):
        # Re-import to get fresh app with patched settings
        from interfaces.webhook import app
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/webhook/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "my_secret_token",
                "hub.challenge": "challenge_12345",
            },
        )

        assert response.status_code == 200
        assert response.text == "challenge_12345"


# ============================================================
# TEST 2: WEBHOOK VERIFICATION FAILURE
# ============================================================

def test_webhook_verification_failure():
    """GET /webhook/whatsapp with wrong token returns 403."""
    from fastapi.testclient import TestClient

    with patch.object(settings, "whatsapp_verify_token", "my_secret_token"):
        from interfaces.webhook import app
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get(
            "/webhook/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "challenge_12345",
            },
        )

        assert response.status_code == 403


def test_webhook_verification_missing_mode():
    """GET /webhook/whatsapp without hub.mode fails."""
    from fastapi.testclient import TestClient
    from interfaces.webhook import app
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(
        "/webhook/whatsapp",
        params={
            "hub.verify_token": "any_token",
            "hub.challenge": "challenge_12345",
        },
    )

    assert response.status_code == 403


# ============================================================
# TEST 3: PARSING TEXT MESSAGES
# ============================================================

def test_parse_text_message():
    """parse_incoming_message correctly extracts text from Meta payload."""
    payload = _make_meta_webhook_payload(text="Hello JARVIS", sender="1234567890")

    msg = parse_incoming_message(payload)

    assert msg is not None
    assert msg.sender_phone == "1234567890"
    assert msg.message_type == "text"
    assert msg.text == "Hello JARVIS"
    assert msg.message_id == "wamid.test123"
    assert msg.sender_name == "Test User"
    assert msg.user_id == "whatsapp:1234567890"
    assert msg.conversation_id == "whatsapp:1234567890"


def test_parse_message_with_no_contacts():
    """Message without contacts section still parses."""
    payload = _make_meta_webhook_payload()
    # Remove contacts
    del payload["entry"][0]["changes"][0]["value"]["contacts"]

    msg = parse_incoming_message(payload)
    assert msg is not None
    assert msg.sender_name is None
    assert msg.text == "Hello JARVIS"


# ============================================================
# TEST 4: MALFORMED PAYLOADS
# ============================================================

def test_parse_malformed_payload_not_dict():
    """Non-dict payload raises WebhookParseError."""
    with pytest.raises(WebhookParseError):
        parse_incoming_message("not a dict")


def test_parse_empty_payload():
    """Empty dict returns None (no message)."""
    result = parse_incoming_message({})
    assert result is None


def test_parse_status_update_payload():
    """Status update payload (no messages) returns None."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "statuses": [{"id": "wamid.xyz", "status": "delivered"}],
                },
                "field": "messages",
            }],
        }],
    }
    result = parse_incoming_message(payload)
    assert result is None


def test_parse_message_missing_sender():
    """Message without 'from' field raises WebhookParseError."""
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{"id": "msg1", "type": "text", "text": {"body": "hi"}}],
                },
            }],
        }],
    }
    with pytest.raises(WebhookParseError, match="'from' or 'id'"):
        parse_incoming_message(payload)


# ============================================================
# TEST 5: UNSUPPORTED MESSAGE TYPES
# ============================================================

def test_unsupported_message_type_image(whatsapp_interface):
    """Image messages get a polite rejection, not a crash."""
    msg = WhatsAppMessage(
        sender_phone="+1234567890",
        message_id="wamid.img_001",
        message_type="image",
    )
    response = whatsapp_interface.handle_message(msg)
    assert "text messages" in response.lower()
    # Agent should NOT be called
    whatsapp_interface.agent.execute_task.assert_not_called()


def test_unsupported_message_type_document(whatsapp_interface):
    """Document messages inform user about the limitation."""
    msg = WhatsAppMessage(
        sender_phone="+1234567890",
        message_id="wamid.doc_001",
        message_type="document",
    )
    response = whatsapp_interface.handle_message(msg)
    assert "document" in response.lower()
    assert "not connected yet" in response.lower()


def test_unsupported_message_type_audio(whatsapp_interface):
    """Audio messages get a polite rejection."""
    msg = WhatsAppMessage(
        sender_phone="+1234567890",
        message_id="wamid.audio_001",
        message_type="audio",
    )
    response = whatsapp_interface.handle_message(msg)
    assert "text messages" in response.lower()


def test_reaction_silently_ignored(whatsapp_interface):
    """Reaction messages are silently ignored — no response sent."""
    msg = WhatsAppMessage(
        sender_phone="+1234567890",
        message_id="wamid.react_001",
        message_type="reaction",
    )
    response = whatsapp_interface.handle_message(msg)
    assert response == ""


def test_unknown_message_type(whatsapp_interface):
    """Completely unknown message types get a generic response."""
    msg = WhatsAppMessage(
        sender_phone="+1234567890",
        message_id="wamid.unknown_001",
        message_type="alien_transmission",
    )
    response = whatsapp_interface.handle_message(msg)
    assert "text messages" in response.lower()


# ============================================================
# TEST 6: MOCK SEND_MESSAGE
# ============================================================

def test_mock_send_message():
    """Mock mode client logs but doesn't make HTTP calls."""
    client = WhatsAppClient(mock_mode=True)
    result = client.send_text_message("+1234567890", "Test message")

    assert result["mock"] is True
    assert "messages" in result
    assert result["contacts"][0]["wa_id"] == "+1234567890"


def test_mock_send_document():
    """Mock mode client handles document messages."""
    client = WhatsAppClient(mock_mode=True)
    result = client.send_document_message(
        "+1234567890",
        "https://example.com/doc.pdf",
        caption="Test doc",
        filename="report.pdf",
    )

    assert result["mock"] is True


def test_mock_mark_as_read():
    """Mock mode client handles read receipts."""
    client = WhatsAppClient(mock_mode=True)
    result = client.mark_as_read("wamid.test123")
    assert result["mock"] is True
    assert result["success"] is True


# ============================================================
# TEST 7: META CLIENT REQUEST CONSTRUCTION
# ============================================================

def test_text_message_payload():
    """Verify the payload structure matches Meta's API spec."""
    client = WhatsAppClient(mock_mode=True)

    # Intercept the payload sent to _send_request
    payloads = []
    original = client._send_request

    def capture_payload(payload):
        payloads.append(payload)
        return original(payload)

    client._send_request = capture_payload
    client.send_text_message("+1234567890", "Hello!")

    assert len(payloads) == 1
    p = payloads[0]
    assert p["messaging_product"] == "whatsapp"
    assert p["recipient_type"] == "individual"
    assert p["to"] == "+1234567890"
    assert p["type"] == "text"
    assert p["text"]["body"] == "Hello!"
    assert p["text"]["preview_url"] is False


def test_document_message_payload():
    """Verify document payload structure."""
    client = WhatsAppClient(mock_mode=True)

    payloads = []
    original = client._send_request

    def capture_payload(payload):
        payloads.append(payload)
        return original(payload)

    client._send_request = capture_payload
    client.send_document_message(
        "+1234567890",
        "https://example.com/doc.pdf",
        caption="My Report",
        filename="report.pdf",
    )

    p = payloads[0]
    assert p["type"] == "document"
    assert p["document"]["link"] == "https://example.com/doc.pdf"
    assert p["document"]["caption"] == "My Report"
    assert p["document"]["filename"] == "report.pdf"


def test_text_message_truncation():
    """Messages over 4096 chars are truncated."""
    client = WhatsAppClient(mock_mode=True)

    payloads = []
    original = client._send_request

    def capture_payload(payload):
        payloads.append(payload)
        return original(payload)

    client._send_request = capture_payload
    long_text = "x" * 5000
    client.send_text_message("+1234567890", long_text)

    body = payloads[0]["text"]["body"]
    assert len(body) <= 4096
    assert body.endswith("[…]")


# ============================================================
# TEST 8: MISSING CREDENTIALS
# ============================================================

def test_live_mode_no_token():
    """Live mode with no access token warns on init."""
    with patch.object(settings, "whatsapp_access_token", ""):
        client = WhatsAppClient(mock_mode=False, access_token="")
        with pytest.raises(WhatsAppAPIError, match="401"):
            client.send_text_message("+1234567890", "test")


def test_live_mode_no_phone_number_id():
    """Live mode with no phone_number_id raises error."""
    client = WhatsAppClient(
        mock_mode=False,
        access_token="valid_token",
        phone_number_id="",
    )
    with pytest.raises(WhatsAppAPIError, match="401"):
        client.send_text_message("+1234567890", "test")


# ============================================================
# TEST 9: MOCK MODE DOES NOT CALL META
# ============================================================

def test_mock_mode_no_http_calls():
    """Verify mock mode never makes actual HTTP requests."""
    client = WhatsAppClient(mock_mode=True)

    with patch("httpx.Client") as mock_httpx:
        client.send_text_message("+1234567890", "Test")
        mock_httpx.assert_not_called()


def test_mock_mode_no_http_for_documents():
    """Verify mock mode never makes HTTP calls for documents."""
    client = WhatsAppClient(mock_mode=True)

    with patch("httpx.Client") as mock_httpx:
        client.send_document_message("+1234567890", "https://example.com/doc.pdf")
        mock_httpx.assert_not_called()


# ============================================================
# TEST 10: AGENT RECEIVES CORRECT USER_ID
# ============================================================

def test_agent_receives_correct_user_id(whatsapp_interface):
    """Agent is called with deterministic user_id based on phone."""
    msg = _make_text_message(sender="+1234567890")
    whatsapp_interface.handle_message(msg)

    whatsapp_interface.agent.execute_task.assert_called_once()
    call_args = whatsapp_interface.agent.execute_task.call_args
    assert call_args.kwargs["user_id"] == "whatsapp:+1234567890"


def test_different_phones_get_different_user_ids(whatsapp_interface):
    """Different phone numbers produce different user_ids."""
    msg1 = _make_text_message(sender="+1111111111", msg_id="msg1")
    msg2 = _make_text_message(sender="+2222222222", msg_id="msg2")

    whatsapp_interface.handle_message(msg1)
    whatsapp_interface.handle_message(msg2)

    calls = whatsapp_interface.agent.execute_task.call_args_list
    assert calls[0].kwargs["user_id"] == "whatsapp:+1111111111"
    assert calls[1].kwargs["user_id"] == "whatsapp:+2222222222"


# ============================================================
# TEST 11: AGENT RECEIVES CORRECT CONVERSATION_ID
# ============================================================

def test_agent_receives_correct_conversation_id(whatsapp_interface):
    """Agent is called with deterministic conversation_id."""
    msg = _make_text_message(sender="+1234567890")
    whatsapp_interface.handle_message(msg)

    call_args = whatsapp_interface.agent.execute_task.call_args
    assert call_args.kwargs["conversation_id"] == "whatsapp:+1234567890"


def test_same_phone_same_conversation(whatsapp_interface):
    """Multiple messages from same phone use the same conversation_id."""
    msg1 = _make_text_message(msg_id="msg1")
    msg2 = _make_text_message(msg_id="msg2")

    whatsapp_interface.handle_message(msg1)
    whatsapp_interface.handle_message(msg2)

    calls = whatsapp_interface.agent.execute_task.call_args_list
    assert calls[0].kwargs["conversation_id"] == calls[1].kwargs["conversation_id"]


# ============================================================
# TEST 12: PERMISSION SYSTEM NOT BYPASSED
# ============================================================

def test_permission_system_intact(db_session):
    """
    WhatsApp messages go through the real permission system.

    HIGH_RISK tools should still be blocked even when invoked
    through WhatsApp. We verify this by checking the existing
    ToolRegistry wrapping behavior.
    """
    from tools.registry import registry, PermissionDeniedError
    from core.permissions import PermissionLevel

    # Verify delete_file is registered as HIGH_RISK
    delete_tool = registry.get_tool("delete_file")
    assert delete_tool is not None
    assert delete_tool.permission_level == PermissionLevel.HIGH_RISK

    # Attempting to execute should raise PermissionDeniedError
    with pytest.raises(PermissionDeniedError):
        delete_tool.executor(path="some_file.txt")


def test_whatsapp_uses_existing_agent(whatsapp_interface, mock_agent):
    """WhatsApp interface uses the injected agent, not a new one."""
    msg = _make_text_message()
    whatsapp_interface.handle_message(msg)

    # The mock_agent.execute_task was called, proving we use the existing agent
    mock_agent.execute_task.assert_called_once()


# ============================================================
# TEST 13: SECRETS NOT LOGGED
# ============================================================

def test_phone_masking():
    """Phone numbers are properly masked."""
    assert mask_phone("+12345678901") == "+12***8901"
    assert mask_phone("+1234") == "***"
    assert mask_phone("") == "***"
    assert mask_phone("+911234567890") == "+91***7890"


def test_client_masks_phone_in_logs():
    """WhatsApp client masks phone numbers when logging."""
    client = WhatsAppClient(mock_mode=True)
    masked = client._mask_phone("+12345678901")
    assert "2345678" not in masked
    assert masked.startswith("+12")
    assert masked.endswith("8901")


def test_secrets_not_in_mock_response():
    """Mock responses don't contain access tokens or secrets."""
    client = WhatsAppClient(
        mock_mode=True,
        access_token="super_secret_token_xyz",
    )
    result = client.send_text_message("+1234567890", "test")
    result_str = json.dumps(result)
    assert "super_secret_token_xyz" not in result_str


# ============================================================
# TEST 14: OVERSIZED MESSAGES REJECTED
# ============================================================

def test_oversized_message_rejected(whatsapp_interface):
    """Messages exceeding the configured limit are rejected."""
    long_text = "x" * (settings.whatsapp_max_message_length + 100)
    msg = _make_text_message(text=long_text)

    response = whatsapp_interface.handle_message(msg)

    assert "too long" in response.lower()
    # Agent should NOT be called
    whatsapp_interface.agent.execute_task.assert_not_called()


def test_empty_message_rejected(whatsapp_interface):
    """Empty text messages are rejected."""
    msg = _make_text_message(text="   ")
    response = whatsapp_interface.handle_message(msg)

    assert "empty" in response.lower()
    whatsapp_interface.agent.execute_task.assert_not_called()


# ============================================================
# TEST 15: DUPLICATE MESSAGE IDS HANDLED
# ============================================================

def test_duplicate_message_deduplication(whatsapp_interface):
    """Same message_id is processed only once."""
    msg1 = _make_text_message(msg_id="wamid.same_id")
    msg2 = _make_text_message(msg_id="wamid.same_id")

    response1 = whatsapp_interface.handle_message(msg1)
    response2 = whatsapp_interface.handle_message(msg2)

    assert response1 != ""  # First one processed
    assert response2 == ""  # Second one skipped
    assert whatsapp_interface.agent.execute_task.call_count == 1


def test_deduplicator_unit():
    """MessageDeduplicator correctly identifies duplicates."""
    dedup = MessageDeduplicator(max_size=100)

    assert dedup.is_duplicate("msg1") is False  # First time
    assert dedup.is_duplicate("msg1") is True   # Duplicate
    assert dedup.is_duplicate("msg2") is False  # New message


def test_deduplicator_eviction():
    """MessageDeduplicator evicts old entries when at capacity."""
    dedup = MessageDeduplicator(max_size=4)

    for i in range(4):
        dedup.is_duplicate(f"msg_{i}")

    assert len(dedup._seen) == 4

    # Adding one more should trigger eviction
    dedup.is_duplicate("msg_new")
    assert len(dedup._seen) <= 4


# ============================================================
# TEST 16: API ERRORS HANDLED WITHOUT CRASHING
# ============================================================

def test_agent_error_returns_graceful_response(db_session):
    """If the agent throws, the interface returns a graceful error."""
    agent = MagicMock()
    agent.execute_task.side_effect = Exception("Model exploded!")

    user = User(id="whatsapp:+1234567890")
    db_session.add(user)
    db_session.commit()

    interface = WhatsAppInterface(
        agent=agent,
        db_session=db_session,
        whatsapp_client=WhatsAppClient(mock_mode=True),
    )

    msg = _make_text_message()
    response = interface.handle_message(msg)

    assert "error" in response.lower()
    assert "try again" in response.lower()


def test_whatsapp_api_error_class():
    """WhatsAppAPIError has useful attributes."""
    error = WhatsAppAPIError(429, "Rate limited")
    assert error.status_code == 429
    assert "429" in str(error)
    assert "Rate limited" in str(error)


# ============================================================
# RATE LIMITER TESTS
# ============================================================

def test_rate_limiter_allows_within_limit():
    """Rate limiter allows messages within the limit."""
    rl = RateLimiter(max_per_minute=5)

    for _ in range(5):
        assert rl.is_allowed("user1") is True


def test_rate_limiter_blocks_over_limit():
    """Rate limiter blocks messages exceeding the limit."""
    rl = RateLimiter(max_per_minute=3)

    for _ in range(3):
        rl.is_allowed("user1")

    assert rl.is_allowed("user1") is False


def test_rate_limiter_per_user():
    """Rate limiter tracks users independently."""
    rl = RateLimiter(max_per_minute=2)

    rl.is_allowed("user1")
    rl.is_allowed("user1")
    assert rl.is_allowed("user1") is False

    # Different user still allowed
    assert rl.is_allowed("user2") is True


def test_rate_limiter_reset():
    """Rate limiter can be reset."""
    rl = RateLimiter(max_per_minute=1)
    rl.is_allowed("user1")
    assert rl.is_allowed("user1") is False

    rl.reset("user1")
    assert rl.is_allowed("user1") is True


def test_rate_limit_applied_in_interface(whatsapp_interface):
    """Interface applies rate limiting to excessive messages."""
    # Set very low limit
    whatsapp_interface.rate_limiter = RateLimiter(max_per_minute=2)

    msg1 = _make_text_message(msg_id="m1")
    msg2 = _make_text_message(msg_id="m2")
    msg3 = _make_text_message(msg_id="m3")

    whatsapp_interface.handle_message(msg1)
    whatsapp_interface.handle_message(msg2)
    response = whatsapp_interface.handle_message(msg3)

    assert "too quickly" in response.lower()
    assert whatsapp_interface.agent.execute_task.call_count == 2


# ============================================================
# WEBHOOK POST ENDPOINT TESTS
# ============================================================

def test_webhook_post_returns_200():
    """POST /webhook/whatsapp always returns 200 to acknowledge receipt."""
    from fastapi.testclient import TestClient
    from interfaces.webhook import app

    client = TestClient(app, raise_server_exceptions=False)
    payload = _make_meta_webhook_payload()

    response = client.post("/webhook/whatsapp", json=payload)
    assert response.status_code == 200


def test_webhook_post_invalid_json():
    """POST with non-JSON body returns 200 (graceful handling)."""
    from fastapi.testclient import TestClient
    from interfaces.webhook import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/webhook/whatsapp",
        content="not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200


def test_health_endpoint():
    """GET /health returns status."""
    from fastapi.testclient import TestClient
    from interfaces.webhook import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "mock_mode" in data


# ============================================================
# WHATSAPP MESSAGE DATACLASS TESTS
# ============================================================

def test_whatsapp_message_user_id():
    """WhatsAppMessage generates correct deterministic user_id."""
    msg = WhatsAppMessage(
        sender_phone="+919876543210",
        message_id="wamid.123",
        message_type="text",
    )
    assert msg.user_id == "whatsapp:+919876543210"
    assert msg.conversation_id == "whatsapp:+919876543210"


def test_whatsapp_message_defaults():
    """WhatsAppMessage has sensible defaults."""
    msg = WhatsAppMessage(
        sender_phone="+1",
        message_id="id",
        message_type="text",
    )
    assert msg.text is None
    assert msg.timestamp is None
    assert msg.sender_name is None
    assert msg.raw_payload == {}
