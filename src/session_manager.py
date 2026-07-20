"""Session management for WhatsApp users with database integration."""
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from enum import Enum

from src.database import Database

# Initialize database
db = Database()

class SessionState:
    """Possible states for a user session."""
    IDLE = "idle"
    AWAITING_MENU_CHOICE = "awaiting_menu_choice"
    AWAITING_TOPIC_SUMMARY = "awaiting_topic_summary"
    AWAITING_QUIZ_TOPIC = "awaiting_quiz_topic"
    IN_QUIZ = "in_quiz"
    IN_FLASHCARD = "in_flashcard"
    IN_TF_QUIZ = "in_tf_quiz"


class SessionManager:
    """
    Manage user conversation states with database persistence.
    
    Hybrid approach:
    - Database: User streaks, PDF metadata, quiz results (long-lived)
    - In-memory: Active quiz traversal state (current_index, current batch)
    """
    
    def __init__(self):
        # In-memory session cache for active state
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self.timeout_minutes = 30
    
    def get_session(self, user_id: str) -> Dict[str, Any]:
        """Get user's current session from memory or create new."""
        # Check if user exists in database (first-time check)
        if not db.user_exists(user_id):
            # New user - create in database
            db.get_or_create_user(user_id)
            self._sessions[user_id] = {
                "state": SessionState.IDLE,
                "context": {},
                "last_active": datetime.now().isoformat(),
                "awaiting_explain_more": False,
                "explain_question_data": None,
                "mood_flag": False,
                "wrong_consecutive": 0
            }
            return self._sessions[user_id]
        
        # Existing user - get from memory or create
        if user_id not in self._sessions:
            self._sessions[user_id] = {
                "state": SessionState.IDLE,
                "context": {},
                "last_active": datetime.now().isoformat(),
                "awaiting_explain_more": False,
                "explain_question_data": None,
                "mood_flag": False,
                "wrong_consecutive": 0
            }
        
        # Check if expired
        if self.is_session_expired(self._sessions[user_id]):
            self.reset_session(user_id)
        
        return self._sessions[user_id]
    
    def update_state(self, user_id: str, state: str, context: Dict = None):
        """Update user's state in memory."""
        if user_id not in self._sessions:
            self._sessions[user_id] = {
                "state": SessionState.IDLE,
                "context": {},
                "last_active": datetime.now().isoformat(),
                "awaiting_explain_more": False,
                "explain_question_data": None,
                "mood_flag": False,
                "wrong_consecutive": 0
            }
        
        self._sessions[user_id]["state"] = state
        self._sessions[user_id]["context"] = context or {}
        self._sessions[user_id]["last_active"] = datetime.now().isoformat()
    
    def get_state(self, user_id: str) -> Dict[str, Any]:
        """Get user's current state."""
        session = self.get_session(user_id)
        return {
            "state": session.get("state", SessionState.IDLE),
            "context": session.get("context", {}),
            "awaiting_explain_more": session.get("awaiting_explain_more", False),
            "mood_flag": session.get("mood_flag", False),
            "wrong_consecutive": session.get("wrong_consecutive", 0)
        }
    
    def reset_session(self, user_id: str):
        """Reset session to IDLE but keep data."""
        if user_id in self._sessions:
            self._sessions[user_id] = {
                "state": SessionState.IDLE,
                "context": {},
                "last_active": datetime.now().isoformat(),
                "awaiting_explain_more": False,
                "explain_question_data": None,
                "mood_flag": False,
                "wrong_consecutive": 0
            }
    
    def is_session_expired(self, session: Dict[str, Any]) -> bool:
        """Check if session has expired (30 min timeout)."""
        if not session.get('last_active'):
            return False
        
        last_active = datetime.fromisoformat(session['last_active'])
        return datetime.now() - last_active > timedelta(minutes=self.timeout_minutes)
    
    def clear_session(self, user_id: str):
        """Completely clear session from memory."""
        if user_id in self._sessions:
            del self._sessions[user_id]
    
    def mark_pdf_uploaded(self, user_id: str, filename: str, chunk_count: int):
        """Add PDF metadata to database and mark in session."""
        pdf_id = db.add_pdf(user_id, filename, chunk_count)
        self.update_state(user_id, SessionState.AWAITING_MENU_CHOICE, {})
        return pdf_id
    
    def get_user_pdfs(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all PDFs for user from database."""
        return db.get_user_pdfs(user_id)
    
    def has_pdf(self, user_id: str) -> bool:
        """Check if user has any PDF uploaded."""
        return db.has_pdf(user_id)
    
    def set_active_pdf(self, user_id: str, pdf_id: str) -> bool:
        """Set active PDF for user."""
        return db.set_active_pdf(user_id, pdf_id)
    
    def get_active_pdf_id(self, user_id: str) -> Optional[str]:
        """Get user's active PDF ID."""
        return db.get_active_pdf_id(user_id)
    
    def update_streak(self, user_id: str) -> int:
        """Update user's streak and return current count."""
        return db.update_streak(user_id)
    
    def get_streak(self, user_id: str) -> int:
        """Get user's current streak."""
        return db.get_streak(user_id)
    
    def add_quiz_result(self, user_id: str, pdf_id: str, topic: str, question: str, correct: bool, question_type: str):
        """Add quiz result to database."""
        db.add_quiz_result(user_id, pdf_id, topic, question, correct, question_type)
    
    def get_total_questions(self, user_id: str) -> int:
        """Get total questions answered by user."""
        return db.get_total_questions(user_id)
    
    def get_weak_topics(self, user_id: str, min_questions: int = 3) -> List[Dict[str, Any]]:
        """Get weak topics for user."""
        return db.get_weak_topics(user_id, min_questions)
    
    def get_quiz_results(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent quiz results for user."""
        return db.get_quiz_results(user_id, limit)
    
    # ========== EXPLAIN MODE METHODS ==========
    
    def set_explain_mode(self, user_id: str, question_data: Dict[str, Any]):
        """Set user in explain mode with the question data."""
        if user_id not in self._sessions:
            self._sessions[user_id] = {
                "state": SessionState.IDLE,
                "context": {},
                "last_active": datetime.now().isoformat(),
                "awaiting_explain_more": False,
                "explain_question_data": None,
                "mood_flag": False,
                "wrong_consecutive": 0
            }
        self._sessions[user_id]['awaiting_explain_more'] = True
        self._sessions[user_id]['explain_question_data'] = question_data
        self._sessions[user_id]['last_active'] = datetime.now().isoformat()

    def clear_explain_mode(self, user_id: str):
        """Clear explain mode."""
        if user_id in self._sessions:
            self._sessions[user_id]['awaiting_explain_more'] = False
            self._sessions[user_id]['explain_question_data'] = None

    def is_in_explain_mode(self, user_id: str) -> bool:
        """Check if user is in explain mode."""
        if user_id not in self._sessions:
            return False
        return self._sessions[user_id].get('awaiting_explain_more', False)

    def get_explain_question(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get the question data for explanation."""
        if user_id not in self._sessions:
            return None
        return self._sessions[user_id].get('explain_question_data')
    
    # ========== MOOD METHODS ==========
    
    def set_mood_flag(self, user_id: str, flag: bool):
        """Set mood flag for user."""
        if user_id not in self._sessions:
            self.get_session(user_id)
        self._sessions[user_id]['mood_flag'] = flag
    
    def get_mood_flag(self, user_id: str) -> bool:
        """Get mood flag for user."""
        if user_id not in self._sessions:
            return False
        return self._sessions[user_id].get('mood_flag', False)
    
    def reset_mood(self, user_id: str):
        """Reset mood flag and wrong consecutive count."""
        if user_id in self._sessions:
            self._sessions[user_id]['mood_flag'] = False
            self._sessions[user_id]['wrong_consecutive'] = 0
    
    def increment_wrong(self, user_id: str) -> int:
        """Increment wrong consecutive count and return new value."""
        if user_id not in self._sessions:
            self.get_session(user_id)
        self._sessions[user_id]['wrong_consecutive'] = self._sessions[user_id].get('wrong_consecutive', 0) + 1
        return self._sessions[user_id]['wrong_consecutive']
    
    def reset_wrong(self, user_id: str):
        """Reset wrong consecutive count."""
        if user_id in self._sessions:
            self._sessions[user_id]['wrong_consecutive'] = 0