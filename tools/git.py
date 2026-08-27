import os
import re
import shlex
import subprocess
from pydantic import BaseModel, Field
from app.logger import get_logger
from tools.registry import registry, ToolDefinition
from core.permissions import PermissionLevel
from core.sandbox import resolve_workspace_path, PathTraversalError

logger = get_logger(__name__)

# Basic secret patterns
SECRET_PATTERNS = [
    r"(?i)AKIA[0-9A-Z]{16}", # AWS Key
    r"-----BEGIN (RSA|OPENSSH|DSA|EC|PGP) PRIVATE KEY-----", # SSH keys
    r"(?i)(password|secret|token|api_key)['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9\-_]{8,}['\"]?" # generic secrets
]

def scan_for_secrets(content: str) -> list[str]:
    found = []
    for pattern in SECRET_PATTERNS:
        if re.search(pattern, content):
            found.append(pattern)
    return found

def _run_git_command(args: list[str], path: str = ".") -> str:
    try:
        cwd = resolve_workspace_path(path)
        if not cwd.is_dir():
            return f"Error: '{path}' is not a directory."
            
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=30,
            shell=False
        )
        
        if result.returncode != 0:
            return f"Git Error (exit code {result.returncode}):\n{result.stderr.strip()}"
            
        return result.stdout.strip() or "Success (no output)."
    except PathTraversalError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

class GitCommandSchema(BaseModel):
    path: str = Field(default=".", description="Path to the git repository.")

def execute_git_status(path: str = ".", user_id: str = None) -> str:
    return _run_git_command(["status"], path)

def execute_git_diff(path: str = ".", user_id: str = None) -> str:
    return _run_git_command(["diff"], path)

def execute_git_log(path: str = ".", user_id: str = None) -> str:
    return _run_git_command(["log", "-n", "10", "--oneline"], path)

def execute_git_branch(path: str = ".", user_id: str = None) -> str:
    return _run_git_command(["branch"], path)

class GitCreateBranchSchema(BaseModel):
    branch_name: str = Field(..., description="Name of the new branch.")
    path: str = Field(default=".", description="Path to the git repository.")

def execute_git_create_branch(branch_name: str, path: str = ".", user_id: str = None) -> str:
    return _run_git_command(["checkout", "-b", branch_name], path)

class GitCommitSchema(BaseModel):
    message: str = Field(..., description="Commit message.")
    files: list[str] = Field(..., description="List of specific files to stage and commit.")
    path: str = Field(default=".", description="Path to the git repository.")

def execute_git_commit(message: str, files: list[str], path: str = ".", user_id: str = None) -> str:
    if not files:
        return "Error: No files specified for commit."
        
    # Add only the specified files to staging
    add_args = ["add"] + files
    add_res = _run_git_command(add_args, path)
    if "Error" in add_res and "Git Error" in add_res:
        return add_res
        
    # Pre-commit secret scanning of staged files
    diff = _run_git_command(["diff", "--cached"], path)
    if "Error" not in diff:
        secrets = scan_for_secrets(diff)
        if secrets:
            _run_git_command(["reset"], path) # Unstage
            return "Error: Refusing to commit. Potential secrets found in diff."
            
    return _run_git_command(["commit", "-m", message], path)

registry.register(ToolDefinition(
    name="git_status",
    description="Show the working tree status.",
    schema=GitCommandSchema,
    executor=execute_git_status,
    permission_level=PermissionLevel.READ
))

registry.register(ToolDefinition(
    name="git_diff",
    description="Show changes between commits, commit and working tree, etc.",
    schema=GitCommandSchema,
    executor=execute_git_diff,
    permission_level=PermissionLevel.READ
))

registry.register(ToolDefinition(
    name="git_log",
    description="Show commit logs.",
    schema=GitCommandSchema,
    executor=execute_git_log,
    permission_level=PermissionLevel.READ
))

registry.register(ToolDefinition(
    name="git_branch",
    description="List branches.",
    schema=GitCommandSchema,
    executor=execute_git_branch,
    permission_level=PermissionLevel.READ
))

registry.register(ToolDefinition(
    name="git_create_branch",
    description="Create a new branch and switch to it.",
    schema=GitCreateBranchSchema,
    executor=execute_git_create_branch,
    permission_level=PermissionLevel.GIT
))

registry.register(ToolDefinition(
    name="git_commit",
    description="Commit current changes. Rejects commits containing secrets.",
    schema=GitCommitSchema,
    executor=execute_git_commit,
    permission_level=PermissionLevel.GIT
))
