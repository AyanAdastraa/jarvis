from typing import List, Dict, Any, Optional
import json
from app.logger import get_logger
from app.config import settings
from models.base import ModelProvider
from tools.registry import registry
from core.permissions import PermissionLevel, requires_confirmation, check_permission
from core.context import ContextManager
from core.planning import extract_json_block
import tools.memory
import tools.rag_tools

logger = get_logger(__name__)

class Agent:
    def __init__(self, model_provider: ModelProvider, context_manager: Optional[ContextManager] = None, max_iterations: int = 10):
        self.model = model_provider
        self.context_manager = context_manager
        self.max_iterations = max_iterations
        self.max_tool_calls = settings.agent_max_tool_calls
        self.max_replans = settings.agent_max_replans
        
    def execute_task(self, user_request: str, user_id: str = "default_user", conversation_id: str = "default_conv") -> str:
        """
        Main execution loop for a user request.
        Implements PLAN -> ACT -> OBSERVE -> REFLECT for complex tasks.
        Simple tasks return immediately.
        """
        logger.info("Starting new agent task.", extra={"user_id": user_id, "conversation_id": conversation_id, "user_request": user_request})
        
        system_prompt = (
            "You are JARVIS, a highly capable and professional personal AI assistant.\n"
            "You have access to tools to accomplish tasks, manage memory, and retrieve documents.\n\n"
            "COGNITIVE LOOP INSTRUCTIONS:\n"
            "If the user's request requires using tools or is a multi-step task, you must follow this strict sequence:\n"
            "1. PLAN: First, output a JSON plan in a markdown block. Do NOT call any tools yet.\n"
            "```json\n"
            "{\n"
            "  \"goal\": \"...\",\n"
            "  \"steps\": [{\"id\": 1, \"description\": \"...\", \"status\": \"pending\"}]\n"
            "}\n"
            "```\n"
            "2. ACT: The system will then prompt you to ACT. You should then call the appropriate tool.\n"
            "3. OBSERVE: The system will execute the tool and provide the observation.\n"
            "4. REFLECT: The system will prompt you to REFLECT. You must output a JSON reflection:\n"
            "```json\n"
            "{\n"
            "  \"goal_achieved\": true/false,\n"
            "  \"continue\": true/false,\n"
            "  \"lesson\": \"optional lesson to remember\"\n"
            "}\n"
            "```\n"
            "If 'continue' is true, we will loop back to ACT or REPLAN. If 'goal_achieved' is true, you must generate a final user-facing response in the next turn.\n"
            "For simple conversational requests (like 'hi', 'thanks'), ignore this loop and just reply naturally."
        )
        
        if self.context_manager:
            self.context_manager.conv_service.save_message(conversation_id, "user", user_request)
            
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_request}]
        if self.context_manager:
            messages = self.context_manager.assemble_context(user_id, conversation_id, user_request, system_prompt)
            
        tool_call_count = 0
        replan_count = 0
        final_response = None
        
        for iteration in range(self.max_iterations):
            logger.info(f"Agent iteration {iteration + 1}/{self.max_iterations}")
            
            try:
                # Always pass tools; ModelRouter strips them for FastModel
                response = self.model.generate(messages, tools=registry.get_openai_tools())
            except Exception as e:
                logger.error("Model generation failed during agent loop.", exc_info=True)
                return f"Error: Unable to communicate with the model provider. Details: {str(e)}"
                
            assistant_content = response.get("content") or ""
            tool_calls = response.get("tool_calls", [])
            
            assistant_message = {"role": "assistant"}
            if assistant_content:
                assistant_message["content"] = assistant_content
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls

            if assistant_content or tool_calls:
                if self.context_manager:
                    metadata = {}
                    if tool_calls:
                        metadata["tool_calls"] = tool_calls
                    self.context_manager.conv_service.save_message(
                        conversation_id,
                        "assistant",
                        assistant_content or "",
                        metadata=metadata if metadata else None
                    )
            
            messages.append(assistant_message)
            
            # 1. Simple request check: no tools, no JSON blocks, first iteration
            if iteration == 0 and not tool_calls:
                json_block = extract_json_block(assistant_content)
                if not json_block or "goal" not in json_block:
                    logger.info("Simple request processed without agent loop.")
                    return assistant_content
            
            # 2. Check for PLAN block
            json_block = extract_json_block(assistant_content)
            if json_block and "goal" in json_block and "steps" in json_block:
                logger.info("[AGENT] Goal identified and Plan created.")
                prompt = "[AGENT] Plan acknowledged. Please ACT by calling the tool for the first step."
                if self.context_manager:
                    self.context_manager.conv_service.save_message(conversation_id, "user", prompt)
                messages.append({"role": "user", "content": prompt})
                continue
                
            # 3. Check for REFLECT block
            if json_block and "goal_achieved" in json_block and "continue" in json_block:
                logger.info(f"[AGENT] Reflection received: goal_achieved={json_block.get('goal_achieved')}, continue={json_block.get('continue')}")
                
                # Save lesson if present
                if json_block.get("lesson") and self.context_manager:
                    logger.info(f"[AGENT] Saving lesson: {json_block['lesson']}")
                    tools.memory.save_memory(
                        key=f"lesson_{conversation_id}_{iteration}",
                        value=json_block["lesson"],
                        category="lesson",
                        user_id=user_id
                    )
                
                if json_block.get("goal_achieved"):
                    logger.info("[AGENT] Task completed.")
                    prompt = "[AGENT] Excellent. Please provide the final, concise response to the user. Do not expose your internal reasoning or JSON."
                    if self.context_manager:
                        self.context_manager.conv_service.save_message(conversation_id, "user", prompt)
                    messages.append({"role": "user", "content": prompt})
                    continue
                elif json_block.get("continue"):
                    prompt = "[AGENT] Please ACT on the next step."
                    if self.context_manager:
                        self.context_manager.conv_service.save_message(conversation_id, "user", prompt)
                    messages.append({"role": "user", "content": prompt})
                    continue
                else:
                    # Not achieved and not continue -> Replan
                    replan_count += 1
                    if replan_count > self.max_replans:
                        logger.warning("Agent reached maximum replans.")
                        return "Error: I encountered too many issues and could not complete the task."
                    logger.info(f"[AGENT] Replanning ({replan_count}/{self.max_replans}).")
                    prompt = "[AGENT] Please output a new PLAN in JSON format to recover from the failure or pursue an alternative approach."
                    if self.context_manager:
                        self.context_manager.conv_service.save_message(conversation_id, "user", prompt)
                    messages.append({"role": "user", "content": prompt})
                    continue
            
            # 4. Handle Tool Calls (ACT)
            if tool_calls:
                tool_call_count += len(tool_calls)
                if tool_call_count > self.max_tool_calls:
                    logger.warning("Agent reached maximum tool calls.")
                    return "Error: I executed too many tools and had to stop."
                    
                for tool_call in tool_calls:
                    tool_func = tool_call.get("function", tool_call)
                    tool_name = tool_func["name"]
                    tool_id = tool_call.get("id", "test_id")
                    try:
                        arguments = json.loads(tool_func["arguments"])
                    except json.JSONDecodeError:
                        arguments = {}
                    
                    # Execute tool
                    tool_result, success, error_msg = self._execute_tool_with_status(tool_name, arguments, user_id)
                    
                    # OBSERVE
                    observation = {
                        "tool": tool_name,
                        "success": success,
                        "result": tool_result,
                        "error": error_msg
                    }
                    obs_str = f"[OBSERVE]\n```json\n{json.dumps(observation, indent=2)}\n```"
                    logger.info(f"[OBSERVE] {tool_name} success={success}")
                    
                    if self.context_manager:
                        self.context_manager.conv_service.save_message(
                            conversation_id,
                            "tool",
                            obs_str,
                            metadata={"tool_call_id": tool_id, "name": tool_name}
                        )
                        
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": obs_str
                    })
                    
                prompt = "[AGENT] Please REFLECT on the observations. Output a JSON reflection block."
                if self.context_manager:
                    self.context_manager.conv_service.save_message(conversation_id, "user", prompt)
                messages.append({"role": "user", "content": prompt})
                continue
                
            # 5. Final Response
            if assistant_content and not tool_calls and iteration > 0:
                # Check if it's just generating final text after reflection
                logger.info("[AGENT] Returning final response to user.")
                if self.context_manager:
                    self.context_manager.conv_service.save_message(conversation_id, "assistant", assistant_content)
                return assistant_content
                
        logger.warning(f"Agent reached max iterations ({self.max_iterations}).")
        return "Error: I reached my maximum thinking limits before completing the task."

    def _execute_tool_with_status(self, tool_name: str, arguments: Dict[str, Any], user_id: str) -> tuple[str, bool, Optional[str]]:
        """Returns (result_string, success_bool, error_string_if_any)"""
        tool = registry.get_tool(tool_name)
        if not tool:
            logger.error(f"Model requested unknown tool: {tool_name}")
            return "", False, f"Tool '{tool_name}' not found."
            
        logger.info(f"[TOOL] Executing {tool_name}", extra={"arguments": arguments})
        
        try:
            validated_args = tool.schema(**arguments)
        except Exception as e:
            logger.error(f"Tool {tool_name} argument validation failed.", exc_info=True)
            return "", False, f"Invalid arguments: {str(e)}"
            
        try:
            import inspect
            sig = inspect.signature(tool.executor)
            if "user_id" in sig.parameters or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                result = tool.executor(**validated_args.model_dump(), user_id=user_id)
            else:
                result = tool.executor(**validated_args.model_dump())
            return str(result), True, None
        except Exception as e:
            logger.error(f"Tool {tool_name} execution failed.", exc_info=True)
            return "", False, str(e)

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any], user_id: str = "default_user") -> str:
        """Alias for backward compatibility with older tests."""
        result, success, error = self._execute_tool_with_status(tool_name, arguments, user_id)
        if not success:
            # Recreate old error format for tests
            if "not found" in error or "Invalid arguments" in error:
                return f"Error: {error}"
            return f"Error: Tool execution failed. Details: {error}"
        return result
