"""Spelling correction and fuzzy matching for natural language commands."""
import re
from difflib import get_close_matches
from typing import Optional, List, Tuple

# Command keywords with common spelling variations
COMMAND_KEYWORDS = {
    "summarize": ["summarize", "summary", "overview", "summrize", "sumarize", "summery", "sumary", "synopsis", "sum"],
    "quiz": ["quiz", "test", "quizz", "quize", "mcq", "multiple", "question", "questions"],
    "flashcard": ["flashcard", "flash", "card", "flshcard", "flascard", "fleshcard", "cards"],
    "true_false": ["truefalse", "true/false", "tf", "true false", "bool", "boolean"],
    "topic": ["topic", "specific", "about", "explain", "tell", "what"],
    "pdf": ["pdf", "file", "document", "upload", "another"],
}

COMMAND_ACTIONS = {
    "summarize": "summarize",
    "summary": "summarize",
    "overview": "summarize",
    "quiz": "quiz",
    "test": "quiz",
    "flashcard": "flashcards",
    "flash": "flashcards",
    "truefalse": "true_false",
    "tf": "true_false",
}

# Common topic words that shouldn't be corrected
STOP_WORDS = {"the", "a", "an", "this", "that", "these", "those", "on", "about", "for", "with", "from", "by", "to", "of"}


def correct_spelling(word: str, word_list: List[str], cutoff: float = 0.7) -> Optional[str]:
    """
    Correct spelling of a word using fuzzy matching.
    
    Args:
        word: The word to correct
        word_list: List of valid words to match against
        cutoff: Similarity threshold (0.0 to 1.0)
    
    Returns:
        Corrected word or None if no match found
    """
    if not word or len(word) < 2:
        return word
    
    matches = get_close_matches(word.lower(), word_list, n=1, cutoff=cutoff)
    return matches[0] if matches else None


def normalize_command(text: str) -> Tuple[str, Optional[str]]:
    """
    Normalize natural language command with spelling correction.
    
    Returns:
        Tuple of (normalized_command, extracted_topic)
    """
    text = text.lower().strip()
    
    # Check for topic extraction first
    topic = None
    
    # Try to extract topic with patterns
    topic_patterns = [
        r"(?:summarize|summary|overview|explain|tell me about|what about|quiz about|quiz on)\s+(?:the\s+)?(.+)$",
        r"(?:about|on)\s+(?:the\s+)?(.+)$",
    ]
    
    for pattern in topic_patterns:
        match = re.search(pattern, text)
        if match:
            topic_candidate = match.group(1).strip()
            # Remove stop words from topic
            topic_words = [w for w in topic_candidate.split() if w not in STOP_WORDS]
            if topic_words:
                topic = " ".join(topic_words)
                # Remove the topic from text for command detection
                text = text.replace(match.group(0), '').strip()
    
    # Get all words from the cleaned text
    words = re.findall(r'\b\w+\b', text)
    
    # Check each word against command keywords
    for word in words:
        # Check if word or its corrected version matches any command
        for keyword, variants in COMMAND_KEYWORDS.items():
            if word in variants:
                return COMMAND_ACTIONS.get(keyword, keyword), topic
            
            # Try spelling correction
            corrected = correct_spelling(word, variants, cutoff=0.7)
            if corrected:
                return COMMAND_ACTIONS.get(keyword, keyword), topic
    
    # Check if text contains command-like phrases
    for keyword, variants in COMMAND_KEYWORDS.items():
        for variant in variants:
            if variant in text:
                return COMMAND_ACTIONS.get(keyword, keyword), topic
    
    # Check if it's a question (contains ? or starts with what/why/how)
    if '?' in text or text.startswith(('what', 'why', 'how', 'when', 'where', 'who', 'is', 'are', 'can', 'does', 'do')):
        return "question", topic
    
    return "unknown", topic


def correct_topic_spelling(topic: str) -> str:
    """
    Correct spelling of a topic name using common technical terms.
    
    Args:
        topic: The topic to correct
    
    Returns:
        Corrected topic name
    """
    # Common technical terms that users might misspell
    TECHNICAL_TERMS = {
        "JDBC": ["jdbc", "jdcb", "jd bc", "jdb c", "jdbc", "j d b c"],
        "SQL": ["sql", "sql", "sgl", "squel", "sequel"],
        "Database": ["database", "data base", "datbase", "data base", "data base"],
        "Python": ["python", "pyton", "py thon", "pythn"],
        "Java": ["java", "jave", "jv", "jva"],
        "JavaScript": ["javascript", "javscript", "js", "java script"],
        "React": ["react", "reactjs", "react js", "reac"],
        "Node": ["node", "nodejs", "node js", "nod"],
        "MongoDB": ["mongodb", "mongo", "mongo db", "mongodb"],
        "MySQL": ["mysql", "my sql", "my sql", "mysq"],
        "PostgreSQL": ["postgresql", "postgres", "postgre", "postgresql"],
        "API": ["api", "a p i", "api"],
        "REST": ["rest", "restful", "rest api"],
        "Docker": ["docker", "dockr", "do cker", "doker"],
        "AWS": ["aws", "amazon", "a w s", "amzon"],
        "Azure": ["azure", "azur", "azre"],
        "Git": ["git", "gti", "g it", "gti"],
        "GitHub": ["github", "git hub", "github"],
        "AI": ["ai", "artificial intelligence", "a i"],
        "ML": ["ml", "machine learning", "m l"],
        "LLM": ["llm", "large language model", "l l m"],
        "RAG": ["rag", "retrieval augmented", "r a g"],
        "DSA": ["dsa", "data structures", "d s a"],
        "OS": ["os", "operating system", "o s"],
        "DBMS": ["dbms", "database management", "d b m s"],
        "CN": ["cn", "computer networks", "c n"],
        "OOPS": ["oops", "object oriented", "o o p s"],
    }
    
    topic_lower = topic.lower().strip()
    
    # Check if topic matches any technical term
    for term, variants in TECHNICAL_TERMS.items():
        if topic_lower in variants:
            return term
        # Check with fuzzy matching
        corrected = correct_spelling(topic_lower, variants, cutoff=0.7)
        if corrected:
            return term
    
    # If no match, return original with first letter capitalized
    return topic.title()