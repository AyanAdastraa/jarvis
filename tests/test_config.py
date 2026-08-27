import os
import pytest

def test_config_loading(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "env_test_key")
    monkeypatch.setenv("DATABASE_URL", "postgres://test")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "super_secret_token")
    
    # Reload settings to capture mocked env vars
    from app.config import Settings
    
    # Create fresh instance
    settings = Settings(_env_file=None)
    
    assert settings.nvidia_api_key == "env_test_key"
    assert settings.database_url == "postgres://test"
    
    # Test representation hides secrets
    printed = str(settings)
    represented = repr(settings)
    
    assert "env_test_key" not in printed
    assert "super_secret_token" not in printed
    assert "env_test_key" not in represented
    
    assert "***REDACTED***" in printed
    
def test_config_defaults():
    from app.config import Settings
    # Empty environment
    settings = Settings(_env_file=None, nvidia_api_key="")
    
    assert settings.nvidia_model == "nvidia/nemotron-3-ultra-550b-a55b"
    assert settings.database_url == "sqlite:///workspace/jarvis.db"
