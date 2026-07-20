"""Configuration management with environment variables."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CHROMA_DB_DIR = DATA_DIR / "chroma_db"

# Create directories
DATA_DIR.mkdir(exist_ok=True)
CHROMA_DB_DIR.mkdir(exist_ok=True)

# API Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable not set")

# Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

# Model configurations
LLM_MODEL = "openai/gpt-oss-120b"  # Main Q&A model
LLM_MODEL_QUIZ = "openai/gpt-oss-20b"  # Quiz generation model
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# RAG Parameters
CHUNK_SIZE = 500  # Reduced from 1000 to save tokens
CHUNK_OVERLAP = 100  # Reduced from 200
TOP_K_RETRIEVAL = 3  # Reduced from 5 to save tokens

# LLM Settings
LLM_TEMPERATURE = 0.3
LLM_MAX_TOKENS = 400  # Keep responses ~1200 characters for WhatsApp

# Limits - UPDATED: Increased file size limit
MAX_PDF_SIZE_MB = 10  # Changed from 10 to 25 MB
MIN_EXTRACTED_CHARS = 25

# WhatsApp Settings
WHATSAPP_MAX_MESSAGE_LENGTH = 1200  # Characters before truncation