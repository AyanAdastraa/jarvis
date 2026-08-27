import difflib
from pydantic import BaseModel, Field
from app.logger import get_logger
from tools.registry import registry, ToolDefinition
from core.permissions import PermissionLevel
from core.sandbox import resolve_workspace_path, PathTraversalError

logger = get_logger(__name__)

class InspectProjectSchema(BaseModel):
    path: str = Field(default=".", description="Path to the project directory.")

def execute_inspect_project(path: str = ".", user_id: str = None) -> str:
    try:
        cwd = resolve_workspace_path(path)
        if not cwd.is_dir():
            return f"Error: '{path}' is not a directory."
            
        important_files = ["package.json", "requirements.txt", "setup.py", "pyproject.toml", "Cargo.toml", "go.mod", "Makefile", "Dockerfile", ".gitignore"]
        detected = []
        top_dirs = []
        
        for item in cwd.iterdir():
            if item.name in important_files and item.is_file():
                detected.append(item.name)
            elif item.is_dir() and not item.name.startswith("."):
                top_dirs.append(item.name)
                
        output = [f"Project Inspection for '{path}':"]
        output.append(f"Top-level directories: {', '.join(top_dirs) if top_dirs else 'None'}")
        output.append(f"Important files found: {', '.join(detected) if detected else 'None'}")
        
        languages = []
        if "package.json" in detected:
            languages.append("Node.js/JavaScript/TypeScript")
        if any(f in detected for f in ["requirements.txt", "setup.py", "pyproject.toml"]):
            languages.append("Python")
        if "Cargo.toml" in detected:
            languages.append("Rust")
        if "go.mod" in detected:
            languages.append("Go")
            
        output.append(f"Detected Languages/Frameworks: {', '.join(languages) if languages else 'Unknown'}")
        
        return "\n".join(output)
    except PathTraversalError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

class ApplyPatchSchema(BaseModel):
    path: str = Field(..., description="Path to the file to modify.")
    search_content: str = Field(..., description="The exact existing content to replace.")
    replace_content: str = Field(..., description="The new content to insert.")

def execute_apply_patch(path: str, search_content: str, replace_content: str, user_id: str = None) -> str:
    try:
        resolved_path = resolve_workspace_path(path)
        if not resolved_path.is_file():
            return f"Error: '{path}' does not exist or is not a file."
            
        with open(resolved_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        if search_content not in content:
            return "Error: The search_content was not found exactly in the file. Ensure you match whitespace and context perfectly."
            
        count = content.count(search_content)
        if count > 1:
            return f"Error: The search_content matched {count} times in the file. Make your search block more specific."
            
        new_content = content.replace(search_content, replace_content)
        
        # Generate diff
        diff = difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=path,
            tofile=path
        )
        diff_text = "".join(diff)
        
        with open(resolved_path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        return f"Patch applied successfully.\n\nDiff:\n{diff_text}"
        
    except PathTraversalError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

registry.register(ToolDefinition(
    name="inspect_project",
    description="Inspect a project structure to identify languages, packages, and frameworks.",
    schema=InspectProjectSchema,
    executor=execute_inspect_project,
    permission_level=PermissionLevel.READ
))

registry.register(ToolDefinition(
    name="apply_patch",
    description="Replace an exact block of code with a new block of code.",
    schema=ApplyPatchSchema,
    executor=execute_apply_patch,
    permission_level=PermissionLevel.MODIFY
))
