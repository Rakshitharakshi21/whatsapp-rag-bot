"""Exam countdown scheduler with reactive reminders."""
import logging
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.database import Database

logger = logging.getLogger(__name__)

class ExamScheduler:
    """Manage exam countdown and reactive reminders."""
    
    def __init__(self):
        self.db = Database()
        self.scheduler = BackgroundScheduler()
        self._init_scheduler()
    
    def _init_scheduler(self):
        """Initialize APScheduler with a daily job."""
        self.scheduler.add_job(
            func=self._daily_cleanup,
            trigger=IntervalTrigger(hours=24),
            id='exam_cleanup',
            replace_existing=True
        )
        self.scheduler.start()
        logger.info("Exam scheduler started")
    
    def _daily_cleanup(self):
        """Deactivate expired exam schedules and update reminders."""
        try:
            schedules = self.db.get_active_exam_schedules()
            today = date.today()
            
            for schedule in schedules:
                exam_date = datetime.strptime(schedule['exam_date'], '%Y-%m-%d').date()
                
                # If exam date passed, deactivate
                if exam_date < today:
                    self.db.deactivate_exam_schedule(schedule['id'])
                    logger.info(f"Deactivated expired exam schedule: {schedule['id']}")
        except Exception as e:
            logger.error(f"Daily cleanup error: {e}")
    
    def get_exam_reminder(self, user_id: str) -> Optional[str]:
        """
        Get exam reminder message for a user (called on incoming message).
        
        Returns:
            str: Exam reminder message or None if no exam scheduled
        """
        schedule = self.db.get_user_exam_schedule(user_id)
        if not schedule:
            return None
        
        try:
            exam_date = datetime.strptime(schedule['exam_date'], '%Y-%m-%d').date()
            today = date.today()
            days_remaining = (exam_date - today).days
            
            # If exam is today or passed, handle accordingly
            if days_remaining < 0:
                self.db.deactivate_exam_schedule(schedule['id'])
                return None
            
            # Get user's weak topics if available
            weak_topics = self.db.get_weak_topics(user_id)
            weak_topic_text = ""
            if weak_topics:
                weak_topic_text = f"\n\n💡 Focus on: {weak_topics[0]['topic']} (you struggled with this)"
            
            # Different messages based on days remaining
            if days_remaining == 0:
                return f"📅 *TODAY IS YOUR EXAM!* 🎯\n{schedule['exam_name']} is today!{weak_topic_text}\n\nYou've got this! 💪"
            
            elif days_remaining == 1:
                return f"📅 *TOMORROW IS YOUR EXAM!* 🔥\n{schedule['exam_name']} is in 1 day!{weak_topic_text}\n\nFocus on final review! 📚"
            
            elif days_remaining <= 5:
                return f"📅 *{days_remaining} days until {schedule['exam_name']}!* ⏰\n\nWant to take a quick quiz or review flashcards?"
            
            elif days_remaining <= 10:
                return f"📅 *{days_remaining} days until {schedule['exam_name']}* 📚\n\nDon't forget to study! Need a summary or flashcards?"
            
            else:
                return f"📅 *{days_remaining} days until {schedule['exam_name']}* 📅\n\nKeep studying daily! 📖"
            
        except Exception as e:
            logger.error(f"Error generating exam reminder: {e}")
            return None
    
    def set_exam_date(self, user_id: str, exam_date: str, exam_name: str = "Exam") -> str:
        """
        Set an exam date for a user.
        
        Args:
            user_id: User's WhatsApp number
            exam_date: Date string in YYYY-MM-DD format
            exam_name: Name of the exam
        
        Returns:
            str: Confirmation message
        """
        # Validate date
        try:
            parsed_date = datetime.strptime(exam_date, '%Y-%m-%d').date()
        except ValueError:
            return "❌ Invalid date format. Please use YYYY-MM-DD (e.g., 2026-08-05)"
        
        # Check if date is in the past
        if parsed_date < date.today():
            return "❌ That date has already passed. Please set a future date."
        
        # Get active PDF for user
        active_pdf_id = self.db.get_active_pdf_id(user_id)
        if not active_pdf_id:
            return "❌ Please upload a PDF first before setting an exam date."
        
        # Remove any existing exam schedule
        self.db.delete_exam_schedule(user_id)
        
        # Add new schedule
        exam_id = self.db.add_exam_schedule(user_id, active_pdf_id, exam_date, exam_name)
        
        days_remaining = (parsed_date - date.today()).days
        return f"✅ Exam scheduled!\n📅 *{exam_name}* on {exam_date}\n⏰ {days_remaining} days remaining\n\nI'll remind you every time you message me! 📚"
    
    def parse_exam_date_command(self, text: str) -> Optional[Dict[str, str]]:
        """
        Parse natural language exam date commands.
        
        Examples:
            "exam on Aug 5 2026"
            "set exam date 2026-08-05"
            "exam on 2026-08-05"
            "exam on 5th August"
            "set exam Aug 5"
        """
        import re
        from dateutil import parser
        
        text = text.lower().strip()
        
        # Check if it's an exam date command
        if not any(word in text for word in ["exam", "exams", "test", "deadline"]):
            return None
        
        if not any(word in text for word in ["on", "set", "date"]):
            return None
        
        # Try to extract date
        try:
            # Remove common prefixes
            cleaned = text
            for prefix in ["set exam date ", "exam on ", "exam date ", "deadline on ", "deadline "]:
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):].strip()
            
            # Try to parse date
            # Handle common date formats
            date_patterns = [
                r'(\d{4}-\d{2}-\d{2})',  # 2026-08-05
                r'(\d{2}/\d{2}/\d{4})',   # 08/05/2026
                r'(\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4})',  # 5 Aug 2026
                r'(\d{1,2}(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)(?:\s+\d{4})?)',  # 5th August 2026
                r'((jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})',  # Aug 5, 2026
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, cleaned, re.IGNORECASE)
                if match:
                    date_str = match.group(1)
                    parsed = parser.parse(date_str, fuzzy=True)
                    return {
                        "date": parsed.strftime('%Y-%m-%d'),
                        "name": "Exam"
                    }
            
            # Try fallback with dateutil parser
            parsed = parser.parse(cleaned, fuzzy=True)
            if parsed:
                return {
                    "date": parsed.strftime('%Y-%m-%d'),
                    "name": "Exam"
                }
                
        except Exception as e:
            logger.info(f"Date parsing failed: {e}")
            return None
        
        return None