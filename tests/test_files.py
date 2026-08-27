import pytest
import os
from pathlib import Path
from tools.files import (
    execute_list_directory,
    execute_read_file,
    execute_write_file,
    execute_search_files,
    execute_move_file,
    execute_copy_file,
    execute_delete_file
)
from app.config import settings

@pytest.fixture(autouse=True)
def setup_workspace(monkeypatch, tmp_path):
    # Monkeypatch resolve_workspace_path to use a temp directory
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    
    # We patch the BASE_DIR / WORKSPACE_DIR in core.sandbox
    from core import sandbox
    monkeypatch.setattr(sandbox, "WORKSPACE_DIR", workspace_dir)
    monkeypatch.setattr(settings, "max_search_results", 5)
    monkeypatch.setattr(settings, "max_file_read_size", 1000)
    yield workspace_dir

def test_write_and_read_file():
    # Test writing
    res = execute_write_file("test.txt", "Hello World")
    assert "written successfully" in res
    
    # Test reading
    content = execute_read_file("test.txt")
    assert content == "Hello World"

def test_file_size_limit():
    execute_write_file("big.txt", "A" * 1500)
    res = execute_read_file("big.txt")
    assert "Error: File is too large" in res

def test_binary_rejection():
    from core.sandbox import resolve_workspace_path
    path = resolve_workspace_path("binary.bin")
    with open(path, "wb") as f:
        f.write(b"\xff\xfe\xff")
        
    res = execute_read_file("binary.bin")
    assert "appears to be binary" in res

def test_path_traversal():
    res = execute_read_file("../outside.txt")
    assert "Error: Relative path ../outside.txt escapes the workspace sandbox" in res

def test_list_directory():
    execute_write_file("a.txt", "a")
    execute_write_file("b.txt", "b")
    execute_write_file("dir1/c.txt", "c")
    
    res = execute_list_directory(".")
    assert "a.txt" in res
    assert "b.txt" in res
    assert "[DIR] dir1" in res

def test_search_files():
    execute_write_file("src/main.py", "print(1)")
    execute_write_file("src/utils.py", "print(2)")
    execute_write_file("tests/test_main.py", "print(3)")
    
    res = execute_search_files("*.py")
    assert "src/main.py" in res
    assert "src/utils.py" in res
    assert "tests/test_main.py" in res

def test_move_copy_delete():
    execute_write_file("source.txt", "content")
    
    # Copy
    res = execute_copy_file("source.txt", "copy.txt")
    assert "Copied" in res
    assert execute_read_file("copy.txt") == "content"
    
    # Move
    res = execute_move_file("source.txt", "moved.txt")
    assert "Moved" in res
    assert execute_read_file("moved.txt") == "content"
    assert "Error" in execute_read_file("source.txt") # not found
    
    # Delete
    res = execute_delete_file("moved.txt")
    assert "Deleted" in res
    assert "Error" in execute_read_file("moved.txt")
