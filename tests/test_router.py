"""
Tests for the Model Router — classification, routing, fallback, and tool passing.
"""

import pytest
from unittest.mock import MagicMock, patch

from models.router import ModelRouter, classify_request, Complexity


# ============================================================
# CLASSIFICATION TESTS
# ============================================================


class TestClassifyRequest:
    """Test the deterministic heuristic classifier."""

    @pytest.mark.parametrize("text", [
        "hi",
        "hello",
        "hey",
        "Hi!",
        "Hello!",
        "Good morning",
        "good afternoon",
        "thanks",
        "thank you",
        "bye",
        "ok",
        "yes",
        "no",
        "what's up",
        "how are you",
        "who are you",
        "what's your name",
    ])
    def test_greetings_are_simple(self, text):
        assert classify_request(text) == Complexity.SIMPLE

    @pytest.mark.parametrize("text", [
        "remember my name is Ayan",
        "save my favorite color is blue",
        "what do you remember about me",
        "do you remember my name",
        "my name is John",
        "recall my project",
        "delete memory about my old address",
    ])
    def test_memory_operations_are_simple(self, text):
        assert classify_request(text) == Complexity.SIMPLE

    @pytest.mark.parametrize("text", [
        "what time is it?",
        "how old is the earth?",
        "tell me a joke",
        "what is python?",
    ])
    def test_short_questions_are_simple(self, text):
        assert classify_request(text) == Complexity.SIMPLE

    @pytest.mark.parametrize("text", [
        "analyze this code and find all potential bugs",
        "write a python script that processes CSV files",
        "implement a binary search tree with balancing",
        "debug this function that's returning wrong results",
        "refactor the authentication module to use JWT",
        "explain step by step how transformers work",
        "design a REST API for a todo app",
        "compare and contrast SQL vs NoSQL databases",
        "review my code for security vulnerabilities",
        "build a web scraper for news articles",
    ])
    def test_complex_requests(self, text):
        assert classify_request(text) == Complexity.COMPLEX

    def test_code_blocks_are_complex(self):
        text = "Fix this:\n```python\ndef foo():\n    return bar\n```"
        assert classify_request(text) == Complexity.COMPLEX

    def test_very_long_messages_are_complex(self):
        text = "word " * 100  # 100 words
        assert classify_request(text) == Complexity.COMPLEX

    def test_multiline_messages_are_complex(self):
        text = "line1\nline2\nline3\nline4\nline5\nline6\nline7"
        assert classify_request(text) == Complexity.COMPLEX

    def test_empty_is_simple(self):
        assert classify_request("") == Complexity.SIMPLE
        assert classify_request("   ") == Complexity.SIMPLE


# ============================================================
# ROUTER TESTS
# ============================================================


def _make_mock_provider(content="Mock response", tool_calls=None):
    """Create a mock ModelProvider that returns a fixed response."""
    provider = MagicMock()
    provider.generate.return_value = {
        "content": content,
        "tool_calls": tool_calls or [],
    }
    provider.health_check.return_value = True
    return provider


def _make_failing_provider(error_msg="Model unavailable"):
    """Create a mock ModelProvider that always raises."""
    provider = MagicMock()
    provider.generate.side_effect = Exception(error_msg)
    provider.health_check.return_value = False
    return provider


