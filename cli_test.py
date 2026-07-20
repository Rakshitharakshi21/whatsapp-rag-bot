#!/usr/bin/env python3
"""
CLI test for the RAG pipeline.
"""
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import GROQ_API_KEY, CHROMA_DB_DIR
from src.rag_pipeline import RAGPipeline

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    print("\n" + "="*60)
    print("📚 RAG PIPELINE TEST - CLI")
    print("="*60)
    
    # Initialize pipeline
    print("\n🔄 Initializing RAG pipeline...")
    pipeline = RAGPipeline(str(CHROMA_DB_DIR), GROQ_API_KEY)
    user_id = "test_user_001"
    
    # Step 1: Upload a PDF
    pdf_path = input("\n📄 Enter path to a PDF file: ").strip()
    
    if not Path(pdf_path).exists():
        print(f"❌ File not found: {pdf_path}")
        return
    
    print(f"\n📖 Processing: {pdf_path}")
    
    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()
    
    result = pipeline.process_pdf(pdf_bytes, user_id, Path(pdf_path).name)
    
    if result['success']:
        print(f"\n✅ Success! Added {result['chunks_added']} chunks")
        print(f"   Total characters: {result['total_chars']:,}")
    else:
        print(f"\n❌ Failed: {result['error']}")
        return
    
    # Step 2: Ask questions
    print("\n" + "="*60)
    print("❓ ASK QUESTIONS ABOUT YOUR NOTES")
    print("Type 'quit' to exit")
    print("="*60)
    
    while True:
        query = input("\n🤔 Your question: ").strip()
        
        if query.lower() in ['quit', 'exit', 'q']:
            break
        
        if not query:
            continue
        
        print("🧠 Thinking...")
        response = pipeline.ask_question(query, user_id)
        
        if response['success']:
            print(f"\n✅ Answer: {response['answer']}")
            print(f"📚 Sources: {response['num_sources']} chunks used")
        else:
            print(f"\n❌ {response['answer']}")
    
    print("\n👋 Goodbye!")

if __name__ == "__main__":
    main()