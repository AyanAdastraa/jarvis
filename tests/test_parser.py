import pytest
import os
from pathlib import Path
from core.parser import parse_document, DocumentParseError
from tools.pdf import create_professional_pdf
import docx
import csv

def test_parse_empty_txt(tmp_path):
    p = tmp_path / "empty.txt"
    p.write_text("")
    doc = parse_document(str(p))
    assert doc.content == ""
    assert doc.mime_type == "text/plain"

def test_parse_txt(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text("Hello world")
    doc = parse_document(str(p))
    assert doc.content == "Hello world"

def test_parse_md(tmp_path):
    p = tmp_path / "test.md"
    p.write_text("# Markdown\n\nContent")
    doc = parse_document(str(p))
    assert doc.content == "# Markdown\n\nContent"
    assert doc.mime_type == "text/markdown"

def test_parse_csv(tmp_path):
    p = tmp_path / "test.csv"
    with open(p, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["col1", "col2"])
        writer.writerow(["val1", "val2"])
        
    doc = parse_document(str(p))
    assert "col1, col2" in doc.content
    assert "val1, val2" in doc.content
    assert doc.mime_type == "text/csv"

def test_parse_docx(tmp_path):
    p = tmp_path / "test.docx"
    doc = docx.Document()
    doc.add_paragraph("Docx content")
    doc.save(p)
    
    parsed = parse_document(str(p))
    assert "Docx content" in parsed.content
    assert parsed.mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

def test_parse_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr("core.sandbox.WORKSPACE_DIR", tmp_path)
    pdf_path_str = create_professional_pdf("Test", "Pdf content", filename="test.pdf")
    
    parsed = parse_document(pdf_path_str)
    assert "Test" in parsed.content
    assert "Pdf content" in parsed.content
    assert parsed.mime_type == "application/pdf"

def test_parse_unsupported(tmp_path):
    p = tmp_path / "test.xyz"
    p.write_text("random")
    with pytest.raises(DocumentParseError, match="Unsupported file type"):
        parse_document(str(p))

def test_parse_missing():
    with pytest.raises(DocumentParseError, match="File not found"):
        parse_document("nonexistent.txt")
