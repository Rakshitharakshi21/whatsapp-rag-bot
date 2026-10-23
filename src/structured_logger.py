"""Structured JSON logging for WhatsApp RAG Bot.

Why this file exists:
Provides structured JSONL logging to logs/app.jsonl for observability across request lifecycle
stages (received, processing, response_sent, error) as required by Section 3.B.
"""
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)
APP_LOG_PATH = LOGS_DIR / "app.jsonl"


def log_stage(
    user_id: str,
    stage: str,
    message_id: Optional[str] = None,
    latency_ms: Optional[float] = None,
    outcome: str = "success",
    extra: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Record a single structured log line for a request lifecycle stage.

    Why: Ensures every incoming WhatsApp interaction can be traced with duration,
    success/failure outcome, and user context in logs/app.jsonl.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "message_id": message_id or "unknown",
        "stage": stage,
        "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
        "outcome": outcome,
    }
    if extra:
        entry["extra"] = extra

    try:
        with open(APP_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.warning(f"Could not write to {APP_LOG_PATH}: {e}")

    return entry
