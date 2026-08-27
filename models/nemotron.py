from typing import List, Dict, Any, Optional
from openai import OpenAI
from app.config import settings
from app.logger import get_logger
from models.base import ModelProvider

logger = get_logger(__name__)

class NemotronProvider(ModelProvider):
    def __init__(self):
        if not settings.nvidia_api_key:
            logger.warning("NVIDIA_API_KEY is not set.")
            
        self.client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=settings.nvidia_api_key or "DUMMY_KEY_FOR_TESTS",
            timeout=float(settings.nemotron_timeout),
            max_retries=2,
        )
        self.model = settings.complex_model or settings.nvidia_model

    def generate(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        logger.info(f"Calling Nemotron ({self.model}) with {len(messages)} messages.", extra={"tools_provided": bool(tools)})
        
        kwargs = {
            "model": self.model,
            "messages": messages,
            "max_tokens": settings.model_max_tokens,
        }
        
        if tools:
            kwargs["tools"] = tools
            
        try:
            response = self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message
            
            result = {
                "content": message.content,
                "tool_calls": []
            }
            
            if message.tool_calls:
                for tc in message.tool_calls:
                    result["tool_calls"].append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })
                    
            return result
        except Exception as e:
            logger.error("Failed to generate response from Nemotron.", exc_info=True)
            raise

    def health_check(self) -> bool:
        if not settings.nvidia_api_key:
            return False
        try:
            # A simple lightweight call to verify auth
            self.client.models.list()
            return True
        except Exception as e:
            logger.error("Nemotron health check failed.", exc_info=True)
            return False
