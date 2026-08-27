import json
import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class PlanStep(BaseModel):
    id: int
    description: str
    status: str = Field(default="pending", description="pending, in_progress, completed, failed")

class Plan(BaseModel):
    goal: str
    steps: List[PlanStep]

class Observation(BaseModel):
    tool: str
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None

class Reflection(BaseModel):
    goal_achieved: bool
    continue_execution: bool = Field(alias="continue")
    lesson: Optional[str] = None

def extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    """
    Extracts and parses a JSON block from a markdown string.
    Looks for ```json ... ``` blocks, or just plain JSON.
    """
    if not text:
        return None
        
    # Look for markdown JSON blocks
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # Fallback: look for just curly braces if no markdown block
        match = re.search(r'(\{.*?\})', text, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            return None
            
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None
