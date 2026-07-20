"""FastAPI wrapper for the RAG pipeline with WhatsApp support and menu system."""
import logging
import os
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta
import re
import random
import time

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from twilio.twiml.messaging_response import MessagingResponse
import requests

from src.config import (
    GROQ_API_KEY, CHROMA_DB_DIR, LLM_MODEL, LLM_MODEL_QUIZ,
    TOP_K_RETRIEVAL, LLM_MAX_TOKENS, WHATSAPP_MAX_MESSAGE_LENGTH,
    MAX_PDF_SIZE_MB
)
from src.rag_pipeline import RAGPipeline
from src.quiz_generator import QuizGenerator
from src.session_manager import SessionManager, SessionState
from src.welcome import WELCOME_MESSAGE, is_new_user, get_welcome_message
from src.exam_scheduler import ExamScheduler
from src.mood_detector import detect_mood, get_encouragement_message, get_easier_quiz_prompt

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="WhatsApp RAG Bot API",
    description="API for PDF upload and question answering using RAG",
    version="2.0.0"
)

# Initialize components
pipeline = RAGPipeline(str(CHROMA_DB_DIR), GROQ_API_KEY)
quiz_gen = QuizGenerator()
session_mgr = SessionManager()
exam_scheduler = ExamScheduler()

# Pydantic models for request/response
class AskRequest(BaseModel):
    query: str
    user_id: str

class AskResponse(BaseModel):
    success: bool
    answer: str
    sources: Optional[list] = []
    num_sources: Optional[int] = 0

class UploadResponse(BaseModel):
    success: bool
    message: str
    chunks_added: Optional[int] = None
    total_chars: Optional[int] = None
    filename: Optional[str] = None

# ========== GLOBAL COMMANDS ==========
GLOBAL_COMMANDS = {"menu", "help", "quit", "stop", "cancel", "weak topics", "weak", "switch pdf", "pdfs", "explain", "cheat sheet", "cheatsheet"}

# ========== SMART NLP COMMANDS ==========
MENU_OPTIONS = {
    "1": "summarize_full",
    "summarize": "summarize_full",
    "summary": "summarize_full",
    "summarize pdf": "summarize_full",
    "summarize the pdf": "summarize_full",
    "summarize all": "summarize_full",
    "summarize everything": "summarize_full",
    "give me a summary": "summarize_full",
    "tell me what it's about": "summarize_full",
    "what is this about": "summarize_full",
    "overview": "summarize_full",
    "give overview": "summarize_full",
    "2": "summarize_topic",
    "topic": "summarize_topic",
    "summarize about": "summarize_topic",
    "summarize topic": "summarize_topic",
    "summarize specific": "summarize_topic",
    "summarize specific topic": "summarize_topic",
    "tell me about": "summarize_topic",
    "what about": "summarize_topic",
    "explain": "summarize_topic",
    "explain about": "summarize_topic",
    "can you explain": "summarize_topic",
    "3": "quiz",
    "quiz": "quiz",
    "quiz me": "quiz",
    "generate quiz": "quiz",
    "test me": "quiz",
    "test": "quiz",
    "mcq": "quiz",
    "multiple choice": "quiz",
    "questions": "quiz",
    "give me a quiz": "quiz",
    "take quiz": "quiz",
    "i want to take quiz": "quiz",
    "practice": "quiz",
    "practice questions": "quiz",
    "4": "flashcards",
    "flashcard": "flashcards",
    "flashcards": "flashcards",
    "generate flashcards": "flashcards",
    "cards": "flashcards",
    "study cards": "flashcards",
    "flash cards": "flashcards",
    "give me flashcards": "flashcards",
    "make flashcards": "flashcards",
    "5": "true_false",
    "tf": "true_false",
    "truefalse": "true_false",
    "true or false": "true_false",
    "true/false": "true_false",
    "generate tf": "true_false",
    "true false questions": "true_false",
    "tf questions": "true_false",
    "give true false": "true_false",
}

NATURAL_COMMANDS = {
    "upload another pdf": "upload_pdf",
    "upload another": "upload_pdf",
    "new pdf": "upload_pdf",
    "send another pdf": "upload_pdf",
    "upload": "upload_pdf",
    "another pdf": "upload_pdf",
    "yes upload": "upload_pdf",
    "yes send": "upload_pdf",
}

AFFIRMATIVE = {"yes", "y", "sure", "ok", "okay", "ya", "yeah", "yea", "of course", "definitely", "go ahead"}
NEGATIVE = {"no", "n", "not", "nope", "nah", "no thanks", "not now", "later", "maybe later"}


def resolve_menu_choice(text: str) -> str:
    text = text.lower().strip()
    if "summarize about" in text or "summarize specific" in text or "tell me about" in text:
        return "summarize_topic"
    if "quiz on" in text or "quiz about" in text:
        return "quiz"
    if text in MENU_OPTIONS:
        return MENU_OPTIONS[text]
    for key, action in MENU_OPTIONS.items():
        if key in text:
            return action
    return None


