"""
Model Router — classifies requests as SIMPLE or COMPLEX and routes to the
appropriate model provider, with automatic fallback.

Architecture:
    WhatsApp → Agent → ModelRouter → Fast/Nemotron → Tools → Response

The router implements ModelProvider so the Agent doesn't know or care
about routing — it's a drop-in replacement.
"""

import re
from enum import Enum
from typing import List, Dict, Any, Optional

from app.config import settings
from app.logger import get_logger
from models.base import ModelProvider
from models.fast_model import FastModelProvider
from models.nemotron import NemotronProvider

logger = get_logger(__name__)


# ============================================================
# REQUEST COMPLEXITY CLASSIFICATION
# ============================================================

class Complexity(str, Enum):
    SIMPLE = "SIMPLE"
    COMPLEX = "COMPLEX"


# --- Greeting / trivial patterns (case-insensitive, anchored) ---
_GREETING_PATTERNS = re.compile(
    r"^(hi|hey|hello|hola|yo|sup|hii+|heyy+|helloo+|"
    r"good\s*(morning|afternoon|evening|night)|"
    r"thanks|thank\s*you|thx|bye|goodbye|see\s*you|"
    r"ok|okay|sure|yes|no|yep|nope|yeah|nah|"
    r"gm|gn|what'?s?\s*up|how\s*are\s*you|"
    r"who\s*are\s*you|what'?s?\s*your\s*name)[\s?!.]*$",
    re.IGNORECASE,
)

# --- Simple memory / recall patterns ---
_SIMPLE_MEMORY_PATTERNS = re.compile(
    r"(^remember\s|^save\s*(this|that|my)|"
    r"^what\s*do\s*you\s*(remember|know)\s*about|"
    r"^do\s*you\s*(remember|know)|"
    r"^my\s*name\s*is\s|"
    r"^recall\s|^forget\s|^delete\s*memory)",
    re.IGNORECASE,
)

# --- Complex signal keywords ---
_COMPLEX_KEYWORDS = re.compile(
    r"\b(analyze|analyse|debug|refactor|implement|architect|"
    r"compare\s+and\s+contrast|step[\s-]*by[\s-]*step|"
    r"write\s+.*?(code|script|program|function|class|module)|"
    r"create\s+.*?(script|program|application|api|server|service)|"
    r"explain\s+in\s+detail|deep\s*dive|"
    r"fix\s+(this|the)\s+(bug|error|issue|code)|"
    r"review\s+(this|the|my)\s+(code|pull|pr|implementation)|"
    r"optimize|refactor|redesign|"
    r"multi[\s-]*step|chain\s*of\s*thought|"
    r"pros?\s+and\s+cons?|trade[\s-]*offs?|"
    r"build\s+(a|an|the)|design\s+(a|an|the))\b",
    re.IGNORECASE,
)

# Code block indicator
_CODE_BLOCK = re.compile(r"```")

# Word-count thresholds
_SHORT_MESSAGE_WORDS = 15
_LONG_MESSAGE_WORDS = 80


def classify_request(text: str) -> Complexity:
    """
    Classify a user request as SIMPLE or COMPLEX using a lightweight
    deterministic heuristic. No LLM call is made.

    Rules (evaluated in order):
        1. Empty / very short → SIMPLE
        2. Matches greeting pattern → SIMPLE
        3. Contains code blocks → COMPLEX
        4. Matches complex keywords → COMPLEX
        5. Very long (>80 words) → COMPLEX
        6. Multi-line (>5 lines) → COMPLEX
        7. Matches simple memory pattern → SIMPLE
        8. Short (<15 words) → SIMPLE
        9. Default → SIMPLE (fallback handles failures)
    """
    stripped = text.strip()

    # 1. Empty or trivially short
    if not stripped or len(stripped.split()) <= 3:
        return Complexity.SIMPLE

    # 2. Greeting / trivial
    if _GREETING_PATTERNS.match(stripped):
        return Complexity.SIMPLE

    # 3. Code blocks
    if _CODE_BLOCK.search(stripped):
        return Complexity.COMPLEX

    # 4. Complex keywords
    if _COMPLEX_KEYWORDS.search(stripped):
        return Complexity.COMPLEX

    # 5. Very long message
    word_count = len(stripped.split())
    if word_count > _LONG_MESSAGE_WORDS:
        return Complexity.COMPLEX

    # 6. Multi-line (likely structured / detailed request)
    line_count = len(stripped.splitlines())
    if line_count > 5:
        return Complexity.COMPLEX

    # 7. Simple memory operations
    if _SIMPLE_MEMORY_PATTERNS.search(stripped):
        return Complexity.SIMPLE

    # 8. Short messages default to SIMPLE
    if word_count <= _SHORT_MESSAGE_WORDS:
        return Complexity.SIMPLE

    # 9. Default: SIMPLE (fast model with fallback is safe)
    return Complexity.SIMPLE


