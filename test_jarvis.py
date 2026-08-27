from models.nemotron import NemotronProvider
from app.agent import Agent

model = NemotronProvider()
agent = Agent(model)

response = agent.execute_task(
    "Hello JARVIS. Explain what you can currently do in a short paragraph."
)

print("\n===== JARVIS =====")
print(response)
print("==================")
