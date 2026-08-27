import pytest
from core.chunker import DeterministicChunker, ChunkerConfigError

def test_chunker_invalid_config():
    with pytest.raises(ChunkerConfigError):
        DeterministicChunker(chunk_size=100, overlap=100)
    with pytest.raises(ChunkerConfigError):
        DeterministicChunker(chunk_size=100, overlap=101)
    with pytest.raises(ChunkerConfigError):
        DeterministicChunker(chunk_size=0, overlap=0)
    with pytest.raises(ChunkerConfigError):
        DeterministicChunker(chunk_size=-10, overlap=5)

def test_chunker_empty():
    chunker = DeterministicChunker(chunk_size=10, overlap=2)
    assert chunker.chunk_text("") == []

def test_chunker_short():
    chunker = DeterministicChunker(chunk_size=10, overlap=2)
    chunks = chunker.chunk_text("hello")
    assert chunks == ["hello"]

def test_chunker_long():
    chunker = DeterministicChunker(chunk_size=10, overlap=2)
    # text is 20 chars long
    text = "0123456789abcdefghij"
    chunks = chunker.chunk_text(text)
    
    # Chunk 1: 0..9 ("0123456789")
    # Overlap 2 chars: "89"
    # Chunk 2: "89" + next 8 = "89abcdefgh"
    # Overlap 2 chars: "gh"
    # Chunk 3: "gh" + "ij" = "ghij"
    
    assert chunks[0] == "0123456789"
    assert chunks[1] == "89abcdefgh"
    assert chunks[2] == "ghij"
    assert len(chunks) == 3

def test_chunker_deterministic():
    chunker = DeterministicChunker(chunk_size=50, overlap=10)
    text = "A" * 1000 + "B" * 500 + "C" * 100
    
    run1 = chunker.chunk_text(text)
    run2 = chunker.chunk_text(text)
    
    assert run1 == run2
