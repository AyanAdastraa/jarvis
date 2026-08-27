"""
JARVIS WhatsApp Mock CLI — Local testing interface.

Simulates WhatsApp message flow entirely locally.
Routes through the REAL WhatsAppInterface → REAL Agent → REAL tools.

No Meta credentials required. No network calls.

Usage:
    python -m interfaces.whatsapp_mock

This is the exact same pipeline that a real WhatsApp message would follow,
except the transport layer logs instead of calling Meta.
"""

import sys
import uuid
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.logger import get_logger
from core.db import Base
from core.context import ContextManager
from services.conversation import ConversationService
from services.memory import MemoryService
from services.rag import RagService
from core.retriever import LexicalRetriever
from models.nemotron import NemotronProvider
from app.agent import Agent

from interfaces.whatsapp import WhatsAppInterface, WhatsAppMessage
from interfaces.whatsapp_client import WhatsAppClient

# Register tools (same as app/main.py)
import tools.files
import tools.terminal
import tools.code
import tools.git
import tools.memory
import tools.rag_tools

logger = get_logger(__name__)

MOCK_PHONE = "+1000000000"
BANNER = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║               JARVIS WhatsApp Mock Interface                 ║
║                                                              ║
║   This simulates WhatsApp messaging through the REAL         ║
║   JARVIS agent pipeline. No Meta credentials needed.         ║
║                                                              ║
║   Type your message and press Enter.                         ║
║   Type 'exit' or 'quit' to stop.                             ║
║   Type '/status' to see session info.                        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""


def main():
    print(BANNER)

    # --- Initialize ---
    print("  Initializing JARVIS engine...")

    try:
        model = NemotronProvider()

        if not model.health_check():
            print("\n  ✗ Failed to connect to model provider.")
            print("    Check your NVIDIA_API_KEY in .env")
            return

        print("  ✓ Model provider connected.")

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

        # Agent — the EXISTING agent
        agent = Agent(model_provider=model, context_manager=cm)

        # WhatsApp client in mock mode
        client = WhatsAppClient(mock_mode=True)

        # WhatsApp interface
        interface = WhatsAppInterface(
            agent=agent,
            db_session=session,
            whatsapp_client=client,
        )

        print("  ✓ JARVIS engine initialized.")
        print(f"  ✓ Mock phone: {MOCK_PHONE}")
        print(f"  ✓ User ID: whatsapp:{MOCK_PHONE}")
        print()
        print("─" * 62)
        print()

    except Exception as e:
        print(f"\n  ✗ Failed to initialize: {e}")
        logger.error("Mock CLI initialization failed.", exc_info=True)
        return

    # --- Interactive Loop ---
    message_counter = 0

    while True:
        try:
            user_input = input("  You: ")
        except (KeyboardInterrupt, EOFError):
            break

        stripped = user_input.strip()

        if stripped.lower() in ("exit", "quit"):
            break

        if stripped == "/status":
            print(f"\n  ℹ  Mock phone: {MOCK_PHONE}")
            print(f"  ℹ  User ID: whatsapp:{MOCK_PHONE}")
            print(f"  ℹ  Messages sent: {message_counter}")
            print(f"  ℹ  Mock mode: {settings.whatsapp_mock_mode}")
            print()
            continue

        if not stripped:
            continue

        message_counter += 1

        # Build a WhatsAppMessage just like the real webhook would
        mock_message = WhatsAppMessage(
            sender_phone=MOCK_PHONE,
            message_id=f"mock_{uuid.uuid4().hex[:16]}",
            message_type="text",
            text=stripped,
            timestamp=str(int(time.time())),
            sender_name="Local Tester",
        )

        # Route through the REAL interface pipeline
        try:
            response = interface.handle_message(mock_message)

            if response:
                # Format the response nicely for CLI
                print()
                print(f"  JARVIS: {response}")
                print()
            else:
                print("\n  JARVIS: [no response]\n")

        except Exception as e:
            print(f"\n  ✗ Error: {e}\n")
            logger.error("Error in mock CLI.", exc_info=True)

    # --- Shutdown ---
    session.close()
    print("\n  JARVIS WhatsApp Mock shutting down.\n")


if __name__ == "__main__":
    main()
