"""Groq API client for LLM interactions."""
import json
import logging
import time
from typing import Optional, Dict, Any
from groq import Groq

logger = logging.getLogger(__name__)

class LLMClient:
    """
    Wrapper for Groq API with retry logic and error handling.
    
    Why Groq: It's incredibly fast and has a generous free tier
    (30 requests/minute on openai/gpt-oss-120b).
    """
    
    def __init__(self, api_key: str, model: str = "openai/gpt-oss-120b"):
        self.api_key = api_key
        self.model = model
        self.client = Groq(api_key=api_key)
        self.max_retries = 3
        self.retry_delay = 1
    
    def generate(self, prompt: str, temperature: float = 0.3, max_tokens: int = 400) -> Optional[str]:
        """
        Generate text from the LLM with retry logic and rate limit handling.
        
        Returns:
            str: Generated text, or None if all retries fail
        """
        logger.info(f"LLM generate called with model: {self.model}")
        logger.info(f"Prompt length: {len(prompt)} characters")
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"LLM attempt {attempt + 1}/{self.max_retries}")
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                result = response.choices[0].message.content
                logger.info(f"LLM response received, length: {len(result)}")
                return result
                
            except Exception as e:
                error_str = str(e).lower()
                logger.error(f"LLM attempt {attempt + 1} failed")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error message: {str(e)}")
                
                # Check if it's a rate limit (429)
                if "429" in error_str or "rate limit" in error_str or "too many requests" in error_str:
                    retry_after = 60  # Default wait
                    try:
                        if hasattr(e, 'response') and hasattr(e.response, 'headers'):
                            retry_after = int(e.response.headers.get('retry-after', 60))
                            logger.info(f"Rate limit headers: {dict(e.response.headers)}")
                    except:
                        pass
                    
                    logger.warning(f"Rate limit hit. Waiting {retry_after}s before retry")
                    
                    if attempt < self.max_retries - 1:
                        time.sleep(retry_after)
                        continue
                    else:
                        logger.error("Rate limit: All retries exhausted")
                        return None
                
                # If it's a model not found error
                if "model" in error_str and "not found" in error_str:
                    logger.error(f"Model '{self.model}' not found. Please check the model name.")
                    return None
                
                # Other errors - retry with backoff
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.info(f"Retrying in {wait_time}s")
                    time.sleep(wait_time)
                else:
                    logger.error(f"All {self.max_retries} attempts failed. Returning None.")
                    return None
        
        return None
    
    def test_connection(self) -> bool:
        """Test if the Groq API is working."""
        try:
            result = self.generate("Say 'OK' if you can read this.", max_tokens=10)
            return result is not None and "OK" in result
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def get_active_models(self) -> list:
        """Get list of active models from Groq API."""
        try:
            import requests
            url = "https://api.groq.com/openai/v1/models"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return [m['id'] for m in data.get('data', [])]
            else:
                logger.error(f"Failed to get models: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error getting models: {e}")
            return []