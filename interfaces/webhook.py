"""
JARVIS WhatsApp Webhook Server — FastAPI application.

Exposes:
    GET  /webhook/whatsapp  — Meta webhook verification
    POST /webhook/whatsapp  — Incoming WhatsApp events
    GET  /health            — Health check

Security:
    - No stack traces exposed to callers
    - No secrets in responses
    - Webhook verify token validated
    - Background processing so Meta doesn't timeout

Usage:
    uvicorn interfaces.webhook:app --host 0.0.0.0 --port 8000

For local development with mock mode:
    WHATSAPP_MOCK_MODE=true uvicorn interfaces.webhook:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Query, BackgroundTasks, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.logger import get_logger
from app.agent import Agent
from core.db import Base
from core.context import ContextManager
from services.conversation import ConversationService
from services.memory import MemoryService
from services.rag import RagService
from core.retriever import LexicalRetriever
from models.router import ModelRouter

from interfaces.whatsapp import (
    WhatsAppInterface,
    WhatsAppMessage,
    parse_incoming_message,
    WebhookParseError,
    mask_phone,
)
from interfaces.whatsapp_client import WhatsAppClient

# Register tools (same as app/main.py)
import tools.files
import tools.terminal
import tools.code
import tools.git
import tools.memory
import tools.rag_tools

logger = get_logger(__name__)

# ============================================================
# APP INITIALIZATION
# ============================================================

# Global state — initialized on startup
_whatsapp_interface: WhatsAppInterface = None
_initialized = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize JARVIS components on server startup, clean up on shutdown."""
    global _whatsapp_interface, _initialized

    logger.info("Starting JARVIS WhatsApp webhook server...")

    try:
        # Model provider (routes between fast and complex models)
        model = ModelRouter()

        # Database
        engine = create_engine(settings.database_url)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        # Services
        conv_svc = ConversationService(session)
        mem_svc = MemoryService(session)
        rag_svc = RagService(session, LexicalRetriever())
        cm = ContextManager(conv_svc, mem_svc, rag_svc)

        # Agent — the EXISTING agent, not a new one
        agent = Agent(model_provider=model, context_manager=cm)

        # WhatsApp client
        client = WhatsAppClient()

        # WhatsApp interface
        _whatsapp_interface = WhatsAppInterface(
            agent=agent,
            db_session=session,
            whatsapp_client=client,
        )

        _initialized = True

        mode = "MOCK" if settings.whatsapp_mock_mode else "LIVE"
        logger.info(f"JARVIS WhatsApp webhook ready. Mode: {mode}")

    except Exception as e:
        logger.error("Failed to initialize JARVIS WhatsApp webhook.", exc_info=True)
        # Don't crash the server — health endpoint will report unhealthy
        _initialized = False

    yield  # Server is running

    # Shutdown — clean up DB session
    if _initialized and _whatsapp_interface:
        try:
            _whatsapp_interface.db.close()
            logger.info("JARVIS WhatsApp webhook shutdown complete.")
        except Exception:
            pass


app = FastAPI(
    title="JARVIS WhatsApp Webhook",
    description="WhatsApp Cloud API webhook for JARVIS personal AI assistant.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,      # Disable Swagger UI in production
    redoc_url=None,      # Disable ReDoc in production
    openapi_url=None,    # Disable OpenAPI schema in production
)


# ============================================================
# EXCEPTION HANDLER — never expose internals
# ============================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler to prevent stack traces from leaking."""
    logger.error("Unhandled exception in webhook server.", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error."},
    )


# ============================================================
# HEALTH ENDPOINT
# ============================================================

@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {
        "status": "healthy" if _initialized else "unhealthy",
        "mock_mode": settings.whatsapp_mock_mode,
        "whatsapp_enabled": settings.whatsapp_enabled,
    }


# ============================================================
# WEBHOOK VERIFICATION (GET)
# ============================================================

@app.get("/webhook/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """
    Meta webhook verification endpoint.

    When you register a webhook URL with Meta, they send a GET request with:
        hub.mode = "subscribe"
        hub.verify_token = <your configured token>
        hub.challenge = <random string>

    You must return the challenge value ONLY if the verify_token matches.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("Webhook verification successful.")
        return PlainTextResponse(content=hub_challenge, status_code=200)

    logger.warning("Webhook verification failed — token mismatch or invalid mode.")
    raise HTTPException(status_code=403, detail="Verification failed.")


# ============================================================
# WEBHOOK HANDLER (POST)
# ============================================================

@app.post("/webhook/whatsapp")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receive incoming WhatsApp events from Meta.

    Returns HTTP 200 immediately to acknowledge receipt,
    then processes the message in the background so Meta doesn't timeout.
    """
    if not _initialized:
        logger.error("Webhook received but server is not initialized.")
        return JSONResponse(status_code=200, content={"status": "not_ready"})

    try:
        payload = await request.json()
        logger.info(f"Received webhook payload: {payload}")
    except Exception:
        logger.warning("Received non-JSON webhook payload.")
        return JSONResponse(status_code=200, content={"status": "invalid_payload"})

    # Parse message
    try:
        message = parse_incoming_message(payload)
    except WebhookParseError as e:
        logger.warning(f"Malformed webhook payload: {e}")
        return JSONResponse(status_code=200, content={"status": "parse_error"})

    if message is None:
        # Not a user message (status update, delivery receipt, etc.)
        return JSONResponse(status_code=200, content={"status": "ignored"})

    # Process in background so we return 200 immediately
    background_tasks.add_task(_process_message, message)

    return JSONResponse(status_code=200, content={"status": "accepted"})


def _process_message(message: WhatsAppMessage):
    """Background task to process a WhatsApp message through JARVIS."""
    try:
        _whatsapp_interface.handle_message(message)
    except Exception:
        logger.error(
            f"Error processing WhatsApp message from {mask_phone(message.sender_phone)}",
            exc_info=True,
        )
        # Try to send an error response to the user
        try:
            _whatsapp_interface.client.send_text_message(
                message.sender_phone,
                "I encountered an unexpected error. Please try again in a moment.",
            )
        except Exception:
            logger.error("Failed to send error response to WhatsApp user.", exc_info=True)
