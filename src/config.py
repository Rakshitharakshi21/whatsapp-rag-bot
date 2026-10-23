"""Configuration management with environment variables.

Why this file exists:
Centralizes all application configurations, loads environment variables, validates credentials
at startup with clear diagnostics, and defines system limits and models.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Project paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CHROMA_DB_DIR = DATA_DIR / "chroma_db"

# Create directories
DATA_DIR.mkdir(exist_ok=True)
CHROMA_DB_DIR.mkdir(exist_ok=True)

# API Keys & Credentials
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
DEV_MODE = os.getenv("DEV_MODE", "0") == "1"

# Model configurations
LLM_MODEL = "openai/gpt-oss-120b"  # Main Q&A model
LLM_MODEL_QUIZ = "openai/gpt-oss-20b"  # Quiz generation model
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# RAG Parameters
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
TOP_K_RETRIEVAL = 3

# LLM Settings
LLM_TEMPERATURE = 0.3
LLM_MAX_TOKENS = 400

# Limits
MAX_PDF_SIZE_MB = 10
MIN_EXTRACTED_CHARS = 25

# WhatsApp Settings
WHATSAPP_MAX_MESSAGE_LENGTH = 1200


def print_config_banner() -> dict:
    """Validate and log presence of all required environment variables."""
    status = {
        "GROQ_API_KEY": bool(GROQ_API_KEY),
        "TWILIO_ACCOUNT_SID": bool(TWILIO_ACCOUNT_SID),
        "TWILIO_AUTH_TOKEN": bool(TWILIO_AUTH_TOKEN),
        "TWILIO_WHATSAPP_NUMBER": bool(TWILIO_WHATSAPP_NUMBER),
    }

    banner = "\n" + "=" * 55 + "\n"
    banner += "  WHATSAPP RAG BOT - CONFIGURATION CHECK\n"
    banner += "=" * 55 + "\n"
    for key, present in status.items():
        val_str = "PRESENT" if present else "MISSING [!]"
        banner += f"  {key:<25} : {val_str}\n"
    banner += "=" * 55

    logger.info(banner)
    print(banner)
    return status


# Run banner on import
_config_status = print_config_banner()
if not GROQ_API_KEY and not os.getenv("TESTING"):
    logger.warning("GROQ_API_KEY is not set. Groq queries will fail.")