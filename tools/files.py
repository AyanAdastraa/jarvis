import os
import shutil
import fnmatch
from pathlib import Path
from pydantic import BaseModel, Field
from app.config import settings
from app.logger import get_logger
from tools.registry import registry, ToolDefinition
from core.permissions import PermissionLevel
from core.sandbox import resolve_workspace_path, PathTraversalError

logger = get_logger(__name__)

class ListDirectorySchema(BaseModel):
    path: str = Field(default=".", description="Relative path to directory to list.")

def execute_list_directory(path: str, user_id: str = None) -> str:
    try:
        resolved_path = resolve_workspace_path(path)
        if not resolved_path.is_dir():
            return f"Error: '{path}' is not a directory."
        
        items = []
        for i, item in enumerate(resolved_path.iterdir()):
            if i >= settings.max_search_results:
                items.append(f"... (truncated, max {settings.max_search_results} items)")
                break
            
            item_type = "DIR" if item.is_dir() else "FILE"
            size = item.stat().st_size if item.is_file() else ""
            items.append(f"[{item_type}] {item.name} {size}")
            
        if not items:
            return "Directory is empty."
        return "\n".join(items)
    except PathTraversalError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

class ReadFileSchema(BaseModel):
    path: str = Field(..., description="Relative path to file to read.")

def execute_read_file(path: str, user_id: str = None) -> str:
    try:
        resolved_path = resolve_workspace_path(path)
        if not resolved_path.is_file():
            return f"Error: '{path}' is not a file."
            
        file_size = resolved_path.stat().st_size
        if file_size > settings.max_file_read_size:
            return f"Error: File is too large ({file_size} bytes). Max allowed is {settings.max_file_read_size} bytes."
            
        try:
            with open(resolved_path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            return "Error: File appears to be binary or not valid UTF-8."
    except PathTraversalError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

class WriteFileSchema(BaseModel):
    path: str = Field(..., description="Relative path to file to write.")
    content: str = Field(..., description="Content to write to the file.")

def execute_write_file(path: str, content: str, user_id: str = None) -> str:
    try:
        resolved_path = resolve_workspace_path(path)
        
        # Ensure parent directory exists
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(resolved_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"File '{path}' written successfully."
    except PathTraversalError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

class SearchFilesSchema(BaseModel):
    pattern: str = Field(..., description="Glob pattern to search for (e.g. '*.py').")
    path: str = Field(default=".", description="Directory to search in.")

def execute_search_files(pattern: str, path: str = ".", user_id: str = None) -> str:
    try:
        resolved_path = resolve_workspace_path(path)
        if not resolved_path.is_dir():
            return f"Error: '{path}' is not a directory."
            
        results = []
        for file_path in resolved_path.rglob(pattern):
            if file_path.is_file():
                results.append(str(file_path.relative_to(resolve_workspace_path("."))))
                if len(results) >= settings.max_search_results:
                    results.append(f"... (truncated to {settings.max_search_results} results)")
                    break
                    
        if not results:
            return f"No files matching '{pattern}' found."
        return "\n".join(results)
    except PathTraversalError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

class MoveCopyFileSchema(BaseModel):
    source: str = Field(..., description="Source file path.")
    destination: str = Field(..., description="Destination file path.")

def execute_move_file(source: str, destination: str, user_id: str = None) -> str:
    try:
        src = resolve_workspace_path(source)
        dst = resolve_workspace_path(destination)
        if not src.exists():
            return f"Error: Source '{source}' does not exist."
            
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Moved '{source}' to '{destination}'."
    except PathTraversalError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

def execute_copy_file(source: str, destination: str, user_id: str = None) -> str:
    try:
        src = resolve_workspace_path(source)
        dst = resolve_workspace_path(destination)
        if not src.exists():
            return f"Error: Source '{source}' does not exist."
            
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
        else:
            shutil.copy2(str(src), str(dst))
        return f"Copied '{source}' to '{destination}'."
    except PathTraversalError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

class DeleteFileSchema(BaseModel):
    path: str = Field(..., description="Path to file or directory to delete.")

def execute_delete_file(path: str, user_id: str = None) -> str:
    try:
        resolved = resolve_workspace_path(path)
        if not resolved.exists():
            return f"Error: '{path}' does not exist."
            
        if resolved.is_dir():
            shutil.rmtree(str(resolved))
        else:
            resolved.unlink()
        return f"Deleted '{path}'."
    except PathTraversalError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

# Register all tools
registry.register(ToolDefinition(
    name="list_directory",
    description="List files and directories in a given path.",
    schema=ListDirectorySchema,
    executor=execute_list_directory,
    permission_level=PermissionLevel.READ
))

registry.register(ToolDefinition(
    name="read_file",
    description="Read the contents of a text file. Rejects large or binary files.",
    schema=ReadFileSchema,
    executor=execute_read_file,
    permission_level=PermissionLevel.READ
))

registry.register(ToolDefinition(
    name="write_file",
    description="Write content to a file, overwriting it if it exists.",
    schema=WriteFileSchema,
    executor=execute_write_file,
    permission_level=PermissionLevel.MODIFY
))

registry.register(ToolDefinition(
    name="search_files",
    description="Search for files in the workspace using a glob pattern.",
    schema=SearchFilesSchema,
    executor=execute_search_files,
    permission_level=PermissionLevel.READ
))

registry.register(ToolDefinition(
    name="move_file",
    description="Move a file or directory to a new destination.",
    schema=MoveCopyFileSchema,
    executor=execute_move_file,
    permission_level=PermissionLevel.MODIFY
))

registry.register(ToolDefinition(
    name="copy_file",
    description="Copy a file or directory to a new destination.",
    schema=MoveCopyFileSchema,
    executor=execute_copy_file,
    permission_level=PermissionLevel.MODIFY
))

registry.register(ToolDefinition(
    name="delete_file",
    description="Delete a file or directory permanently.",
    schema=DeleteFileSchema,
    executor=execute_delete_file,
    permission_level=PermissionLevel.HIGH_RISK
))
