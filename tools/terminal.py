import os
import shlex
import subprocess
from pydantic import BaseModel, Field
from app.config import settings
from app.logger import get_logger
from tools.registry import registry, ToolDefinition
from core.permissions import PermissionLevel
from core.sandbox import resolve_workspace_path, PathTraversalError

logger = get_logger(__name__)

class ExecuteCommandSchema(BaseModel):
    command: str = Field(..., description="The command to execute in the terminal.")
    working_directory: str = Field(default=".", description="Relative path for the working directory.")

def sanitize_environment() -> dict:
    """Return a sanitized copy of the current environment, removing sensitive keys."""
    env = os.environ.copy()
    sensitive_substrings = ["KEY", "TOKEN", "SECRET", "PASS", "CREDENTIAL", "AUTH"]
    keys_to_remove = []
    
    for k in env.keys():
        k_upper = k.upper()
        if any(sub in k_upper for sub in sensitive_substrings):
            keys_to_remove.append(k)
            
    for k in keys_to_remove:
        del env[k]
        
    return env

def truncate_output(text: str, max_size: int) -> str:
    """Truncate text if it exceeds max_size bytes, appending a warning."""
    if not text:
        return ""
    # encoding to bytes to accurately measure length
    text_bytes = text.encode("utf-8", errors="replace")
    if len(text_bytes) > max_size:
        truncated = text_bytes[:max_size].decode("utf-8", errors="replace")
        return truncated + f"\n\n... [Output truncated, exceeded {max_size} bytes limit] ..."
    return text

def execute_terminal_command(command: str, working_directory: str = ".", user_id: str = None) -> str:
    try:
        # Resolve working directory safely
        cwd = resolve_workspace_path(working_directory)
        if not cwd.is_dir():
            return f"Error: Working directory '{working_directory}' does not exist or is not a directory."
            
        args = shlex.split(command)
        if not args:
            return "Error: Empty command."
            
        base_cmd = args[0]
        if base_cmd not in settings.terminal_allowlist:
            return f"Error: Command '{base_cmd}' is not allowed. Allowed commands: {', '.join(settings.terminal_allowlist)}"
            
        # Execute securely
        env = sanitize_environment()
        
        try:
            result = subprocess.run(
                args,
                cwd=str(cwd),
                env=env,
                capture_output=True,
                text=True,
                timeout=settings.command_timeout,
                shell=False
            )
            
            stdout = truncate_output(result.stdout, settings.max_command_output_size)
            stderr = truncate_output(result.stderr, settings.max_command_output_size)
            
            exit_code = result.returncode
            
            output = f"Exit code: {exit_code}\n"
            if stdout:
                output += f"STDOUT:\n{stdout}\n"
            if stderr:
                output += f"STDERR:\n{stderr}\n"
                
            return output.strip()
            
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {settings.command_timeout} seconds."
            
    except PathTraversalError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

registry.register(ToolDefinition(
    name="execute_command",
    description="Execute a safe terminal command (e.g. pytest, python, npm).",
    schema=ExecuteCommandSchema,
    executor=execute_terminal_command,
    permission_level=PermissionLevel.EXECUTE
))
