# JARVIS WhatsApp Interface

## Architecture

```
WhatsApp Cloud API (Meta)
        ↓
    Webhook Server              ← interfaces/webhook.py (FastAPI)
        ↓
    WhatsApp Interface          ← interfaces/whatsapp.py (message lifecycle)
        ↓
    JARVIS Agent                ← app/agent.py (existing Phase 1–3 agent)
        ↓
    Tool Registry + Nemotron    ← tools/, models/nemotron.py
        ↓
    Memory / RAG / Files / Terminal / Git / PDF
        ↓
    WhatsApp Client             ← interfaces/whatsapp_client.py (outbound)
        ↓
    WhatsApp Cloud API (response)
```

WhatsApp is an **interface layer only**. It does not contain agent logic, bypass permissions, or duplicate existing systems. All messages flow through the same `Agent.execute_task()` pipeline as the CLI.

## Files

| File | Purpose |
|---|---|
| `interfaces/whatsapp.py` | Message parsing, rate limiting, dedup, interface orchestration |
| `interfaces/whatsapp_client.py` | Outbound Meta Cloud API client (mock + live) |
| `interfaces/webhook.py` | FastAPI webhook server |
| `interfaces/whatsapp_mock.py` | Local CLI mock for testing without Meta credentials |
| `interfaces/__init__.py` | Package init |
| `interfaces/__main__.py` | Entrypoint for `python -m interfaces.whatsapp_mock` |
| `tests/test_whatsapp.py` | 50 comprehensive tests |

## Environment Variables

Add these to your `.env` file:

```bash
# ============================================================
# WHATSAPP CONFIGURATION
# ============================================================

# Master toggle — set to true to enable the WhatsApp webhook
WHATSAPP_ENABLED=false

# Mock mode — when true, outbound messages are logged locally
# instead of calling Meta's API. No credentials needed.
WHATSAPP_MOCK_MODE=true

# Meta Cloud API credentials (only needed when MOCK_MODE=false)
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_VERIFY_TOKEN=your_webhook_verify_token

# Meta Graph API version
WHATSAPP_API_VERSION=v21.0

# Safety limits
WHATSAPP_MAX_MESSAGE_LENGTH=4096
WHATSAPP_RATE_LIMIT_PER_MINUTE=30
```

## Local Mock Mode

Test the complete message pipeline locally without Meta credentials:

```bash
python -m interfaces.whatsapp_mock
```

This launches an interactive CLI that:
- Simulates WhatsApp message payloads
- Routes through the **real** WhatsAppInterface → **real** Agent → **real** tools
- Uses a mock phone number (`+1000000000`)
- Logs outbound messages locally instead of calling Meta

### Example Session

```
  You: What time is it?

  JARVIS: The current time is 2:30 PM IST.

  You: /status

  ℹ  Mock phone: +1000000000
  ℹ  User ID: whatsapp:+1000000000
  ℹ  Messages sent: 1
  ℹ  Mock mode: True
```

## Running the Webhook Server

For local development:

```bash
uvicorn interfaces.webhook:app --host 0.0.0.0 --port 8000 --reload
```

For production:

```bash
uvicorn interfaces.webhook:app --host 0.0.0.0 --port 8000 --workers 4
```

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/webhook/whatsapp` | Meta webhook verification |
| `POST` | `/webhook/whatsapp` | Incoming WhatsApp events |
| `GET` | `/health` | Health check |

## Meta Integration (Production)

When you have a Meta Business account and phone number:

1. **Create a Meta App** at [developers.facebook.com](https://developers.facebook.com)
2. **Add WhatsApp product** to your app
3. **Get credentials**:
   - System User Access Token → `WHATSAPP_ACCESS_TOKEN`
   - Phone Number ID → `WHATSAPP_PHONE_NUMBER_ID`
   - Choose a verify token → `WHATSAPP_VERIFY_TOKEN`
4. **Set environment**:
   ```bash
   WHATSAPP_MOCK_MODE=false
   WHATSAPP_ENABLED=true
   ```
5. **Expose your webhook** (use ngrok for local development):
   ```bash
   ngrok http 8000
   ```
6. **Register webhook URL** in Meta Dashboard:
   - URL: `https://<your-domain>/webhook/whatsapp`
   - Verify Token: matches your `WHATSAPP_VERIFY_TOKEN`
   - Subscribe to: `messages`

## User Identity

- **User ID**: `whatsapp:<phone_number>` (e.g., `whatsapp:+919876543210`)
- **Conversation ID**: Same as user ID — one persistent conversation per phone number
- User and Conversation rows are auto-created in the database on first message

## Security

| Concern | Mitigation |
|---|---|
| Untrusted input | Input size limit (4096 chars), rate limiting (30/min) |
| Permission bypass | All calls go through existing Agent → ToolRegistry → PermissionLevel |
| Secret exposure | Phone numbers masked in logs, `SecretRedactingFormatter` preserved |
| Sandbox escape | Tool execution uses `resolve_workspace_path()` |
| Duplicate processing | Message ID deduplication (bounded in-memory set) |
| API key exposure | Webhook never returns internal errors, mock mode prevents Meta calls |
| Stack trace leaks | Custom exception handler returns generic error responses |

## Message Types

| Type | Behavior |
|---|---|
| `text` | ✅ Processed through JARVIS agent |
| `image` | ❌ Polite rejection with future support note |
| `document` | ❌ Polite rejection, directs to CLI interface |
| `audio` | ❌ Polite rejection |
| `video` | ❌ Polite rejection |
| `sticker` | ❌ Polite rejection |
| `location` | ❌ Polite rejection |
| `reaction` | 🔇 Silently ignored |
| `system` | 🔇 Silently ignored |
| Unknown | ❌ Generic rejection |

## Testing

Run the WhatsApp test suite:

```bash
python -m pytest tests/test_whatsapp.py -v
```

Run the full project test suite:

```bash
python -m pytest -q
```

### Test Coverage (50 tests)

1. Webhook verification success/failure
2. Meta payload parsing (text, contacts, edge cases)
3. Malformed payload handling
4. Unsupported message types (image, document, audio, reaction, unknown)
5. Mock mode send_message / send_document / mark_as_read
6. Meta client payload construction validation
7. Missing credentials behavior
8. Mock mode never makes HTTP calls
9. Agent receives correct user_id and conversation_id
10. Permission system integrity
11. Phone number masking
12. Oversized message rejection
13. Duplicate message deduplication
14. Agent error graceful handling
15. Rate limiter (within limit, over limit, per-user, reset)
16. Webhook POST endpoint behavior
17. Health endpoint
18. WhatsAppMessage dataclass properties

## Future Enhancements

- **Image/document processing** via WhatsApp media API
- **Voice message** transcription and response
- **Interactive messages** (buttons, lists) for structured interactions
- **Media upload** (binary upload to Meta's media endpoint)
- **Session-based conversations** with configurable timeouts
- **Typing indicators** during agent processing
- **Webhook signature verification** (HMAC-SHA256)
