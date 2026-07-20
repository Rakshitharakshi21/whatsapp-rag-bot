"""ChromaDB interface for storing and retrieving document chunks."""
import logging
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

class VectorStore:
    """
    Manages ChromaDB collections with per-user filtering.
    
    Why ChromaDB: It's lightweight, file-based, and doesn't require a server.
    For a portfolio project, it's perfect because:
    1. Zero infrastructure cost
    2. Persists to disk automatically
    3. Supports metadata filtering (for per-user isolation)
    """
    
    def __init__(self, persist_directory: str, collection_name: str = "notes"):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        
        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"Using collection '{collection_name}' with {self.collection.count()} documents")
    
    def add_chunks(self, chunks: List[Dict[str, Any]], user_id: str) -> int:
        """Add chunks to the vector store with user metadata."""
        if not chunks:
            return 0
        
        ids = []
        embeddings = []
        metadatas = []
        documents = []
        
        for i, chunk in enumerate(chunks):
            chunk_id = f"{user_id}_{chunk['chunk_id']}"
            ids.append(chunk_id)
            embeddings.append(chunk['embedding'])
            metadatas.append({
                "user_id": user_id,
                "chunk_id": chunk['chunk_id'],
                "source": chunk.get('source', 'unknown')
            })
            documents.append(chunk['text'])
        
        # Add to ChromaDB
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents
        )
        
        logger.info(f"Added {len(chunks)} chunks for user {user_id}")
        return len(chunks)
    
    def query(self, query_embedding: List[float], user_id: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Query the vector store for relevant chunks belonging to a specific user."""
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"user_id": user_id}
        )
        
        # Format results
        formatted_results = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                formatted_results.append({
                    "text": doc,
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                    "distance": results['distances'][0][i] if results['distances'] else None
                })
        
        logger.info(f"Retrieved {len(formatted_results)} chunks for user {user_id}")
        return formatted_results