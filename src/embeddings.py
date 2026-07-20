"""Embedding generation using local sentence-transformers."""
import logging
from typing import List
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class EmbeddingGenerator:
    """
    Generates embeddings using sentence-transformers.
    
    Why local: This avoids API costs for embeddings. all-MiniLM-L6-v2 is
    lightweight (80MB) and performs well for RAG.
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = None
        
    def _load_model(self):
        """Lazy-load the model to avoid startup delays."""
        if self.model is None:
            logger.info(f"Loading embedding model: {self.model_name}")
            self.model = SentenceTransformer(self.model_name)
            logger.info("Model loaded successfully")
    
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        if not text or not text.strip():
            return []
        self._load_model()
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts efficiently."""
        if not texts:
            return []
        self._load_model()
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return [emb.tolist() for emb in embeddings]
    
    def get_embedding_dimension(self) -> int:
        """Return the dimension of the embedding vectors."""
        return 384  # all-MiniLM-L6-v2 fixed dimension