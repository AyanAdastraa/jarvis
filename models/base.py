from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class ModelProvider(ABC):
    @abstractmethod
    def generate(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Generate a response based on the conversation history and available tools.
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """
        Verify the provider is configured correctly and reachable.
        """
        pass
