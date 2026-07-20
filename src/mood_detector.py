"""Mood detection and encouragement system."""
import logging
import re
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

# Keywords indicating stress/frustration
STRESS_KEYWORDS = [
    "stressed", "stress", "tired", "exhausted", "hard", "difficult", "confused", 
    "confusing", "give up", "giving up", "frustrated", "frustrating", "struggling",
    "struggle", "overwhelmed", "overwhelming", "can't", "cannot", "too much",
    "ugh", "argh", "annoying", "annoyed", "tough", "headache", "brain",
    "don't understand", "doesn't make sense", "not getting", "no idea",
    "hate", "worst", "bad", "terrible", "awful", "useless", "stupid"
]

# Keywords indicating positive mood (used to reset)
POSITIVE_KEYWORDS = [
    "great", "good", "awesome", "amazing", "nice", "love", "happy", "excited",
    "easy", "simple", "understood", "finally", "yes", "got it", "perfect"
]

# Encouragement messages for different moods
ENCOURAGEMENT_MESSAGES = [
    "💪 You've got this! Take a deep breath and try again.",
    "🧠 Learning is a journey, not a race. Every wrong answer is a step closer to understanding.",
    "🌟 You're doing better than you think! Keep going!",
    "📚 It's okay to find things hard — that's where growth happens!",
    "💡 Remember: even experts were once beginners. You're learning!",
    "🎯 Focus on progress, not perfection. You're getting better!",
    "🙌 I believe in you! Take a moment and try again.",
    "🌱 Every challenge you face is making you stronger. Keep pushing!",
]

# Encouragement with flashcard suggestion
ENCOURAGEMENT_FLASHCARD = "💡 Want to switch to flashcards instead? They're less pressure and great for building basics!"


def detect_mood(text: str) -> Tuple[bool, Optional[str]]:
    """
    Detect if user is showing signs of frustration.
    
    Returns:
        Tuple of (is_frustrated, matched_keyword)
    """
    text_lower = text.lower().strip()
    
    # Check for positive keywords first (reset mood)
    for keyword in POSITIVE_KEYWORDS:
        if keyword in text_lower:
            return False, None
    
    # Check for stress keywords
    for keyword in STRESS_KEYWORDS:
        if keyword in text_lower:
            logger.info(f"Mood detected: {keyword}")
            return True, keyword
    
    # Check for 3+ wrong answers pattern (handled in main.py)
    return False, None


def get_encouragement_message(consecutive_wrong: int = 0) -> str:
    """
    Get an appropriate encouragement message.
    
    Args:
        consecutive_wrong: Number of consecutive wrong answers
    
    Returns:
        str: Encouragement message
    """
    import random
    
    # More severe encouragement for more wrongs
    if consecutive_wrong >= 3:
        message = random.choice(ENCOURAGEMENT_MESSAGES)
        return f"{message}\n\n{ENCOURAGEMENT_FLASHCARD}"
    else:
        return random.choice(ENCOURAGEMENT_MESSAGES)


def get_easier_quiz_prompt(original_prompt: str) -> str:
    """
    Modify quiz generation prompt to be easier and more encouraging.
    
    Args:
        original_prompt: Original quiz generation prompt
    
    Returns:
        str: Modified prompt for easier questions
    """
    # Add instructions for easier questions with encouraging tone
    modifications = [
        "\n\nIMPORTANT: Generate SLIGHTLY EASIER questions than usual.",
        "Focus on fundamental concepts and core definitions.",
        "Avoid tricky or edge-case questions.",
        "Use encouraging and clear language.",
        "Make questions more straightforward and less ambiguous.",
        "Add a brief encouraging note after each question if helpful."
    ]
    
    modified = original_prompt + "\n\n" + "\n".join(modifications)
    
    # Replace "generate X questions" with "generate X easier questions"
    modified = re.sub(
        r'generate (\d+) questions',
        r'generate \1 easier, encouraging questions',
        modified
    )
    
    return modified


def get_encouraging_flashcard_prompt(original_prompt: str) -> str:
    """
    Modify flashcard generation prompt to be more encouraging.
    
    Args:
        original_prompt: Original flashcard generation prompt
    
    Returns:
        str: Modified prompt for encouraging flashcards
    """
    modifications = [
        "\n\nIMPORTANT: Create encouraging and confidence-building flashcards.",
        "Focus on basic, foundational concepts.",
        "Use simple, clear language.",
        "Add a brief explanation that boosts understanding.",
        "Avoid complex or niche topics for now."
    ]
    
    return original_prompt + "\n\n" + "\n".join(modifications)