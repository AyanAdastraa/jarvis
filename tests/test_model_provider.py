import pytest
from unittest.mock import MagicMock, patch
from models.nemotron import NemotronProvider

@patch("models.nemotron.OpenAI")
def test_nemotron_provider_implements_interface(mock_openai):
    provider = NemotronProvider()
    assert hasattr(provider, "generate")
    assert hasattr(provider, "health_check")

@patch("models.nemotron.OpenAI")
def test_nemotron_provider_auth_config(mock_openai):
    with patch("app.config.settings.nvidia_api_key", "test_key_123"):
        provider = NemotronProvider()
        # Verify it was called with the right base_url and api_key
        call_kwargs = mock_openai.call_args
        assert call_kwargs.kwargs["base_url"] == "https://integrate.api.nvidia.com/v1"
        assert call_kwargs.kwargs["api_key"] == "test_key_123"

@patch("models.nemotron.OpenAI")
def test_nemotron_generate_no_tools(mock_openai):
    mock_client = mock_openai.return_value
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hello there"
    mock_response.choices[0].message.tool_calls = None
    mock_client.chat.completions.create.return_value = mock_response
    
    provider = NemotronProvider()
    messages = [{"role": "user", "content": "Hi"}]
    
    result = provider.generate(messages)
    
    assert result["content"] == "Hello there"
    assert result["tool_calls"] == []
    mock_client.chat.completions.create.assert_called_once()
    
@patch("models.nemotron.OpenAI")
def test_nemotron_generate_with_tools(mock_openai):
    mock_client = mock_openai.return_value
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = None
    
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_123"
    mock_tool_call.function.name = "my_tool"
    mock_tool_call.function.arguments = '{"arg1": "value1"}'
    mock_response.choices[0].message.tool_calls = [mock_tool_call]
    
    mock_client.chat.completions.create.return_value = mock_response
    
    provider = NemotronProvider()
    messages = [{"role": "user", "content": "Do it"}]
    tools = [{"type": "function", "function": {"name": "my_tool"}}]
    
    result = provider.generate(messages, tools=tools)
    
    assert result["content"] is None
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["id"] == "call_123"
    assert result["tool_calls"][0]["type"] == "function"
    assert result["tool_calls"][0]["function"]["name"] == "my_tool"
    assert result["tool_calls"][0]["function"]["arguments"] == '{"arg1": "value1"}'

@patch("models.nemotron.OpenAI")
def test_nemotron_health_check(mock_openai):
    mock_client = mock_openai.return_value
    
    with patch("app.config.settings.nvidia_api_key", "test"):
        provider = NemotronProvider()
        
        # Simulate success
        assert provider.health_check() is True
        
        # Simulate failure
        mock_client.models.list.side_effect = Exception("API down")
        assert provider.health_check() is False
