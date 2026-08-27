import pytest
from pathlib import Path
from tools.code import execute_inspect_project, execute_apply_patch

@pytest.fixture(autouse=True)
def setup_workspace(monkeypatch, tmp_path):
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    
    from core import sandbox
    monkeypatch.setattr(sandbox, "WORKSPACE_DIR", workspace_dir)
    yield workspace_dir

def test_inspect_project(setup_workspace):
    # Setup dummy project
    (setup_workspace / "requirements.txt").touch()
    (setup_workspace / "src").mkdir()
    (setup_workspace / "tests").mkdir()
    
    res = execute_inspect_project(".")
    assert "Important files found: requirements.txt" in res
    assert "Detected Languages/Frameworks: Python" in res
    assert "src" in res
    assert "tests" in res

def test_apply_patch(setup_workspace):
    file_path = setup_workspace / "main.py"
    with open(file_path, "w") as f:
        f.write("def hello():\n    print('world')\n")
        
    # Successful patch
    res = execute_apply_patch("main.py", "print('world')", "print('JARVIS')")
    assert "Patch applied successfully" in res
    assert "-    print('world')" in res
    assert "+    print('JARVIS')" in res
    
    with open(file_path, "r") as f:
        assert "print('JARVIS')" in f.read()
        
    # Failed patch (not found)
    res_fail = execute_apply_patch("main.py", "print('missing')", "print('here')")
    assert "Error: The search_content was not found exactly" in res_fail
    
    # Failed patch (multiple)
    with open(file_path, "a") as f:
        f.write("def hi():\n    print('JARVIS')\n")
        
    res_multi = execute_apply_patch("main.py", "print('JARVIS')", "print('multiple')")
    assert "Error: The search_content matched 2 times" in res_multi
