import pytest
import os
import subprocess
from tools.git import (
    execute_git_status,
    execute_git_diff,
    execute_git_log,
    execute_git_branch,
    execute_git_create_branch,
    execute_git_commit,
    scan_for_secrets
)

@pytest.fixture(autouse=True)
def setup_workspace(monkeypatch, tmp_path):
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    
    from core import sandbox
    monkeypatch.setattr(sandbox, "WORKSPACE_DIR", workspace_dir)
    
    # Init git repo
    subprocess.run(["git", "init"], cwd=str(workspace_dir), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(workspace_dir), check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(workspace_dir), check=True)
    
    yield workspace_dir

def test_git_status():
    res = execute_git_status(".")
    assert "On branch" in res

def test_git_branch_and_commit(setup_workspace):
    res = execute_git_create_branch("feature-1", ".")
    assert "Switched to a new branch" in res or "Success" in res
    
    # Create file
    with open(setup_workspace / "test.txt", "w") as f:
        f.write("hello")
        
    res = execute_git_commit("Initial commit", ["test.txt"], ".")
    assert "Initial commit" in res or "1 file changed" in res
    
    log = execute_git_log(".")
    assert "Initial commit" in log

def test_secret_scanning(setup_workspace):
    with open(setup_workspace / "secret.txt", "w") as f:
        f.write("AKIA1234567890ABCDEF")
        
    res = execute_git_commit("Add secret", ["secret.txt"], ".")
    assert "Error: Refusing to commit" in res

def test_selective_commit(setup_workspace):
    with open(setup_workspace / "modified_file_A.py", "w") as f:
        f.write("A")
    with open(setup_workspace / "modified_file_B.py", "w") as f:
        f.write("B")
        
    res = execute_git_commit("Commit A", ["modified_file_A.py"], ".")
    assert "1 file changed" in res or "Commit A" in res
    
    status = execute_git_status(".")
    assert "modified_file_B.py" in status
    assert "Untracked files:" in status or "Changes not staged for commit:" in status

def test_scan_for_secrets_regex():
    assert len(scan_for_secrets("aws_key = 'AKIAIOSFODNN7EXAMPLE'")) > 0
    assert len(scan_for_secrets("-----BEGIN RSA PRIVATE KEY-----")) > 0
    assert len(scan_for_secrets("password = 'super_secret_password_123'")) > 0
    assert len(scan_for_secrets("const token = 'ghp_1234567890'")) > 0
    assert len(scan_for_secrets("just a normal string")) == 0
