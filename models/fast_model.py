"""
Fast Model Provider — lightweight, low-latency model for simple JARVIS requests.

Uses the same NVIDIA NIM API (integrate.api.nvidia.com) as NemotronProvider,
but targets a smaller, faster model for quick conversational responses.
"""

from typing import List, Dict, Any, Optional
from openai import OpenAI
from app.config import settings
from app.logger import get_logger
from models.base import ModelProvider

logger = get_logger(__name__)


class FastModelProvider(ModelProvider):
    def __init__(self):
        if not settings.nvidia_api_key:
            logger.warning("NVIDIA_API_KEY is not set.")

        self.client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=settings.nvidia_api_key or "DUMMY_KEY_FOR_TESTS",
            timeout=float(settings.fast_model_timeout),
            max_retries=1,
        )
        self.model = settings.fast_model

    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        # Strip tool-related messages from history — the fast model can't
        # process tool calls/results and they just bloat the context.
        # Strip tool-related messages from history — the fast model can't
        # process tool calls/results and they just bloat the context.
        clean_messages = []
        has_system = False
        
        for msg in messages:
            if msg.get("role") == "tool":
                continue
            # Skip assistant messages that were pure tool-call (no text)
            if msg.get("role") == "assistant" and msg.get("tool_calls") and not msg.get("content"):
                continue
            
            if msg.get("role") == "system":
                has_system = True
                # If tools are available, instruct the fast model to escalate if it needs them
                if tools:
                    content = msg.get("content", "")
                    escalate_instruction = (
                        "\n\nIMPORTANT: You are a fast, text-only model. You CANNOT use tools. "
                        "If the user's request requires taking an action (like saving data, searching memory, "
                        "reading files, running code, etc.), you MUST reply with exactly the word <ESCALATE> "
                        "and nothing else. This will route the request to a more capable model."
                    )
                    clean_messages.append({"role": "system", "content": content + escalate_instruction})
                else:
                    clean_messages.append(msg)
                continue
                
            # Remove tool_calls key from assistant messages that also have text
            cleaned = {k: v for k, v in msg.items() if k != "tool_calls"}
            clean_messages.append(cleaned)
            
        # If no system prompt was provided but tools are available, we should add one
        if not has_system and tools:
            clean_messages.insert(0, {
                "role": "system",
                "content": "You are a fast, text-only model. You CANNOT use tools. If the user's request requires taking an action (like saving data, searching memory, reading files, running code, etc.), you MUST reply with exactly the word <ESCALATE> and nothing else."
            })

        logger.info(
            f"Calling FastModel ({self.model}) with {len(clean_messages)} messages "
            f"(stripped from {len(messages)}).",
        )

        # NEVER pass tools to FastModel — NIM models return empty responses
        # when tool schemas are included. The fast model is text-only.
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": clean_messages,
            "max_tokens": 256,  # Keep responses short and fast
        }

        try:
            response = self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            return {
                "content": message.content,
                "tool_calls": [],  # Fast model never does tool calls
            }
        except Exception as e:
            logger.error("Failed to generate response from FastModel.", exc_info=True)
            raise

    def health_check(self) -> bool:
        if not settings.nvidia_api_key:
            return False
        try:
            self.client.models.list()
            return True
        except Exception:
            logger.error("FastModel health check failed.", exc_info=True)
            return False
