import pytest
import logging
import json
from io import StringIO
from pathlib import Path
from core.sandbox import resolve_workspace_path, PathTraversalError
from app.logger import get_logger, SecretRedactingFormatter

def test_path_traversal_protection(tmp_path, monkeypatch):
    monkeypatch.setattr("core.sandbox.WORKSPACE_DIR", tmp_path)
    
    # Safe path
    safe = resolve_workspace_path("output/test.txt")
    assert str(safe).startswith(str(tmp_path))
    
    # Unsafe relative path
    with pytest.raises(PathTraversalError):
        resolve_workspace_path("../.env")
        
    with pytest.raises(PathTraversalError):
        resolve_workspace_path("../../etc/passwd")
        
    # Unsafe absolute path
    with pytest.raises(PathTraversalError):
        resolve_workspace_path("/etc/passwd")

def test_secret_redaction(monkeypatch):
    # Setup mock config secrets
    monkeypatch.setattr("app.config.settings.nvidia_api_key", "SUPER_SECRET_KEY_123")
    monkeypatch.setattr("app.config.settings.whatsapp_access_token", "WHATSAPP_TOKEN_456")
    
    # We must instantiate the formatter after patching the settings so it picks up the patched secrets
    formatter = SecretRedactingFormatter()
    
    # Create a stream handler to capture logs
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    
    logger = logging.getLogger("test_security_logger")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    
    # Log a message containing the secret
    logger.info("Connecting with key SUPER_SECRET_KEY_123 and token WHATSAPP_TOKEN_456")
    
    # Also log an extra field with the secret
    logger.info("Another log", extra={"api_key": "some_other_secret", "normal_field": "SUPER_SECRET_KEY_123"})
    
    log_output = stream.getvalue()
    
    # Verify secrets do not appear
    assert "SUPER_SECRET_KEY_123" not in log_output
    assert "WHATSAPP_TOKEN_456" not in log_output
    assert "some_other_secret" not in log_output
    
    assert "***REDACTED***" in log_output
    
    logger.removeHandler(handler)
