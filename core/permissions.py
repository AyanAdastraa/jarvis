from enum import IntEnum
from app.logger import get_logger

logger = get_logger(__name__)

class PermissionLevel(IntEnum):
    READ = 0            # Level 0: Read-only information (files, memory)
    MODIFY = 1          # Level 1: Modify workspace files
    EXECUTE = 2         # Level 2: Execute safe terminal commands/tests
    GIT = 3             # Level 3: Git operations (commit)
    EXTERNAL_COMM = 4   # Level 4: External communication (Phase 4)
    HIGH_RISK = 5       # Level 5: Delete, destructive, push

def requires_confirmation(level: PermissionLevel, action_details: str = "") -> bool:
    """
    Determine if an action requires explicit user confirmation.
    """
    if level >= PermissionLevel.HIGH_RISK:
        logger.info("Action blocked: Requires explicit confirmation for destructive actions.", extra={"action": action_details})
        return True
        
    if level == PermissionLevel.EXTERNAL_COMM:
        logger.info("Action blocked: Requires explicit confirmation for external communication.", extra={"action": action_details})
        return True
        
    # Lower levels don't require explicit human intervention by default
    return False

def check_permission(requested_level: PermissionLevel, granted_level: PermissionLevel) -> bool:
    """
    Check if the requested permission level is within the granted level.
    """
    allowed = requested_level <= granted_level
    if not allowed:
        logger.warning(f"Permission denied: Requested level {requested_level.name}, granted level {granted_level.name}")
    return allowed
