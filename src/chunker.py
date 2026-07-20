"""Text chunking with overlap for RAG."""
import re
from typing import List, Dict, Any

class TextChunker:
    """
    Splits text into overlapping chunks for better retrieval.
    
    Why overlap: When relevant information falls exactly on a chunk boundary,
    overlap ensures we don't lose context.
    """
    
    def __init__(self, chunk_size: int = 1000, overlap: int = 200):
        self.chunk_size = chunk_size
        self.overlap = overlap
        
    def chunk_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Split text into overlapping chunks.
        """
        if not text or len(text) < self.chunk_size:
            return [{
                "chunk_id": 0,
                "text": text,
                "start_char": 0,
                "end_char": len(text)
            }]
        
        # Split into paragraphs
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        
        chunks = []
        current_chunk = []
        current_length = 0
        chunk_id = 0
        
        for para in paragraphs:
            para_len = len(para)
            
            # If a single paragraph is too long, split by sentences
            if para_len > self.chunk_size:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                for sent in sentences:
                    if current_length + len(sent) > self.chunk_size and current_chunk:
                        # Save current chunk
                        chunk_text = " ".join(current_chunk)
                        chunks.append({
                            "chunk_id": chunk_id,
                            "text": chunk_text,
                            "start_char": 0,
                            "end_char": len(chunk_text)
                        })
                        chunk_id += 1
                        # Keep overlap
                        if self.overlap > 0:
                            overlap_text = " ".join(current_chunk[-self.overlap//10:])
                            current_chunk = [overlap_text] if overlap_text else []
                            current_length = len(overlap_text) if overlap_text else 0
                        else:
                            current_chunk = []
                            current_length = 0
                    
                    current_chunk.append(sent)
                    current_length += len(sent)
            else:
                # Regular paragraph
                if current_length + para_len > self.chunk_size and current_chunk:
                    # Save current chunk
                    chunk_text = " ".join(current_chunk)
                    chunks.append({
                        "chunk_id": chunk_id,
                        "text": chunk_text,
                        "start_char": 0,
                        "end_char": len(chunk_text)
                    })
                    chunk_id += 1
                    # Keep overlap
                    if self.overlap > 0:
                        overlap_text = " ".join(current_chunk[-self.overlap//10:])
                        current_chunk = [overlap_text] if overlap_text else []
                        current_length = len(overlap_text) if overlap_text else 0
                    else:
                        current_chunk = []
                        current_length = 0
                
                current_chunk.append(para)
                current_length += para_len
        
        # Final chunk
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append({
                "chunk_id": chunk_id,
                "text": chunk_text,
                "start_char": 0,
                "end_char": len(chunk_text)
            })
        
        return chunks