class TestModelRouter:

    @patch("models.router.settings")
    def test_simple_request_uses_fast_model(self, mock_settings):
        mock_settings.model_routing_enabled = True
        mock_settings.fast_model = "fast-model"
        mock_settings.complex_model = "complex-model"

        fast = _make_mock_provider("Fast response")
        nemotron = _make_mock_provider("Complex response")

        router = ModelRouter(fast_provider=fast, complex_provider=nemotron)

        messages = [{"role": "user", "content": "hi"}]
        result = router.generate(messages)

        assert result["content"] == "Fast response"
        fast.generate.assert_called_once()
        nemotron.generate.assert_not_called()
        assert router.last_classification == Complexity.SIMPLE

    @patch("models.router.settings")
    def test_complex_request_uses_nemotron(self, mock_settings):
        mock_settings.model_routing_enabled = True
        mock_settings.fast_model = "fast-model"
        mock_settings.complex_model = "complex-model"

        fast = _make_mock_provider("Fast response")
        nemotron = _make_mock_provider("Complex response")

        router = ModelRouter(fast_provider=fast, complex_provider=nemotron)

        messages = [{"role": "user", "content": "analyze this code and find all bugs step by step"}]
        result = router.generate(messages)

        assert result["content"] == "Complex response"
        nemotron.generate.assert_called_once()
        fast.generate.assert_not_called()
        assert router.last_classification == Complexity.COMPLEX

    @patch("models.router.settings")
    def test_fast_model_failure_falls_back_to_nemotron(self, mock_settings):
        mock_settings.model_routing_enabled = True
        mock_settings.fast_model = "fast-model"
        mock_settings.complex_model = "complex-model"

        fast = _make_failing_provider("Fast model down")
        nemotron = _make_mock_provider("Nemotron fallback response")

        router = ModelRouter(fast_provider=fast, complex_provider=nemotron)

        messages = [{"role": "user", "content": "hello"}]
        result = router.generate(messages)

        assert result["content"] == "Nemotron fallback response"
        fast.generate.assert_called_once()
        nemotron.generate.assert_called_once()

    @patch("models.router.settings")
    def test_fast_model_escalation_falls_back_to_nemotron(self, mock_settings):
        mock_settings.model_routing_enabled = True
        mock_settings.fast_model = "fast-model"
        mock_settings.complex_model = "complex-model"

        fast = _make_mock_provider("<ESCALATE>")
        nemotron = _make_mock_provider("Nemotron escalation response")

        router = ModelRouter(fast_provider=fast, complex_provider=nemotron)

        messages = [{"role": "user", "content": "save my memory"}]
        result = router.generate(messages, tools=[{"type": "function", "function": {"name": "save"}}])

        assert result["content"] == "Nemotron escalation response"
        fast.generate.assert_called_once()
        nemotron.generate.assert_called_once()

    @patch("models.router.settings")
    def test_both_models_failure_raises(self, mock_settings):
        mock_settings.model_routing_enabled = True
        mock_settings.fast_model = "fast-model"
        mock_settings.complex_model = "complex-model"

        fast = _make_failing_provider("Fast model down")
        nemotron = _make_failing_provider("Nemotron also down")

        router = ModelRouter(fast_provider=fast, complex_provider=nemotron)

        messages = [{"role": "user", "content": "hello"}]
        with pytest.raises(Exception, match="Nemotron also down"):
            router.generate(messages)

    @patch("models.router.settings")
    def test_tools_passed_correctly(self, mock_settings):
        mock_settings.model_routing_enabled = True
        mock_settings.fast_model = "fast-model"
        mock_settings.complex_model = "complex-model"

        fast = _make_mock_provider("Response with tools")
        nemotron = _make_mock_provider()

        router = ModelRouter(fast_provider=fast, complex_provider=nemotron)

        tools = [{"type": "function", "function": {"name": "save_memory"}}]
        messages = [{"role": "user", "content": "remember my name is Ayan"}]

        router.generate(messages, tools=tools)

        # Verify tools were passed through to the fast model
        fast.generate.assert_called_once_with(messages, tools=tools)

    @patch("models.router.settings")
    def test_routing_disabled_uses_nemotron(self, mock_settings):
        mock_settings.model_routing_enabled = False
        mock_settings.fast_model = "fast-model"
        mock_settings.complex_model = "complex-model"

        fast = _make_mock_provider("Fast response")
        nemotron = _make_mock_provider("Complex response")

        router = ModelRouter(fast_provider=fast, complex_provider=nemotron)

        messages = [{"role": "user", "content": "hi"}]
        result = router.generate(messages)

        assert result["content"] == "Complex response"
        nemotron.generate.assert_called_once()
        fast.generate.assert_not_called()
        assert router.last_classification == Complexity.COMPLEX

    @patch("models.router.settings")
    def test_timeout_on_complex_raises_cleanly(self, mock_settings):
        mock_settings.model_routing_enabled = True
        mock_settings.fast_model = "fast-model"
        mock_settings.complex_model = "complex-model"

        fast = _make_mock_provider()
        nemotron = _make_failing_provider("Request timed out")

        router = ModelRouter(fast_provider=fast, complex_provider=nemotron)

        messages = [{"role": "user", "content": "analyze this architecture in detail step by step"}]
        with pytest.raises(Exception, match="Request timed out"):
            router.generate(messages)

    @patch("models.router.settings")
    def test_health_check_partial(self, mock_settings):
        mock_settings.model_routing_enabled = True
        mock_settings.fast_model = "fast-model"
        mock_settings.complex_model = "complex-model"

        fast = _make_mock_provider()
        fast.health_check.return_value = True
        nemotron = _make_mock_provider()
        nemotron.health_check.return_value = False

        router = ModelRouter(fast_provider=fast, complex_provider=nemotron)

        # Router is healthy if at least one provider works
        assert router.health_check() is True

    @patch("models.router.settings")
    def test_extracts_latest_user_text(self, mock_settings):
        mock_settings.model_routing_enabled = True
        mock_settings.fast_model = "fast-model"
        mock_settings.complex_model = "complex-model"

        fast = _make_mock_provider()
        nemotron = _make_mock_provider()

        router = ModelRouter(fast_provider=fast, complex_provider=nemotron)

        messages = [
            {"role": "system", "content": "You are JARVIS."},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "analyze this complex problem"},
        ]
        result = router.generate(messages)

        # The latest user message is complex
        assert router.last_classification == Complexity.COMPLEX
