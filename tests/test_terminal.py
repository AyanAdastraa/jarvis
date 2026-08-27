import pytest
import os
import subprocess
import sys
from app.config import settings
from tools.terminal import execute_terminal_command, sanitize_environment

@pytest.fixture(autouse=True)
def setup_workspace(monkeypatch, tmp_path):
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    
    from core import sandbox
    monkeypatch.setattr(sandbox, "WORKSPACE_DIR", workspace_dir)
    
    # Overwrite for tests
    monkeypatch.setattr(settings, "terminal_allowlist", [sys.executable, "ls", "echo", "sleep"])
    monkeypatch.setattr(settings, "command_timeout", 2)
    monkeypatch.setattr(settings, "max_command_output_size", 50)
    yield workspace_dir

def test_execute_allowed_command():
    # Use python as an allowed command
    res = execute_terminal_command(f"{sys.executable} -c \"print('hello')\"")
    assert "Exit code: 0" in res
    assert "hello" in res

def test_rejected_command():
    res = execute_terminal_command("rm -rf /")
    assert "Error: Command 'rm' is not allowed" in res

def test_timeout():
    res = execute_terminal_command(f"{sys.executable} -c \"import time; time.sleep(3)\"")
    assert "Error: Command timed out" in res

def test_output_truncation():
    # Output size limit is 50 bytes
    res = execute_terminal_command(f"{sys.executable} -c \"print('A' * 100)\"")
    assert "Exit code: 0" in res
    assert "Output truncated, exceeded" in res

def test_environment_sanitization(monkeypatch):
    # Temporarily add secrets to environ
    monkeypatch.setenv("MY_SECRET_KEY", "super_secret_value")
    monkeypatch.setenv("AWS_ACCESS_TOKEN", "aws_token_value")
    monkeypatch.setenv("SAFE_ENV", "safe_value")
    
    env = sanitize_environment()
    assert "MY_SECRET_KEY" not in env
    assert "AWS_ACCESS_TOKEN" not in env
    assert "SAFE_ENV" in env
    assert env["SAFE_ENV"] == "safe_value"