# ============================================================
# MODEL ROUTER
# ============================================================

class ModelRouter(ModelProvider):
    """
    Routes requests to the appropriate model based on complexity.

    When MODEL_ROUTING_ENABLED=true:
        SIMPLE  → FastModelProvider (with fallback to Nemotron)
        COMPLEX → NemotronProvider

    When MODEL_ROUTING_ENABLED=false:
        All requests → NemotronProvider (original behavior)
    """

    def __init__(
        self,
        fast_provider: Optional[FastModelProvider] = None,
        complex_provider: Optional[NemotronProvider] = None,
    ):
        self._fast = fast_provider or FastModelProvider()
        self._complex = complex_provider or NemotronProvider()
        self._routing_enabled = settings.model_routing_enabled
        self._last_classification: Optional[Complexity] = None

        logger.info(
            "ModelRouter initialized.",
            extra={
                "routing_enabled": self._routing_enabled,
                "fast_model": settings.fast_model,
                "complex_model": settings.complex_model,
            },
        )

    @property
    def last_classification(self) -> Optional[Complexity]:
        """Expose the last classification for testing / debugging."""
        return self._last_classification

    def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Route the request to the appropriate model.

        The router inspects the last user message to classify complexity.
        """
        # Extract the latest user message for classification
        user_text = self._extract_latest_user_text(messages)

        # Classify
        if not self._routing_enabled:
            classification = Complexity.COMPLEX  # Always use Nemotron when disabled
            logger.info("Model routing DISABLED — using Nemotron for all requests.")
        else:
            classification = classify_request(user_text)

        self._last_classification = classification

        logger.info(
            f"ModelRouter: request classified as {classification.value}",
            extra={
                "classification": classification.value,
                "user_text_preview": user_text[:80] if user_text else "",
                "model": settings.fast_model if classification == Complexity.SIMPLE else settings.complex_model,
            },
        )

        # Route
        if classification == Complexity.SIMPLE:
            return self._generate_with_fallback(messages, tools)
        else:
            return self._generate_complex(messages, tools)

    def _generate_with_fallback(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Try fast model first; fall back to Nemotron on failure or escalation."""
        try:
            logger.info(f"ModelRouter: using FAST model ({settings.fast_model})")
            response = self._fast.generate(messages, tools=tools)
            
            # Check for dynamic escalation
            content = response.get("content") or ""
            if content.strip() == "<ESCALATE>":
                logger.info("ModelRouter: FastModel requested ESCALATION. Rerouting to Nemotron.")
                return self._complex.generate(messages, tools=tools)
                
            return response
        except Exception as fast_err:
            logger.warning(
                f"FastModel failed, falling back to Nemotron: {fast_err}",
                exc_info=True,
            )
            try:
                logger.info(f"ModelRouter: FALLBACK to Nemotron ({settings.complex_model})")
                return self._complex.generate(messages, tools=tools)
            except Exception as complex_err:
                logger.error(
                    "Both FastModel and Nemotron failed.",
                    exc_info=True,
                )
                raise complex_err

    def _generate_complex(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Use Nemotron directly for complex requests."""
        try:
            logger.info(f"ModelRouter: using NEMOTRON ({settings.complex_model})")
            return self._complex.generate(messages, tools=tools)
        except Exception:
            logger.error("Nemotron failed for complex request.", exc_info=True)
            raise

    def health_check(self) -> bool:
        """Router is healthy if at least one provider is reachable."""
        fast_ok = False
        complex_ok = False
        try:
            fast_ok = self._fast.health_check()
        except Exception:
            pass
        try:
            complex_ok = self._complex.health_check()
        except Exception:
            pass
        return fast_ok or complex_ok

    @staticmethod
    def _extract_latest_user_text(messages: List[Dict[str, Any]]) -> str:
        """Walk backwards through messages to find the last user message."""
        for msg in reversed(messages):
            if msg.get("role") == "user" and msg.get("content"):
                return msg["content"]
        return ""
