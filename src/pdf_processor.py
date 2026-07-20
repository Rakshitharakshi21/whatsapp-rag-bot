import io
import logging
from typing import Optional
import pdfplumber
import PyPDF2

logger = logging.getLogger(__name__)

class PDFProcessor:
    @staticmethod
    def extract_text(pdf_bytes: bytes, filename: str = "unknown.pdf") -> Optional[str]:
        text = None
        
        try:
            with io.BytesIO(pdf_bytes) as pdf_buffer:
                with pdfplumber.open(pdf_buffer) as pdf:
                    pages_text = []
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            pages_text.append(page_text)
                    text = "\n\n".join(pages_text)
                    if text:
                        logger.info(f"pdfplumber extracted {len(text)} chars from {filename}")
        except Exception as e:
            logger.warning(f"pdfplumber failed: {e}")
        
        if not text or len(text) < 50:
            try:
                with io.BytesIO(pdf_bytes) as pdf_buffer:
                    pdf_reader = PyPDF2.PdfReader(pdf_buffer)
                    pages_text = []
                    for page in pdf_reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            pages_text.append(page_text)
                    text = "\n\n".join(pages_text)
                    if text:
                        logger.info(f"PyPDF2 extracted {len(text)} chars from {filename}")
            except Exception as e:
                logger.warning(f"PyPDF2 fallback failed: {e}")
        
        if text:
            text = text.strip()
            if len(text) < 50:
                logger.warning(f"Extracted text too short ({len(text)} chars)")
                return None
        
        return text