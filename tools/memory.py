from pydantic import BaseModel, Field
from core.permissions import PermissionLevel
from tools.registry import ToolDefinition, registry
from services.memory import MemoryService
from core.db import SessionLocal
import json

class SaveMemorySchema(BaseModel):
    category: str = Field(..., description="Category of the memory (e.g., preference, fact, project, goal)")
    key: str = Field(..., description="Key or subject of the memory")
    value: str = Field(..., description="Value or detail of the memory")
    importance: float = Field(1.0, description="Importance from 0.0 to 1.0")

class SearchMemorySchema(BaseModel):
    query: str = Field(..., description="Search query")
    category: str = Field(None, description="Optional category to filter by")
    limit: int = Field(5, description="Max results")

class GetMemorySchema(BaseModel):
    memory_id: str = Field(..., description="ID of the memory")

class DeleteMemorySchema(BaseModel):
    memory_id: str = Field(..., description="ID of the memory")

def execute_save_memory(category: str, key: str, value: str, importance: float, user_id: str = None) -> str:
    if not user_id: return "Error: user_id missing from context"
    with SessionLocal() as db:
        svc = MemoryService(db)
        try:
            mem = svc.save_memory(user_id, category, key, value, importance, source="agent")
            return f"Memory saved successfully. ID: {mem.id}"
        except Exception as e:
            return f"Error saving memory: {e}"

def execute_search_memory(query: str, category: str = None, limit: int = 5, user_id: str = None) -> str:
    if not user_id: return "Error: user_id missing from context"
    with SessionLocal() as db:
        svc = MemoryService(db)
        try:
            results = svc.search_memory(user_id, query, category, limit)
            if not results:
                return "No memories found."
            return json.dumps([{"id": r.id, "category": r.category, "key": r.key, "value": r.value} for r in results])
        except Exception as e:
            return f"Error searching memory: {e}"

def execute_get_memory(memory_id: str, user_id: str = None) -> str:
    if not user_id: return "Error: user_id missing from context"
    with SessionLocal() as db:
        svc = MemoryService(db)
        mem = svc.get_memory(user_id, memory_id)
        if not mem:
            return "Memory not found."
        return json.dumps({"id": mem.id, "category": mem.category, "key": mem.key, "value": mem.value})

def execute_delete_memory(memory_id: str, user_id: str = None) -> str:
    if not user_id: return "Error: user_id missing from context"
    with SessionLocal() as db:
        svc = MemoryService(db)
        success = svc.delete_memory(user_id, memory_id)
        return "Memory deleted." if success else "Memory not found."

registry.register(ToolDefinition(
    name="save_memory",
    description="Save a long-term memory for the user. Used to remember facts, preferences, and details.",
    schema=SaveMemorySchema,
    executor=execute_save_memory,
    permission_level=PermissionLevel.MODIFY
))

registry.register(ToolDefinition(
    name="search_memory",
    description="Search the user's long-term memory for specific keywords.",
    schema=SearchMemorySchema,
    executor=execute_search_memory,
    permission_level=PermissionLevel.READ
))

registry.register(ToolDefinition(
    name="get_memory",
    description="Retrieve a specific memory by ID.",
    schema=GetMemorySchema,
    executor=execute_get_memory,
    permission_level=PermissionLevel.READ
))

registry.register(ToolDefinition(
    name="delete_memory",
    description="Delete a specific memory by ID.",
    schema=DeleteMemorySchema,
    executor=execute_delete_memory,
    permission_level=PermissionLevel.MODIFY
))
