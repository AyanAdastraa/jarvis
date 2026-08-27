import pytest
import os
from pathlib import Path
from app.agent import Agent
from app.config import settings

# Import tools so they register
import tools.files
import tools.terminal
import tools.code

@pytest.fixture
def agent():
    from tests.test_agent_v2 import MockModel
    provider = MockModel([])
    return Agent(model_provider=provider)

@pytest.fixture(autouse=True)
def setup_workspace(monkeypatch, tmp_path):
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    
    from core import sandbox
    monkeypatch.setattr(sandbox, "WORKSPACE_DIR", workspace_dir)
    
    # Create sample project with a bug
    sample_dir = workspace_dir / "sample_project"
    sample_dir.mkdir()
    
    calc_py = sample_dir / "calc.py"
    calc_py.write_text("def add(a, b):\n    return a - b\n")
    
    test_calc_py = sample_dir / "test_calc.py"
    test_calc_py.write_text(
        "import sys, os\n"
        "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
        "from calc import add\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
    )
    
    yield workspace_dir

def test_agent_can_fix_bug(setup_workspace):
    from tests.test_agent_v2 import MockModel
    import json
    
    responses = [
        # 1. Inspect project
        {
            "content": "",
            "tool_calls": [{
                "id": "call_1",
                "name": "inspect_project",
                "arguments": json.dumps({"path": "sample_project"})
            }]
        },
        # 2. Read file
        {
            "content": None,
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "run_python",
                    "arguments": json.dumps({"code": "print('hello world')", "timeout_seconds": 5})
                }
            }]
        },
        # 3. Apply patch
        {
            "content": "",
            "tool_calls": [{
                "id": "call_3",
                "name": "apply_patch",
                "arguments": json.dumps({
                    "path": "sample_project/calc.py",
                    "search_content": "return a - b",
                    "replace_content": "return a + b"
                })
            }]
        },
        # 4. Run pytest
        {
            "content": "",
            "tool_calls": [{
                "id": "call_4",
                "name": "execute_command",
                "arguments": json.dumps({
                    "command": "pytest sample_project/test_calc.py"
                })
            }]
        },
        # 5. Final response
        {
            "content": "I fixed the bug and tests passed.",
            "tool_calls": []
        }
    ]
    
    agent = Agent(model_provider=MockModel(responses))
    
    result = agent.execute_task("Fix the subtract bug in calc", "u1", "conv1")
    
    # 7. Final response reflects result
    assert result == "I fixed the bug and tests passed."
    
    # 4. Actual file changed
    with open(setup_workspace / "sample_project" / "calc.py", "r") as f:
        assert "return a + b" in f.read()

