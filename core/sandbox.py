import os
from pathlib import Path

# The workspace is sandboxed to the workspace/ directory in the project root.
BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = BASE_DIR / "workspace"
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

class PathTraversalError(Exception):
    pass

def resolve_workspace_path(unsafe_path: str) -> Path:
    """
    Resolve a path to ensure it is inside the workspace sandbox.
    Raises PathTraversalError if it attempts to escape.
    """
    try:
        unsafe_p = Path(unsafe_path).expanduser()
        
        if unsafe_p.is_absolute():
            # If absolute, verify it's inside the workspace
            resolved_unsafe = unsafe_p.resolve()
            if not str(resolved_unsafe).startswith(str(WORKSPACE_DIR.resolve())):
                raise PathTraversalError(f"Absolute path {unsafe_path} is outside the workspace sandbox.")
            safe_path = resolved_unsafe
        else:
            # If relative, resolve it relative to WORKSPACE_DIR
            safe_path = (WORKSPACE_DIR / unsafe_p).resolve()
            if not str(safe_path).startswith(str(WORKSPACE_DIR.resolve())):
                raise PathTraversalError(f"Relative path {unsafe_path} escapes the workspace sandbox.")
                
        return safe_path
    except Exception as e:
        if isinstance(e, PathTraversalError):
            raise
        raise PathTraversalError(f"Invalid path: {unsafe_path}")
