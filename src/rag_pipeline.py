"""Main RAG pipeline orchestration."""
import logging
from typing import Dict, Any
from datetime import datetime

from src.config import CHUNK_SIZE, CHUNK_OVERLAP, TOP_K_RETRIEVAL, LLM_MAX_TOKENS
from src.pdf_processor import PDFProcessor
from src.chunker import TextChunker
from src.embeddings import EmbeddingGenerator
from src.vector_store import VectorStore
from src.llm_client import LLMClient

logger = logging.getLogger(__name__)

class RAGPipeline:
    """
    End-to-end RAG pipeline: PDF → Chunks → Embeddings → Storage → Query → Answer.
    """
    
    def __init__(self, chroma_persist_dir: str, groq_api_key: str):
        self.pdf_processor = PDFProcessor()
        self.chunker = TextChunker(CHUNK_SIZE, CHUNK_OVERLAP)
        self.embedder = EmbeddingGenerator()
        self.vector_store = VectorStore(chroma_persist_dir)
        self.llm = LLMClient(groq_api_key)
        
        logger.info("RAG Pipeline initialized")
    
    def process_pdf(self, pdf_bytes: bytes, user_id: str, filename: str = "unknown.pdf") -> Dict[str, Any]:
        """Complete PDF ingestion pipeline."""
        try:
            # 1. Extract text
            text = self.pdf_processor.extract_text(pdf_bytes, filename)
            
            if not text:
                return {
                    "success": False,
                    "error": "Could not extract text. Is this a scanned/image PDF? Please send a text-based PDF."
                }
            
            if len(text) < 50:
                return {
                    "success": False,
                    "error": f"Extracted text too short ({len(text)} chars). The PDF might be scanned or corrupted."
                }
            
            # 2. Chunk the text
            chunks = self.chunker.chunk_text(text)
            
            if not chunks:
                return {
                    "success": False,
                    "error": "Failed to split text into chunks."
                }
            
            # 3. Generate embeddings
            chunk_texts = [chunk['text'] for chunk in chunks]
            embeddings = self.embedder.embed_batch(chunk_texts)
            
            # 4. Prepare chunks with embeddings
            for chunk, embedding in zip(chunks, embeddings):
                chunk['embedding'] = embedding
                chunk['source'] = filename
                chunk['timestamp'] = datetime.now().isoformat()
            
            # 5. Store in ChromaDB
            num_chunks = self.vector_store.add_chunks(chunks, user_id)
            
            logger.info(f"PDF processed: {num_chunks} chunks, {len(text)} chars for user {user_id}")
            
            return {
                "success": True,
                "chunks_added": num_chunks,
                "total_chars": len(text),
                "filename": filename
            }
            
        except Exception as e:
            logger.error(f"PDF processing failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Processing failed: {str(e)}"
            }
    
    def ask_question(self, query: str, user_id: str) -> Dict[str, Any]:
        """Answer a question using the user's stored notes."""
        try:
            logger.info(f"Asking question for user {user_id}: {query[:100]}")
            
            # 1. Embed the query
            query_embedding = self.embedder.embed_text(query)
            
            if not query_embedding:
                return {
                    "success": False,
                    "answer": "Could not process your question. Please try again.",
                    "sources": []
                }
            
            # 2. Retrieve relevant chunks
            retrieved_chunks = self.vector_store.query(
                query_embedding, 
                user_id, 
                top_k=TOP_K_RETRIEVAL
            )
            
            logger.info(f"Retrieved {len(retrieved_chunks)} chunks for user {user_id}")
            
            if not retrieved_chunks:
                return {
                    "success": False,
                    "answer": "I don't have any notes about that yet. Try uploading notes first or ask about something you've studied.",
                    "sources": []
                }
            
            # 3. Build prompt with context
            context = "\n\n---\n\n".join([chunk['text'] for chunk in retrieved_chunks])
            
            prompt = f"""
            Answer the following question based ONLY on the provided context.
            If the context doesn't contain the answer, say "I don't have information about that in your notes."
            
            Context:
            {context}
            
            Question: {query}
            
            Answer (be concise, use bullet points if helpful):"""
            
            logger.info(f"Prompt length: {len(prompt)} characters")
            logger.info(f"Number of context chunks: {len(retrieved_chunks)}")
            
            # 4. Get response from LLM
            answer = self.llm.generate(prompt, max_tokens=LLM_MAX_TOKENS)
            
            if not answer:
                logger.warning(f"LLM returned None for query: {query[:50]}")
                return {
                    "success": False,
                    "answer": "I'm having trouble generating an answer right now. Please try again in a moment.",
                    "sources": [chunk['metadata'] for chunk in retrieved_chunks]
                }
            
            logger.info(f"Generated answer: {len(answer)} characters")
            
            return {
                "success": True,
                "answer": answer.strip(),
                "sources": [chunk['metadata'] for chunk in retrieved_chunks],
                "num_sources": len(retrieved_chunks)
            }
            
        except Exception as e:
            logger.error(f"Question answering failed: {e}", exc_info=True)
            return {
                "success": False,
                "answer": "Something went wrong. Please try again.",
                "sources": []
            }