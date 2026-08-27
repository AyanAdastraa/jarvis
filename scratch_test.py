import os
import sys

# Ensure jarvis root is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from models.nemotron import NemotronProvider
from app.config import settings

def run():
    print(f"API key present: {bool(settings.nvidia_api_key)}")
    if not settings.nvidia_api_key:
        print("Skipping real smoke test since no key is present.")
        return
        
    provider = NemotronProvider()
    print(f"Health check: {provider.health_check()}")
    
    messages = [{"role": "user", "content": "What is 2+2? Reply with just the number."}]
    response = provider.generate(messages)
    print(f"Response: {response['content']}")

if __name__ == "__main__":
    run()
