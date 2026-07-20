"""Quiz and content generation for PDF notes."""
import logging
import json
import re
from typing import Dict, Any, List, Optional
from src.llm_client import LLMClient
from src.config import GROQ_API_KEY, LLM_MODEL_QUIZ

logger = logging.getLogger(__name__)

class QuizGenerator:
    """Generate quizzes, summaries, flashcards from PDF content."""
    
    def __init__(self):
        self.llm = LLMClient(GROQ_API_KEY, LLM_MODEL_QUIZ)
    
    def summarize_pdf(self, context: str) -> str:
        """Generate a brief summary of the entire PDF."""
        prompt = f"""
        Based on the following content, provide a brief summary in 5-8 sentences.
        Start with: "This PDF describes..."
        Be concise and cover the main topics.
        
        Content:
        {context[:6000]}
        
        Summary:
        """
        result = self.llm.generate(prompt, max_tokens=200)
        return result if result else "Could not generate summary."
    
    def summarize_topic(self, context: str, topic: str) -> str:
        """Generate a summary of a specific topic from the PDF."""
        prompt = f"""
        Based on the following content, summarize what it says about "{topic}".
        Be concise (5-8 sentences).
        If the topic is not clearly covered, say "I couldn't find much about '{topic}' in this PDF."
        
        Content:
        {context[:6000]}
        
        Summary about "{topic}":
        """
        result = self.llm.generate(prompt, max_tokens=200)
        return result if result else f"Could not find information about '{topic}'."
    
    def generate_quiz(self, context: str, num_questions: int = 5) -> List[Dict]:
        """Generate multiple choice questions from context."""
        prompt = f"""
        Based on the following content, generate {num_questions} multiple choice questions.
        
        IMPORTANT: Return ONLY valid JSON. No markdown, no extra text.
        
        Format:
        {{
            "questions": [
                {{
                    "question": "Question text?",
                    "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
                    "correct_answer": "A",
                    "explanation": "Brief explanation"
                }}
            ]
        }}
        
        Content:
        {context[:5000]}
        """
        
        try:
            result = self.llm.generate(prompt, max_tokens=1200)
            
            if not result:
                logger.error("LLM returned None for quiz generation")
                return []
            
            # Clean the response
            result = result.strip()
            
            # Remove markdown code blocks if present
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0].strip()
            elif '```' in result:
                result = result.split('```')[1].split('```')[0].strip()
            
            # Try to find JSON in the response
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                result = json_match.group(0)
            
            data = json.loads(result)
            questions = data.get('questions', [])
            
            if not questions:
                logger.warning("No questions found in JSON response")
                return []
            
            # Validate each question has required fields
            valid_questions = []
            for q in questions:
                if all(k in q for k in ['question', 'options', 'correct_answer']):
                    valid_questions.append(q)
                else:
                    logger.warning(f"Skipping invalid question: {q}")
            
            logger.info(f"Generated {len(valid_questions)} valid questions")
            return valid_questions
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.error(f"Response was: {result[:500] if result else 'None'}")
            return []
        except Exception as e:
            logger.error(f"Quiz generation error: {e}", exc_info=True)
            return []
    
    def generate_flashcards(self, context: str, num_cards: int = 5) -> List[Dict]:
        """Generate flashcards from context."""
        prompt = f"""
        Based on the following content, generate {num_cards} flashcards.
        Each flashcard should have a term/concept and its definition.
        
        IMPORTANT: Return ONLY valid JSON. No markdown, no extra text.
        
        Format:
        {{
            "flashcards": [
                {{"term": "Concept name", "definition": "Brief explanation"}}
            ]
        }}
        
        Content:
        {context[:5000]}
        """
        
        try:
            result = self.llm.generate(prompt, max_tokens=1000)
            
            if not result:
                logger.error("LLM returned None for flashcards")
                return []
            
            result = result.strip()
            
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0].strip()
            elif '```' in result:
                result = result.split('```')[1].split('```')[0].strip()
            
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                result = json_match.group(0)
            
            data = json.loads(result)
            cards = data.get('flashcards', [])
            
            valid_cards = []
            for c in cards:
                if all(k in c for k in ['term', 'definition']):
                    valid_cards.append(c)
            
            logger.info(f"Generated {len(valid_cards)} valid flashcards")
            return valid_cards
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return []
        except Exception as e:
            logger.error(f"Flashcard generation error: {e}", exc_info=True)
            return []
    
    def generate_true_false(self, context: str, num_questions: int = 3) -> List[Dict]:
        """Generate true/false questions from context."""
        prompt = f"""
        Based on the following content, generate {num_questions} true/false questions.
        
        IMPORTANT: Return ONLY valid JSON. No markdown, no extra text. Keep the response SHORT.
        
        Format:
        {{
            "questions": [
                {{"statement": "Short statement", "answer": true, "explanation": "Short explanation"}}
            ]
        }}
        
        Content:
        {context[:4000]}
        """
        
        try:
            result = self.llm.generate(prompt, max_tokens=1200)
            
            if not result:
                logger.error("LLM returned None for true/false")
                return []
            
            logger.info(f"True/False raw response length: {len(result)}")
            
            # Clean the response
            result = result.strip()
            
            # Remove markdown code blocks if present
            if '```json' in result:
                result = result.split('```json')[1].split('```')[0].strip()
            elif '```' in result:
                result = result.split('```')[1].split('```')[0].strip()
            
            # Try to find JSON in the response
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                result = json_match.group(0)
            
            # Try to fix incomplete JSON by adding missing brackets
            if result.startswith('{') and not result.endswith('}'):
                # Count open and close braces
                open_braces = result.count('{')
                close_braces = result.count('}')
                if open_braces > close_braces:
                    result += '}' * (open_braces - close_braces)
                    logger.info(f"Fixed JSON: added {open_braces - close_braces} closing braces")
            
            data = json.loads(result)
            questions = data.get('questions', [])
            
            if not questions:
                logger.warning("No questions found in JSON response")
                return []
            
            # Validate and clean each question
            valid_questions = []
            for q in questions:
                if 'statement' in q and 'answer' in q:
                    # Ensure answer is boolean
                    if isinstance(q['answer'], bool):
                        valid_questions.append(q)
                    elif isinstance(q['answer'], str):
                        q['answer'] = q['answer'].lower() in ['true', 't', 'yes', '1']
                        valid_questions.append(q)
                    elif isinstance(q['answer'], (int, float)):
                        q['answer'] = bool(q['answer'])
                        valid_questions.append(q)
                    else:
                        logger.warning(f"Skipping question with invalid answer type: {q}")
                else:
                    logger.warning(f"Skipping incomplete question: {q}")
            
            logger.info(f"Generated {len(valid_questions)} valid true/false questions")
            return valid_questions
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.error(f"Response was: {result[:500] if result else 'None'}")
            return []
        except Exception as e:
            logger.error(f"True/False generation error: {e}", exc_info=True)
            return []