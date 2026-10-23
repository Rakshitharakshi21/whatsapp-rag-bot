"""SQLite database manager for user data, PDF metadata, and quiz results."""
import sqlite3
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
import logging
import uuid

logger = logging.getLogger(__name__)

class Database:
    """Handle all SQLite database operations."""
    
    def __init__(self, db_path: str = "data/bot_data.db"):
        self.db_path = db_path
        Path("data").mkdir(exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize all tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                streak_count INTEGER DEFAULT 0,
                last_active_date DATE,
                active_pdf_id TEXT,
                total_questions_answered INTEGER DEFAULT 0
            )
        """)
        
        # PDF metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pdf_metadata (
                pdf_id TEXT PRIMARY KEY,
                user_id TEXT,
                filename TEXT,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                chunk_count INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Quiz results table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quiz_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                pdf_id TEXT,
                topic TEXT,
                question TEXT,
                correct BOOLEAN,
                question_type TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (pdf_id) REFERENCES pdf_metadata(pdf_id)
            )
        """)
        
        # Exam Schedules table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exam_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                pdf_id TEXT,
                exam_date DATE,
                exam_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_reminder_sent DATE,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (pdf_id) REFERENCES pdf_metadata(pdf_id)
            )
        """)
        
        # Processed messages table for idempotency
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_sid TEXT PRIMARY KEY,
                user_id TEXT,
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("Database initialized")
    
    # ========== USER METHODS ==========
    
    def get_or_create_user(self, user_id: str) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            conn.close()
            return {
                "user_id": row[0],
                "first_seen": row[1],
                "streak_count": row[2],
                "last_active_date": row[3],
                "active_pdf_id": row[4],
                "total_questions_answered": row[5]
            }
        else:
            cursor.execute(
                "INSERT INTO users (user_id, last_active_date) VALUES (?, ?)",
                (user_id, date.today().isoformat())
            )
            conn.commit()
            conn.close()
            logger.info(f"New user created: {user_id}")
            return {
                "user_id": user_id,
                "first_seen": datetime.now().isoformat(),
                "streak_count": 0,
                "last_active_date": date.today().isoformat(),
                "active_pdf_id": None,
                "total_questions_answered": 0
            }
    
    def update_streak(self, user_id: str) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT streak_count, last_active_date FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return 0
        current_streak = row[0]
        last_active = row[1]
        today = date.today().isoformat()
        if last_active == today:
            conn.close()
            return current_streak
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        if last_active == yesterday:
            new_streak = current_streak + 1
        else:
            new_streak = 1
        cursor.execute(
            "UPDATE users SET streak_count = ?, last_active_date = ? WHERE user_id = ?",
            (new_streak, today, user_id)
        )
        conn.commit()
        conn.close()
        logger.info(f"User {user_id} streak: {new_streak}")
        return new_streak
    
    def get_streak(self, user_id: str) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT streak_count FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0
    
    def increment_question_count(self, user_id: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET total_questions_answered = total_questions_answered + 1 WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        conn.close()
    
    def get_total_questions(self, user_id: str) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT total_questions_answered FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0
    
    def user_exists(self, user_id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    
    # ========== PDF METADATA METHODS ==========
    
    def add_pdf(self, user_id: str, filename: str, chunk_count: int) -> str:
        """Add PDF metadata and set as active PDF."""
        pdf_id = str(uuid.uuid4())[:8]
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO pdf_metadata (pdf_id, user_id, filename, chunk_count) VALUES (?, ?, ?, ?)",
            (pdf_id, user_id, filename, chunk_count)
        )
        # Set as active PDF - THIS IS THE KEY LINE
        cursor.execute(
            "UPDATE users SET active_pdf_id = ? WHERE user_id = ?",
            (pdf_id, user_id)
        )
        conn.commit()
        conn.close()
        logger.info(f"Added PDF {filename} for user {user_id} with id {pdf_id} (active)")
        return pdf_id
    
    def get_user_pdfs(self, user_id: str) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT pdf_id, filename, upload_date, chunk_count FROM pdf_metadata WHERE user_id = ? ORDER BY upload_date DESC",
            (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {"pdf_id": row[0], "filename": row[1], "upload_date": row[2], "chunk_count": row[3]}
            for row in rows
        ]
    
    def get_active_pdf_id(self, user_id: str) -> Optional[str]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT active_pdf_id FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    
    def set_active_pdf(self, user_id: str, pdf_id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT pdf_id FROM pdf_metadata WHERE pdf_id = ? AND user_id = ?", (pdf_id, user_id))
        if not cursor.fetchone():
            conn.close()
            return False
        cursor.execute("UPDATE users SET active_pdf_id = ? WHERE user_id = ?", (pdf_id, user_id))
        conn.commit()
        conn.close()
        return True
    
    def has_pdf(self, user_id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pdf_metadata WHERE user_id = ?", (user_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    
    # ========== QUIZ RESULTS METHODS ==========
    
    def add_quiz_result(self, user_id: str, pdf_id: str, topic: str, question: str, correct: bool, question_type: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO quiz_results (user_id, pdf_id, topic, question, correct, question_type)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, pdf_id, topic, question, correct, question_type)
        )
        conn.commit()
        conn.close()
        self.increment_question_count(user_id)
    
    def get_quiz_results(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """SELECT topic, correct, question_type, timestamp
               FROM quiz_results WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?""",
            (user_id, limit)
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {"topic": row[0], "correct": row[1], "question_type": row[2], "timestamp": row[3]}
            for row in rows
        ]
    
    def get_topic_accuracy(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """SELECT topic, COUNT(*) as total, SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as correct
               FROM quiz_results WHERE user_id = ? GROUP BY topic""",
            (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        result = {}
        for row in rows:
            topic = row[0]
            total = row[1]
            correct = row[2]
            result[topic] = {
                "total": total,
                "correct": correct,
                "accuracy": (correct / total * 100) if total > 0 else 0
            }
        return result
    
    def get_weak_topics(self, user_id: str, min_questions: int = 3) -> List[Dict[str, Any]]:
        topic_data = self.get_topic_accuracy(user_id)
        weak_topics = []
        for topic, data in topic_data.items():
            if data['total'] >= min_questions and data['accuracy'] < 60:
                weak_topics.append({
                    "topic": topic,
                    "accuracy": data['accuracy'],
                    "total": data['total'],
                    "correct": data['correct']
                })
        return sorted(weak_topics, key=lambda x: x['accuracy'])
    
    # ========== EXAM SCHEDULE METHODS ==========
    
    def add_exam_schedule(self, user_id: str, pdf_id: str, exam_date: str, exam_name: str = "Exam") -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO exam_schedules (user_id, pdf_id, exam_date, exam_name)
               VALUES (?, ?, ?, ?)""",
            (user_id, pdf_id, exam_date, exam_name)
        )
        conn.commit()
        exam_id = cursor.lastrowid
        conn.close()
        logger.info(f"Exam schedule added for user {user_id}: {exam_name} on {exam_date}")
        return exam_id
    
    def get_active_exam_schedules(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, pdf_id, exam_date, exam_name, created_at, last_reminder_sent
            FROM exam_schedules
            WHERE is_active = 1 AND exam_date >= date('now')
            ORDER BY exam_date ASC
        """)
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": row[0],
                "user_id": row[1],
                "pdf_id": row[2],
                "exam_date": row[3],
                "exam_name": row[4],
                "created_at": row[5],
                "last_reminder_sent": row[6]
            }
            for row in rows
        ]
    
    def get_user_exam_schedule(self, user_id: str) -> Optional[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, pdf_id, exam_date, exam_name, last_reminder_sent
            FROM exam_schedules
            WHERE user_id = ? AND is_active = 1 AND exam_date >= date('now')
            ORDER BY exam_date ASC LIMIT 1
        """, (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "id": row[0],
                "pdf_id": row[1],
                "exam_date": row[2],
                "exam_name": row[3],
                "last_reminder_sent": row[4]
            }
        return None
    
    def update_last_reminder_sent(self, schedule_id: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE exam_schedules SET last_reminder_sent = date('now') WHERE id = ?",
            (schedule_id,)
        )
        conn.commit()
        conn.close()
    
    def deactivate_exam_schedule(self, schedule_id: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE exam_schedules SET is_active = 0 WHERE id = ?",
            (schedule_id,)
        )
        conn.commit()
        conn.close()
    
    def delete_exam_schedule(self, user_id: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM exam_schedules WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        conn.close()

    def is_message_processed(self, message_sid: str) -> bool:
        """Check if message_sid has already been processed (idempotency)."""
        if not message_sid:
            return False
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM processed_messages WHERE message_sid = ?", (message_sid,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    def mark_message_processed(self, message_sid: str, user_id: str) -> bool:
        """Record message_sid in processed_messages table."""
        if not message_sid:
            return True
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO processed_messages (message_sid, user_id) VALUES (?, ?)",
                (message_sid, user_id)
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False