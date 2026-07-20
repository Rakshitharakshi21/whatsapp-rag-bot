"""First-time user onboarding and welcome messages."""
import logging
from src.database import Database

logger = logging.getLogger(__name__)
db = Database()

# Welcome message for first-time users
WELCOME_MESSAGE = """👋 *Welcome to your Study Assistant Bot!*

I'm here to help you learn from your PDF notes.

📚 *What I can do:*
• Upload any PDF and I'll extract the content
• Ask me questions about your notes
• Generate quizzes to test your knowledge
• Create flashcards for revision
• Track your study streaks

🚀 *To get started:*
Simply send me a PDF file!

*Commands you can use anytime:*
• `menu` - Show options
• `help` - Show this message
• `stop` - Stop current activity

Let's get started! Send a PDF to begin. 📄"""


def is_new_user(user_id: str) -> bool:
    """
    Check if user is new (never interacted before).
    
    Uses database only (not ChromaDB) to determine if we've seen this user.
    """
    return not db.user_exists(user_id)


def get_welcome_message() -> str:
    """Get the welcome message for new users."""
    return WELCOME_MESSAGE


def get_help_message() -> str:
    """Get the help message."""
    return WELCOME_MESSAGE


def get_menu_message() -> str:
    """Get the menu message (reused from main)."""
    return """📋 *What would you like to do?*

1️⃣ Summarize entire PDF
2️⃣ Summarize specific topic
3️⃣ Generate quiz
4️⃣ Generate flashcards
5️⃣ True/False questions

Reply with a number, or type 'menu' anytime to see this again."""