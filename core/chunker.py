from typing import List

class ChunkerConfigError(Exception):
    pass

class DeterministicChunker:
    def __init__(self, chunk_size: int = 1000, overlap: int = 100):
        if overlap >= chunk_size:
            raise ChunkerConfigError(f"overlap ({overlap}) must be less than chunk_size ({chunk_size})")
        if chunk_size <= 0 or overlap < 0:
            raise ChunkerConfigError("chunk_size must be positive and overlap must be non-negative")
            
        self.chunk_size = chunk_size
        self.overlap = overlap
        
    def chunk_text(self, text: str) -> List[str]:
        if not text:
            return []
            
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            end = min(start + self.chunk_size, text_len)
            chunk = text[start:end]
            chunks.append(chunk)
            
            if end == text_len:
                break
                
            start += (self.chunk_size - self.overlap)
            
        return chunks
