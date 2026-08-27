import json
from typing import List, Dict, Any, Optional
from services.conversation import ConversationService
from services.memory import MemoryService
from services.rag import RagService

class ContextLimitsError(Exception):
    pass

class ContextManager:
    def __init__(
        self,
        conversation_service: ConversationService,
        memory_service: MemoryService,
        rag_service: RagService,
        max_messages: int = 10,
        max_memories: int = 5,
        max_rag_chunks: int = 3,
        max_context_chars: int = 15000
    ):
        self.conv_service = conversation_service
        self.memory_service = memory_service
        self.rag_service = rag_service
        
        self.max_messages = max_messages
        self.max_memories = max_memories
        self.max_rag_chunks = max_rag_chunks
        self.max_context_chars = max_context_chars

    def assemble_context(self, user_id: str, conversation_id: str, latest_query: str, system_prompt: str = "") -> List[Dict[str, str]]:
        context_messages = []
        
        # 1. System Prompt (always included first)
        if system_prompt:
            context_messages.append({"role": "system", "content": system_prompt})
            
        current_chars = len(system_prompt)
        
        # 2. RAG Context
        rag_text = ""
        if latest_query:
            chunks = self.rag_service.retrieve_relevant_chunks(user_id, latest_query, limit=self.max_rag_chunks)
            if chunks:
                rag_text = "Relevant Document Excerpts:\n"
                for chunk, score in chunks:
                    rag_text += f"---\n{chunk.content}\n"
                    
        # 3. Memory Context
        memory_text = ""
        if latest_query:
            # simple search
            memories = self.memory_service.search_memory(user_id, latest_query, limit=self.max_memories)
            if memories:
                memory_text = "Relevant Long-term Memories:\n"
                for mem in memories:
                    memory_text += f"- {mem.key}: {mem.value}\n"
                    
        # Add RAG and Memory to a system injection if they exist
        injected_context = ""
        if memory_text:
            injected_context += memory_text + "\n"
        if rag_text:
            injected_context += rag_text + "\n"
            
        if injected_context:
            context_messages.append({"role": "system", "content": injected_context.strip()})
            current_chars += len(injected_context)
            
        # 4. Conversation History
        history = self.conv_service.get_history(conversation_id, limit=self.max_messages)
        
        # Ensure we don't exceed max chars with history
        history_msgs = []
        # History from service is chronological. We want to drop oldest if over limit, 
        # so we iterate backwards through the chronological list (newest first)
        for msg in reversed(history):
            msg_len = len(msg.content or "")
            if current_chars + msg_len > self.max_context_chars:
                break
                
            formatted_msg = {"role": msg.role, "content": msg.content or ""}
            try:
                meta = json.loads(msg.metadata_json or "{}")
            except:
                meta = {}
                
            if msg.role == "assistant" and "tool_calls" in meta:
                tool_calls = meta["tool_calls"]
                formatted_tool_calls = []
                for tc in tool_calls:
                    if "function" not in tc and "name" in tc:
                        formatted_tool_calls.append({
                            "id": tc.get("id"),
                            "type": "function",
                            "function": {
                                "name": tc.get("name"),
                                "arguments": tc.get("arguments")
                            }
                        })
                    else:
                        formatted_tool_calls.append(tc)
                formatted_msg["tool_calls"] = formatted_tool_calls
            elif msg.role == "tool" and "tool_call_id" in meta:
                formatted_msg["tool_call_id"] = meta["tool_call_id"]
                if "name" in meta:
                    formatted_msg["name"] = meta["name"]
                    
            history_msgs.insert(0, formatted_msg)
            current_chars += msg_len
            
        context_messages.extend(history_msgs)
        
        return context_messages
