import os
import pytest
from pathlib import Path
from tools.pdf import create_professional_pdf

def test_pdf_generation(tmp_path, monkeypatch):
    # Monkeypatch the WORKSPACE_DIR so it writes to the tmp_path
    monkeypatch.setattr("core.sandbox.WORKSPACE_DIR", tmp_path)
    
    content = """
    # Test Document
    ## A Subheading
    This is a test document.
    """
    
    pdf_path_str = create_professional_pdf(
        title="Test PDF",
        content=content,
        filename="pytest_test.pdf"
    )
    
    pdf_path = Path(pdf_path_str)
    
    # Verify file exists
    assert pdf_path.exists()
    
    # Verify file size > 0
    assert pdf_path.stat().st_size > 0
    
    # Verify it has PDF signature
    with open(pdf_path, "rb") as f:
        header = f.read(4)
        assert header == b"%PDF"
