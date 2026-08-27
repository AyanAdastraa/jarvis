import json
from openai import OpenAI
from app.config import settings
from tools.registry import registry
import tools.files
import tools.memory
import tools.terminal
import tools.git
import tools.code
import tools.rag_tools

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=settings.nvidia_api_key,
)

tools = registry.get_openai_tools()
messages = [{"role": "user", "content": "hello"}]

try:
    response = client.chat.completions.create(
        model="nvidia/nemotron-3-ultra-550b-a55b",
        messages=messages,
        tools=tools
    )
    print("SUCCESS")
except Exception as e:
    print(f"ERROR: {e}")
