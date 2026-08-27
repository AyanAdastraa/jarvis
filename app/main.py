import sys
import uuid
from app.agent import Agent
from models.nemotron import NemotronProvider
from app.logger import get_logger
from app.config import settings

# For context manager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.db import Base
from core.context import ContextManager
from services.conversation import ConversationService
from services.memory import MemoryService
from services.rag import RagService
from core.retriever import LexicalRetriever

# Register tools
import tools.files
import tools.terminal
import tools.code
import tools.git
import tools.memory
import tools.rag_tools

logger = get_logger(__name__)

def main():
    logger.info("Initializing JARVIS...")
    
    try:
        model = NemotronProvider()
        
        if not model.health_check():
            logger.error("Nemotron health check failed. Exiting.")
            print("Failed to connect to the model provider. Check your API keys and configuration.")
            return

        # Setup Database for memory and context
        engine = create_engine(settings.database_url)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()

        # Initialize Services
        conv_svc = ConversationService(session)
        mem_svc = MemoryService(session)
        rag_svc = RagService(session, LexicalRetriever())
        cm = ContextManager(conv_svc, mem_svc, rag_svc)

        # Initialize Agent
        agent = Agent(model_provider=model, context_manager=cm)
        
        print("\n=======================================================")
        print("JARVIS Phase 3 CLI Initialized")
        print("Type 'exit' or 'quit' to stop.")
        print("=======================================================\n")
        
        # We simulate a specific user and conversation for the CLI session
        user_id = "local_user"
        conv_id = conv_svc.create_conversation(user_id)

        while True:
            try:
                user_input = input("\nYou: ")
                if user_input.strip().lower() in ["exit", "quit"]:
                    break
                
                if not user_input.strip():
                    continue

                response = agent.execute_task(user_input, user_id, conv_id)
                print(f"\nJARVIS: {response}")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"\nError processing request: {e}")
                logger.error("Error during CLI loop", exc_info=True)

        session.close()
        print("\nJARVIS shutting down...")

    except Exception as e:
        logger.error("JARVIS failed to start.", exc_info=True)
        print("Fatal error during startup. Check logs.")

if __name__ == "__main__":
    main()