def extract_topic_from_message(text: str) -> Optional[str]:
    text = text.lower().strip()
    patterns = [
        r"summarize about\s+(.+)",
        r"summarize specific\s+(.+)",
        r"tell me about\s+(.+)",
        r"what about\s+(.+)",
        r"explain about\s+(.+)",
        r"explain\s+(.+)",
        r"quiz on\s+(.+)",
        r"quiz about\s+(.+)",
        r"test on\s+(.+)",
        r"test about\s+(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            topic = match.group(1).strip()
            topic = re.sub(r'^the\s+', '', topic)
            topic = re.sub(r'^pdf\s+', '', topic)
            return topic
    return None


def truncate_message(text: str, max_length: int = WHATSAPP_MAX_MESSAGE_LENGTH) -> str:
    if not text:
        return text
    if len(text) <= max_length:
        return text
    truncated = text[:max_length]
    last_space = truncated.rfind(' ')
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated + "... (continued)"


def get_menu_text() -> str:
    return """📋 *What would you like to do?*

1️⃣ Summarize entire PDF
2️⃣ Summarize specific topic
3️⃣ Generate quiz
4️⃣ Generate flashcards
5️⃣ True/False questions

Reply with a number, or type 'menu' anytime to see this again.

💡 *You can also say:*
"summarize about [topic]"
"quiz me on [topic]"
"tell me about [topic]"
"explain [topic]"
"upload another PDF"
"flashcards please"
"true false questions"
"practice questions"
"test me"
"give me a summary"
"overview"
"cheat sheet"
"exam on Aug 5"

Just type naturally! 🚀"""


def format_question(q: dict, index: int, total: int) -> str:
    options_text = "\n".join(q.get('options', []))
    return f"""📝 *Quiz Question {index + 1}/{total}*
{q.get('question')}

{options_text}

Reply with A, B, C, or D"""


def format_flashcard(card: dict, index: int, total: int) -> str:
    return f"""📝 *Flashcard {index + 1}/{total}*
📌 *{card.get('term')}*
{card.get('definition')}

Type 'next' for next card, or 'quit' to stop."""


def format_tf_question(q: dict, index: int, total: int) -> str:
    statement = q.get('statement', '')
    return f"""📝 *True/False Question {index + 1}/{total}*
{statement}

Reply with 'True' or 'False'"""


# ========== GENERATE EXPLANATION FUNCTION ==========
def generate_explanation(question: dict, correct_answer: str, topic: str, options: list) -> str:
    """Generate explanation for why other options were wrong."""
    try:
        options_text = "\n".join(options)
        prompt = f"""
        You are a helpful tutor explaining a quiz question to a student who got it wrong.

        Question: {question.get('question')}
        
        Options:
        {options_text}
        
        Correct Answer: {correct_answer}

        Task: 
        1. Briefly explain (2-3 sentences) WHY the correct answer is right
        2. Briefly explain (2-3 sentences each) WHY each INCORRECT option is wrong

        Format your response for WhatsApp with:
        - *Asterisks* for emphasis
        - Use '-' for bullet points
        - Keep it concise (total under 500 words)
        - Use encouraging language

        Response:
        """
        result = pipeline.llm.generate(prompt, max_tokens=600)
        return result if result else "❌ Could not generate explanation right now. Please try again."
    except Exception as e:
        logger.error(f"Explanation generation error: {e}")
        return "❌ Sorry, couldn't generate explanation. Please try again."


# ========== CHEAT SHEET FUNCTIONS ==========
async def _generate_cheat_sheet_from_context(context: str) -> str:
    """Generate final cheat sheet from context."""
    prompt = f"""
    Create a compact cheat sheet from the following content.
    
    Include:
    1. Key terms with one-line definitions (*term*: definition)
    2. Important dates/formulas/numbers if present
    3. 3-5 critical must-know points
    
    Format for WhatsApp:
    - Use *asterisks* for emphasis
    - Use '-' for bullet points
    - Keep it concise and easy to scan
    
    Content:
    {context}
    
    Cheat Sheet:
    """
    result = pipeline.llm.generate(prompt, max_tokens=800)
    return result if result else "Could not generate cheat sheet."


async def handle_cheat_sheet(user_id: str, msg):
    """Generate a cheat sheet for the user's active PDF with timing logs."""
    t0 = time.time()
    try:
        logger.info(f"[{time.time()-t0:.1f}s] Starting cheat sheet for user {user_id}")
        
        active_pdf_id = session_mgr.get_active_pdf_id(user_id)
        logger.info(f"[{time.time()-t0:.1f}s] got active_pdf_id: {active_pdf_id}")
        
        if not active_pdf_id:
            msg.body("❌ No active PDF found. Please upload a PDF first.")
            return

        logger.info(f"[{time.time()-t0:.1f}s] Embedding query...")
        query_embedding = pipeline.embedder.embed_text("content")
        logger.info(f"[{time.time()-t0:.1f}s] Embedding complete")

        logger.info(f"[{time.time()-t0:.1f}s] Querying ChromaDB...")
        chunks = pipeline.vector_store.query(query_embedding, user_id, top_k=15)
        logger.info(f"[{time.time()-t0:.1f}s] Got {len(chunks) if chunks else 0} chunks")

        if not chunks:
            msg.body("❌ Could not find any content for the cheat sheet.")
            return

        all_text = [c['text'] for c in chunks]
        context = "\n\n---\n\n".join(all_text[:6])
        context = context[:4000]
        
        logger.info(f"[{time.time()-t0:.1f}s] Calling Groq for cheat sheet...")
        cheat_sheet = await _generate_cheat_sheet_from_context(context)
        logger.info(f"[{time.time()-t0:.1f}s] Got cheat sheet from Groq")

        msg.body(f"📄 *Cheat Sheet*\n\n{cheat_sheet}")
        logger.info(f"[{time.time()-t0:.1f}s] Cheat sheet complete!")
        
    except Exception as e:
        logger.error(f"Cheat sheet error at {time.time()-t0:.1f}s: {e}", exc_info=True)
        msg.body("❌ Error generating cheat sheet. Please try again.")


@app.on_event("startup")
async def startup_event():
    try:
        url = "https://api.groq.com/openai/v1/models"
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            active_models = [m['id'] for m in response.json().get('data', [])]
            logger.info(f"Active Groq models count: {len(active_models)}")
            if LLM_MODEL not in active_models:
                logger.warning(f"⚠️ Main model '{LLM_MODEL}' not found!")
            else:
                logger.info(f"✅ Main model '{LLM_MODEL}' is available")
            if LLM_MODEL_QUIZ not in active_models:
                logger.warning(f"⚠️ Quiz model '{LLM_MODEL_QUIZ}' not found!")
            else:
                logger.info(f"✅ Quiz model '{LLM_MODEL_QUIZ}' is available")
    except Exception as e:
        logger.warning(f"Model check failed: {e}")


@app.get("/")
async def root():
    return {
        "message": "WhatsApp RAG Bot API",
        "status": "running",
        "endpoints": {
            "/upload": "POST - Upload a PDF file",
            "/ask": "POST - Ask a question about your notes",
            "/webhook": "POST - WhatsApp webhook",
            "/health": "GET - Check API health"
        }
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "chunks_stored": pipeline.vector_store.collection.count()}


@app.post("/upload", response_model=UploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    user_id: str = Form(...)
):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    content = await file.read()
    result = pipeline.process_pdf(content, user_id, file.filename)
    if result['success']:
        return UploadResponse(
            success=True,
            message="PDF processed successfully",
            chunks_added=result['chunks_added'],
            total_chars=result['total_chars'],
            filename=result['filename']
        )
    else:
        raise HTTPException(status_code=400, detail=result['error'])


@app.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    result = pipeline.ask_question(request.query, request.user_id)
    return AskResponse(
        success=result['success'],
        answer=result['answer'],
        sources=result.get('sources', []),
        num_sources=result.get('num_sources', 0)
    )


@app.get("/webhook")
async def webhook_get():
    return {"message": "Webhook is active. Use POST for messages."}


@app.post("/webhook")
async def webhook(request: Request):
    """Handle incoming WhatsApp messages with all features integrated."""
    try:
        form = await request.form()
        raw_from = form.get('From', '')
        user_id = raw_from.replace('whatsapp:', '').strip()
        incoming_msg = form.get('Body', '').strip()
        media_url = form.get('MediaUrl0', None)
        media_type = form.get('MediaContentType0', None)
        
        resp = MessagingResponse()
        msg = resp.message()
        
        TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
        TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
        
        # ========== FIRST-TIME USER CHECK ==========
        if is_new_user(user_id):
            logger.info(f"New user detected: {user_id}")
            msg.body(WELCOME_MESSAGE)
            return Response(content=str(resp), media_type="application/xml")
        
        logger.info(f"Received message from user: {user_id}")
        logger.info(f"Message content: {incoming_msg[:100] if incoming_msg else '(empty)'}")
        
        # ========== CHEAT SHEET COMMAND DETECTION (EARLY) ==========
        if "cheat" in incoming_msg.lower() or "sheet" in incoming_msg.lower():
            logger.info(f"User {user_id} requested cheat sheet")
            msg.body("📝 Generating cheat sheet... Please wait.")
            await handle_cheat_sheet(user_id, msg)
            return Response(content=str(resp), media_type="application/xml")
        
        # ========== SESSION MANAGEMENT ==========
        session = session_mgr.get_session(user_id)
        if session_mgr.is_session_expired(session):
            logger.info(f"Session expired for user {user_id}, resetting")
            session_mgr.reset_session(user_id)
            session = session_mgr.get_session(user_id)
        session_mgr.update_state(user_id, session.get('state', 'idle'), session.get('context', {}))
        
        # ========== HANDLE PDF UPLOAD ==========
        if media_url and media_type:
            if 'pdf' not in media_type.lower():
                msg.body("❌ Sorry, I only accept PDF files. Please send a PDF document.")
                logger.warning(f"Rejected non-PDF file: {media_type}")
                return Response(content=str(resp), media_type="application/xml")
            
            try:
                logger.info(f"Downloading PDF from: {media_url}")
                response = requests.get(media_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN), timeout=30)
                if response.status_code != 200:
                    msg.body("❌ Failed to download your PDF. Please try again.")
                    logger.error(f"PDF download failed: {response.status_code}")
                    return Response(content=str(resp), media_type="application/xml")
                
                pdf_bytes = response.content
                logger.info(f"PDF downloaded: {len(pdf_bytes)} bytes")
                
                MAX_FILE_SIZE = MAX_PDF_SIZE_MB * 1024 * 1024
                if len(pdf_bytes) > MAX_FILE_SIZE:
                    msg.body(f"❌ File too large. Please send a PDF under {MAX_PDF_SIZE_MB}MB.")
                    logger.warning(f"File too large: {len(pdf_bytes)} bytes")
                    return Response(content=str(resp), media_type="application/xml")
                
                from src.pdf_processor import PDFProcessor
                processor = PDFProcessor()
                extracted_text = processor.extract_text(pdf_bytes, "whatsapp.pdf")
                
                if not extracted_text or len(extracted_text) < 100:
                    msg.body("""❌ I couldn't extract text from this PDF.

📄 This looks like a *scanned or image-based PDF* (no selectable text).

💡 *What you can do:*
• Upload a PDF with selectable text (not scanned)
• Use a PDF with text from Word/Google Docs
• Future version may support OCR

Try again with a text-based PDF! 📚""")
                    logger.warning(f"Scanned PDF detected: {len(extracted_text) if extracted_text else 0} chars")
                    return Response(content=str(resp), media_type="application/xml")
                
                logger.info(f"Text extracted: {len(extracted_text)} characters")
                
                result = pipeline.process_pdf(pdf_bytes, user_id, "whatsapp.pdf")
                
                if result['success']:
                    pdf_id = session_mgr.mark_pdf_uploaded(user_id, "whatsapp.pdf", result['chunks_added'])
                    streak = session_mgr.update_streak(user_id)
                    streak_msg = f"\n\n🔥 {streak}-day study streak!" if streak > 1 else ""
                    
                    exam_reminder = exam_scheduler.get_exam_reminder(user_id)
                    exam_msg = f"\n\n{exam_reminder}" if exam_reminder else ""
                    
                    msg.body(f"✅ PDF processed! Added {result['chunks_added']} chunks.{streak_msg}{exam_msg}\n\n{get_menu_text()}")
                    logger.info(f"PDF processing successful: {result['chunks_added']} chunks")
                else:
                    msg.body(f"❌ Sorry, I couldn't process your PDF: {result['error']}")
                    logger.error(f"PDF processing failed: {result['error']}")
            except Exception as e:
                logger.error(f"PDF processing error: {e}", exc_info=True)
                msg.body("❌ Error processing your PDF. Please try again.")
            
            return Response(content=str(resp), media_type="application/xml")
        
        # ========== NO-PDF GUARD ==========
        if incoming_msg.lower() in ["1", "2", "3", "4", "5", "menu"]:
            if not session_mgr.has_pdf(user_id):
                msg.body("📚 You haven't uploaded any PDF yet!\n\nPlease send me a PDF file first to get started.")
                return Response(content=str(resp), media_type="application/xml")
        
        # ========== CHECK FOR EXAM DATE COMMAND ==========
        if any(word in incoming_msg.lower() for word in ["exam on", "set exam", "exam date", "deadline on"]):
            parsed = exam_scheduler.parse_exam_date_command(incoming_msg)
            if parsed:
                result = exam_scheduler.set_exam_date(user_id, parsed['date'], parsed['name'])
                msg.body(result)
                return Response(content=str(resp), media_type="application/xml")
        
        # ========== MOOD DETECTION ==========
        is_stressed, keyword = detect_mood(incoming_msg)
        if is_stressed:
            session_mgr.set_mood_flag(user_id, True)
            wrong_count = session_mgr._sessions.get(user_id, {}).get('wrong_consecutive', 0)
            encouragement = get_encouragement_message(wrong_count)
            msg.body(f"💙 I noticed you might be feeling stressed. {encouragement}")
            session_mgr.reset_mood(user_id)
            return Response(content=str(resp), media_type="application/xml")
        
        # ========== GLOBAL COMMANDS ==========
        if incoming_msg.lower() in GLOBAL_COMMANDS:
            # Handle "explain" command
            if incoming_msg.lower() == "explain":
                if session_mgr.is_in_explain_mode(user_id):
                    q_data = session_mgr.get_explain_question(user_id)
                    if q_data:
                        explanation = generate_explanation(
                            q_data.get('question', {}),
                            q_data.get('correct_answer', ''),
                            q_data.get('topic', 'General'),
                            q_data.get('options', [])
                        )
                        msg.body(f"📖 *Explanation:*\n\n{explanation}")
                        session_mgr.clear_explain_mode(user_id)
                    else:
                        msg.body("❌ No question to explain. Try answering a question first!")
                else:
                    msg.body("❌ No question to explain. Answer a quiz question first, then type 'explain'.")
                return Response(content=str(resp), media_type="application/xml")
            
            # Handle "weak topics" command
            if incoming_msg.lower() in ["weak topics", "weak"]:
                weak_topics = session_mgr.get_weak_topics(user_id)
                if not weak_topics:
                    msg.body("📊 You haven't answered enough questions yet!\n\nKeep using quizzes and I'll analyze your weak topics after 15 questions.")
                else:
                    result = "📊 *Your Weak Topics:*\n\n"
                    for topic in weak_topics:
                        result += f"• *{topic['topic']}* - {topic['accuracy']:.1f}% correct ({topic['correct']}/{topic['total']})\n"
                    result += "\n💡 Want a focused quiz on any of these? Type 'quiz' and mention the topic!"
                    msg.body(result)
                return Response(content=str(resp), media_type="application/xml")
            
            # Handle "switch pdf" command
            if incoming_msg.lower() in ["switch pdf", "pdfs"]:
                pdfs = session_mgr.get_user_pdfs(user_id)
                if not pdfs:
                    msg.body("📚 You haven't uploaded any PDFs yet.")
                else:
                    result = "📄 *Your PDFs:*\n\n"
                    for i, pdf in enumerate(pdfs, 1):
                        active = " ✅ (active)" if pdf['pdf_id'] == session_mgr.get_active_pdf_id(user_id) else ""
                        result += f"{i}. {pdf['filename']} ({pdf['chunk_count']} chunks){active}\n"
                    result += "\nReply with the number to switch."
                    session_mgr.update_state(user_id, "awaiting_pdf_switch", {"pdfs": pdfs})
                    msg.body(result)
                return Response(content=str(resp), media_type="application/xml")
            
            # Handle quit/stop/cancel
            if incoming_msg.lower() in ["quit", "stop", "cancel"]:
                session_mgr.reset_session(user_id)
                msg.body("✅ Stopped current activity.\n\n" + get_menu_text())
            else:
                session_mgr.update_state(user_id, "awaiting_menu_choice", {})
                msg.body(get_menu_text())
            return Response(content=str(resp), media_type="application/xml")
        
        # ========== NATURAL LANGUAGE "UPLOAD ANOTHER PDF" ==========
        if incoming_msg.lower() in NATURAL_COMMANDS:
            msg.body("📄 Please send me the new PDF file.")
            session_mgr.update_state(user_id, "awaiting_pdf_upload", {})
            return Response(content=str(resp), media_type="application/xml")
        
        # Get current state
        current_state = session.get('state', 'idle')
        context = session.get('context', {})
        
        # ========== HANDLE PDF SWITCH ==========
        if current_state == "awaiting_pdf_switch":
            try:
                choice = int(incoming_msg.strip())
                pdfs = context.get('pdfs', [])
                if 1 <= choice <= len(pdfs):
                    pdf_id = pdfs[choice-1]['pdf_id']
                    session_mgr.set_active_pdf(user_id, pdf_id)
                    msg.body(f"✅ Switched to: {pdfs[choice-1]['filename']}\n\n{get_menu_text()}")
                    session_mgr.update_state(user_id, "awaiting_menu_choice", {})
                else:
                    msg.body(f"❌ Invalid choice. Please reply with a number 1-{len(pdfs)}.")
            except ValueError:
                msg.body("❌ Please reply with a number.")
            return Response(content=str(resp), media_type="application/xml")
        
        # ========== HANDLE "GENERATE MORE" ==========
        if current_state == "awaiting_more":
            if incoming_msg.lower() in AFFIRMATIVE:
                context = session.get('context', {})
                used_chunk_ids = context.get('used_chunk_ids', [])
                topic = context.get('topic', "Entire PDF content")
                
                query_embedding = pipeline.embedder.embed_text(topic if topic != "Entire PDF content" else "content")
                chunks = pipeline.vector_store.query(query_embedding, user_id, top_k=30)
                available_chunks = [c for c in chunks if c.get('metadata', {}).get('chunk_id') not in used_chunk_ids]
                
                if not available_chunks:
                    msg.body("📚 No new content available for more questions!\n\n" + get_menu_text())
                    session_mgr.update_state(user_id, "awaiting_menu_choice", {})
                else:
                    context_text = "\n\n---\n\n".join([c['text'] for c in available_chunks[:15]])
                    
                    if session_mgr.get_mood_flag(user_id):
                        context_text = get_easier_quiz_prompt(context_text)
                        session_mgr.reset_mood(user_id)
                    
                    questions = quiz_gen.generate_quiz(context_text)
                    
                    if questions and len(questions) > 0:
                        new_used = used_chunk_ids + [c.get('metadata', {}).get('chunk_id') for c in available_chunks[:len(questions)]]
                        session_mgr.update_state(user_id, "in_quiz", {
                            "questions": questions,
                            "current_index": 0,
                            "score": 0,
                            "total": len(questions),
                            "used_chunk_ids": new_used,
                            "topic": topic
                        })
                        q = questions[0]
                        msg.body(format_question(q, 0, len(questions)))
                    else:
                        msg.body("❌ Could not generate more questions. Please try again.")
                        session_mgr.update_state(user_id, "awaiting_menu_choice", {})
            elif incoming_msg.lower() in NEGATIVE:
                msg.body("✅ Returning to menu.\n\n" + get_menu_text())
                session_mgr.update_state(user_id, "awaiting_menu_choice", {})
            else:
                msg.body("Please reply with 'yes' for more questions, or 'no' to return to menu.")
            return Response(content=str(resp), media_type="application/xml")
        
        # ========== STATE: IDLE / AWAITING MENU ==========
        if current_state == "idle" or current_state == "awaiting_menu_choice":
            if not session_mgr.has_pdf(user_id):
                msg.body("📚 You haven't uploaded any notes yet. Send me a PDF file first!")
            else:
                exam_reminder = exam_scheduler.get_exam_reminder(user_id)
                exam_prefix = f"{exam_reminder}\n\n" if exam_reminder else ""
                
                action = resolve_menu_choice(incoming_msg)
                extracted_topic = extract_topic_from_message(incoming_msg)
                
                if action == "summarize_full":
                    logger.info(f"User {user_id} chose: Summarize Entire PDF")
                    query_embedding = pipeline.embedder.embed_text("Entire PDF content")
                    chunks = pipeline.vector_store.query(query_embedding, user_id, top_k=20)
                    context_text = "\n\n".join([chunk['text'] for chunk in chunks])
                    if not chunks:
                        msg.body(f"{exam_prefix}❌ I couldn't find any notes. Please upload a PDF first.")
                    else:
                        msg.body(f"{exam_prefix}📝 Generating summary... Please wait.")
                        summary = quiz_gen.summarize_pdf(context_text)
                        msg.body(f"{exam_prefix}📝 *Summary:*\n\n{truncate_message(summary)}")
                        logger.info(f"Summary sent to user {user_id}")
                
                elif action == "summarize_topic":
                    logger.info(f"User {user_id} chose: Summarize Specific Topic")
                    if extracted_topic:
                        msg.body(f"{exam_prefix}📝 Summarizing '{extracted_topic}'... Please wait.")
                        query_embedding = pipeline.embedder.embed_text(extracted_topic)
                        chunks = pipeline.vector_store.query(query_embedding, user_id, top_k=6)
                        context_text = "\n\n".join([chunk['text'] for chunk in chunks])
                        if not chunks:
                            msg.body(f"{exam_prefix}❌ I couldn't find information about '{extracted_topic}' in your notes.")
                        else:
                            summary = quiz_gen.summarize_topic(context_text, extracted_topic)
                            msg.body(f"{exam_prefix}📝 *Summary about '{extracted_topic}':*\n\n{truncate_message(summary)}")
                        session_mgr.update_state(user_id, "awaiting_menu_choice", {})
                    else:
                        session_mgr.update_state(user_id, "awaiting_topic_summary", {})
                        msg.body(f"{exam_prefix}📝 Which topic would you like me to summarize?")
                
                elif action == "quiz":
                    logger.info(f"User {user_id} chose: Generate Quiz")
                    if extracted_topic:
                        session_mgr.update_state(user_id, "awaiting_quiz_topic", {})
                        await handle_quiz_with_topic(user_id, msg, extracted_topic, exam_prefix)
                    else:
                        session_mgr.update_state(user_id, "awaiting_quiz_topic", {})
                        msg.body(f"{exam_prefix}📝 Quiz on the whole PDF, or a specific topic?\n(Reply with a topic, or just say 'whole PDF')")
                
                elif action == "flashcards":
                    logger.info(f"User {user_id} chose: Generate Flashcards")
                    await handle_flashcards(user_id, msg, exam_prefix)
                
                elif action == "true_false":
                    logger.info(f"User {user_id} chose: True/False Questions")
                    await handle_true_false(user_id, msg, exam_prefix)
                
                elif incoming_msg.lower() in ["upload another pdf", "new pdf", "another pdf"]:
                    msg.body(f"{exam_prefix}📄 Please send me the new PDF file.")
                    session_mgr.update_state(user_id, "awaiting_pdf_upload", {})
                
                else:
                    if len(incoming_msg.split()) > 3:
                        logger.info(f"User {user_id} asked a question: {incoming_msg}")
                        msg.body(f"{exam_prefix}🤔 Let me think...")
                        result = pipeline.ask_question(incoming_msg, user_id)
                        if result['success']:
                            msg.body(truncate_message(result['answer']))
                        else:
                            msg.body(f"{exam_prefix}❌ {result['answer']}\n\n{get_menu_text()}")
                    else:
                        msg.body(f"{exam_prefix}❌ I didn't get that.\n\n{get_menu_text()}")
            
            return Response(content=str(resp), media_type="application/xml")
        
        # ========== STATE: AWAITING TOPIC SUMMARY ==========
        elif current_state == "awaiting_topic_summary":
            topic = incoming_msg.strip()
            exam_reminder = exam_scheduler.get_exam_reminder(user_id)
            exam_prefix = f"{exam_reminder}\n\n" if exam_reminder else ""
            
            if not topic:
                msg.body(f"{exam_prefix}Please tell me which topic you want to summarize.")
            else:
                msg.body(f"{exam_prefix}📝 Summarizing '{topic}'... Please wait.")
                logger.info(f"User {user_id} asked to summarize topic: {topic}")
                
                query_embedding = pipeline.embedder.embed_text(topic)
                chunks = pipeline.vector_store.query(query_embedding, user_id, top_k=6)
                context_text = "\n\n".join([chunk['text'] for chunk in chunks])
                
                if not chunks:
                    msg.body(f"{exam_prefix}❌ I couldn't find information about '{topic}' in your notes.")
                else:
                    summary = quiz_gen.summarize_topic(context_text, topic)
                    msg.body(f"{exam_prefix}📝 *Summary about '{topic}':*\n\n{truncate_message(summary)}")
                
                session_mgr.update_state(user_id, "awaiting_menu_choice", {})
            
            return Response(content=str(resp), media_type="application/xml")
        
        # ========== STATE: AWAITING QUIZ TOPIC ==========
        elif current_state == "awaiting_quiz_topic":
            topic_input = incoming_msg.strip()
            exam_reminder = exam_scheduler.get_exam_reminder(user_id)
            exam_prefix = f"{exam_reminder}\n\n" if exam_reminder else ""
            
            if not topic_input:
                msg.body(f"{exam_prefix}Please tell me a topic or say 'whole PDF'.")
            else:
                await handle_quiz_with_topic(user_id, msg, topic_input, exam_prefix)
            
            return Response(content=str(resp), media_type="application/xml")
        
        # ========== STATE: IN QUIZ ==========
        elif current_state == "in_quiz":
            answer = incoming_msg.strip().upper()
            questions = context.get('questions', [])
            current_index = context.get('current_index', 0)
            score = context.get('score', 0)
            total = context.get('total', 0)
            
            if current_index >= len(questions):
                msg.body(f"🏁 Quiz complete! Score: {score}/{total}\n\n{get_menu_text()}")
                session_mgr.update_state(user_id, "awaiting_menu_choice", {})
            else:
                q = questions[current_index]
                correct_answer = q.get('correct_answer', '').upper()
                topic = q.get('topic', 'General')
                
                if answer == correct_answer:
                    score += 1
                    feedback = "✅ Correct!"
                    session_mgr.reset_wrong(user_id)
                else:
                    feedback = f"❌ Wrong. Correct answer: {correct_answer}"
                    wrong_count = session_mgr.increment_wrong(user_id)
                    
                    session_mgr.set_explain_mode(user_id, {
                        "question": q,
                        "correct_answer": correct_answer,
                        "topic": topic,
                        "options": q.get('options', [])
                    })
                    feedback += "\n\n💡 Type 'explain' to learn why the other options were wrong!"
                    
                    if wrong_count >= 3:
                        feedback += "\n\n💙 Don't worry! Let's try something different. Want to switch to flashcards? Type 'flashcards' anytime."
                        session_mgr.reset_mood(user_id)
                
                if q.get('explanation'):
                    feedback += f"\n💡 {q.get('explanation')}"
                
                session_mgr.add_quiz_result(
                    user_id=user_id,
                    pdf_id=session_mgr.get_active_pdf_id(user_id) or "unknown",
                    topic=topic,
                    question=q.get('question', ''),
                    correct=(answer == correct_answer),
                    question_type="mcq"
                )
                
                current_index += 1
                
                if current_index >= len(questions):
                    total_questions = session_mgr.get_total_questions(user_id)
                    if total_questions % 15 == 0:
                        weak_topics = session_mgr.get_weak_topics(user_id)
                        if weak_topics:
                            feedback += f"\n\n💡 *Study Insight:* You've struggled with '{weak_topics[0]['topic']}' — type 'weak topics' to see all!"
                    
                    msg.body(f"{feedback}\n\n🏁 Quiz complete! Score: {score}/{total}\n\nWant more? Reply 'yes' for 5 more, or 'menu' for other options.")
                    session_mgr.update_state(user_id, "awaiting_more", {
                        "used_chunk_ids": context.get('used_chunk_ids', []),
                        "topic": context.get('topic', "Entire PDF content")
                    })
                else:
                    session_mgr.update_state(user_id, "in_quiz", {
                        "questions": questions,
                        "current_index": current_index,
                        "score": score,
                        "total": total,
                        "used_chunk_ids": context.get('used_chunk_ids', []),
                        "topic": context.get('topic', "Entire PDF content")
                    })
                    q = questions[current_index]
                    msg.body(f"{feedback}\n\n{format_question(q, current_index, len(questions))}")
            
            return Response(content=str(resp), media_type="application/xml")
        
        # ========== STATE: IN FLASHCARD ==========
        elif current_state == "in_flashcard":
            user_input = incoming_msg.lower().strip()
            flashcards = context.get('flashcards', [])
            current_index = context.get('current_index', 0)
            total = context.get('total', 0)
            
            if user_input in ["quit", "stop", "cancel"]:
                session_mgr.reset_session(user_id)
                msg.body(f"✅ Stopped flashcards.\n\n{get_menu_text()}")
            elif user_input == "next" or user_input == "n":
                current_index += 1
                if current_index >= len(flashcards):
                    msg.body(f"🏁 All flashcards done!\n\n{get_menu_text()}")
                    session_mgr.update_state(user_id, "awaiting_menu_choice", {})
                else:
                    session_mgr.update_state(user_id, "in_flashcard", {
                        "flashcards": flashcards,
                        "current_index": current_index,
                        "total": total
                    })
                    card = flashcards[current_index]
                    msg.body(format_flashcard(card, current_index, len(flashcards)))
            else:
                msg.body("Type 'next' for next card, or 'quit' to stop.")
            
            return Response(content=str(resp), media_type="application/xml")
        
        # ========== STATE: IN TF QUIZ ==========
        elif current_state == "in_tf_quiz":
            answer = incoming_msg.strip().lower()
            questions = context.get('questions', [])
            current_index = context.get('current_index', 0)
            score = context.get('score', 0)
            total = context.get('total', 0)
            
            if current_index >= len(questions):
                msg.body(f"🏁 True/False complete! Score: {score}/{total}\n\n{get_menu_text()}")
                session_mgr.update_state(user_id, "awaiting_menu_choice", {})
            else:
                q = questions[current_index]
                correct_answer = q.get('answer', False)
                
                if isinstance(correct_answer, str):
                    correct_answer = correct_answer.lower() in ['true', 't', 'yes', '1']
                
                if answer in ["true", "false", "t", "f", "yes", "no", "y", "n"]:
                    user_answer = answer in ["true", "t", "yes", "y"]
                    
                    if user_answer == correct_answer:
                        score += 1
                        feedback = "✅ Correct!"
                        session_mgr.reset_wrong(user_id)
                    else:
                        feedback = f"❌ Wrong. Correct answer: {'True' if correct_answer else 'False'}"
                        wrong_count = session_mgr.increment_wrong(user_id)
                        if wrong_count >= 3:
                            feedback += "\n\n💙 Don't worry! Want to switch to flashcards? Type 'flashcards' anytime."
                            session_mgr.reset_mood(user_id)
                    
                    if q.get('explanation'):
                        feedback += f"\n💡 {q.get('explanation')}"
                    
                    session_mgr.add_quiz_result(
                        user_id=user_id,
                        pdf_id=session_mgr.get_active_pdf_id(user_id) or "unknown",
                        topic=q.get('topic', 'General'),
                        question=q.get('statement', ''),
                        correct=(user_answer == correct_answer),
                        question_type="true_false"
                    )
                    
                    current_index += 1
                    
                    if current_index >= len(questions):
                        total_questions = session_mgr.get_total_questions(user_id)
                        if total_questions % 15 == 0:
                            weak_topics = session_mgr.get_weak_topics(user_id)
                            if weak_topics:
                                feedback += f"\n\n💡 *Study Insight:* You've struggled with '{weak_topics[0]['topic']}' — type 'weak topics' to see all!"
                        
                        msg.body(f"{feedback}\n\n🏁 True/False complete! Score: {score}/{total}\n\nWant more? Reply 'yes' for 5 more, or 'menu' for other options.")
                        session_mgr.update_state(user_id, "awaiting_more", {
                            "used_chunk_ids": context.get('used_chunk_ids', []),
                            "topic": context.get('topic', "Entire PDF content")
                        })
                    else:
                        session_mgr.update_state(user_id, "in_tf_quiz", {
                            "questions": questions,
                            "current_index": current_index,
                            "score": score,
                            "total": total,
                            "used_chunk_ids": context.get('used_chunk_ids', []),
                            "topic": context.get('topic', "Entire PDF content")
                        })
                        q = questions[current_index]
                        msg.body(f"{feedback}\n\n{format_tf_question(q, current_index, len(questions))}")
                else:
                    msg.body("Please reply with 'True' or 'False'.")
            
            return Response(content=str(resp), media_type="application/xml")
        
        else:
            session_mgr.update_state(user_id, "awaiting_menu_choice", {})
            msg.body(get_menu_text())
            return Response(content=str(resp), media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        resp = MessagingResponse()
        msg = resp.message()
        msg.body("❌ Sorry, something went wrong. Please try again.")
        return Response(content=str(resp), media_type="application/xml")


# ========== HELPER FUNCTIONS ==========

async def handle_flashcards(user_id: str, msg, exam_prefix: str = ""):
    """Generate and send first flashcard."""
    try:
        query_embedding = pipeline.embedder.embed_text("Entire PDF content")
        chunks = pipeline.vector_store.query(query_embedding, user_id, top_k=20)
        context_text = "\n\n".join([chunk['text'] for chunk in chunks])
        
        if not chunks:
            msg.body(f"{exam_prefix}❌ I couldn't find any notes. Please upload a PDF first.")
            return
        
        flashcards = quiz_gen.generate_flashcards(context_text)
        if flashcards and len(flashcards) > 0:
            session_mgr.update_state(user_id, "in_flashcard", {
                "flashcards": flashcards,
                "current_index": 0,
                "total": len(flashcards)
            })
            card = flashcards[0]
            msg.body(f"{exam_prefix}{format_flashcard(card, 0, len(flashcards))}")
        else:
            msg.body(f"{exam_prefix}❌ Could not generate flashcards. Please try again.")
            session_mgr.update_state(user_id, "awaiting_menu_choice", {})
    except Exception as e:
        logger.error(f"Flashcard error: {e}", exc_info=True)
        msg.body(f"{exam_prefix}❌ Error generating flashcards. Please try again.")


async def handle_true_false(user_id: str, msg, exam_prefix: str = ""):
    """Generate and send first true/false question."""
    try:
        query_embedding = pipeline.embedder.embed_text("Entire PDF content")
        chunks = pipeline.vector_store.query(query_embedding, user_id, top_k=20)
        context_text = "\n\n".join([chunk['text'] for chunk in chunks])
        
        if not chunks:
            msg.body(f"{exam_prefix}❌ I couldn't find any notes. Please upload a PDF first.")
            return
        
        tf_questions = quiz_gen.generate_true_false(context_text)
        if tf_questions and len(tf_questions) > 0:
            session_mgr.update_state(user_id, "in_tf_quiz", {
                "questions": tf_questions,
                "current_index": 0,
                "score": 0,
                "total": len(tf_questions),
                "used_chunk_ids": [],
                "topic": "Entire PDF content"
            })
            q = tf_questions[0]
            msg.body(f"{exam_prefix}{format_tf_question(q, 0, len(tf_questions))}")
        else:
            msg.body(f"{exam_prefix}❌ Could not generate True/False questions. Please try again.")
            session_mgr.update_state(user_id, "awaiting_menu_choice", {})
    except Exception as e:
        logger.error(f"True/False error: {e}", exc_info=True)
        msg.body(f"{exam_prefix}❌ Error generating True/False questions. Please try again.")


async def handle_quiz_with_topic(user_id: str, msg, topic_input: str, exam_prefix: str = ""):
    """Handle quiz generation with topic input."""
    msg.body(f"{exam_prefix}📝 Generating quiz... Please wait.")
    logger.info(f"User {user_id} asked for quiz on: {topic_input}")
    
    try:
        if topic_input.lower() == "whole pdf":
            query_embedding = pipeline.embedder.embed_text("content")
            chunks = pipeline.vector_store.query(query_embedding, user_id, top_k=30)
            topic = "Entire PDF content"
        else:
            query_embedding = pipeline.embedder.embed_text(topic_input)
            chunks = pipeline.vector_store.query(query_embedding, user_id, top_k=15)
            topic = topic_input
        
        if not chunks or len(chunks) == 0:
            msg.body(f"{exam_prefix}❌ I couldn't find any content to generate a quiz. Please upload a PDF first.")
            session_mgr.update_state(user_id, "awaiting_menu_choice", {})
            return
        
        context_text = "\n\n---\n\n".join([chunk['text'] for chunk in chunks if chunk.get('text')])
        
        if len(context_text) < 100:
            msg.body(f"{exam_prefix}❌ Not enough content found to generate a quiz. Please upload a larger PDF.")
            session_mgr.update_state(user_id, "awaiting_menu_choice", {})
            return
        
        if session_mgr.get_mood_flag(user_id):
            context_text = get_easier_quiz_prompt(context_text)
            session_mgr.reset_mood(user_id)
        
        questions = quiz_gen.generate_quiz(context_text)
        
        if questions and len(questions) > 0:
            used_chunk_ids = [c.get('metadata', {}).get('chunk_id') for c in chunks[:len(questions)]]
            session_mgr.update_state(user_id, "in_quiz", {
                "questions": questions,
                "current_index": 0,
                "score": 0,
                "total": len(questions),
                "used_chunk_ids": used_chunk_ids,
                "topic": topic
            })
            q = questions[0]
            msg.body(f"{exam_prefix}{format_question(q, 0, len(questions))}")
        else:
            msg.body(f"{exam_prefix}❌ Could not generate quiz. Please try again.")
            session_mgr.update_state(user_id, "awaiting_menu_choice", {})
    except Exception as e:
        logger.error(f"Quiz generation error: {e}", exc_info=True)
        msg.body(f"{exam_prefix}❌ Error generating quiz. Please try again.")
        session_mgr.update_state(user_id, "awaiting_menu_choice", {})