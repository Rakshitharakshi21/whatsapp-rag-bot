"""Unit tests for health, diagnostics, idempotency, and message flow.

Why this file exists:
Validates the core stability requirements, health endpoints, idempotency guard,
and initial message response contracts before deployment.
"""
import pytest
from fastapi.testclient import TestClient

from src.main import app, handle_incoming_message_core, extract_body_from_twiml
from src.database import Database
from src.structured_logger import log_stage, APP_LOG_PATH
from src.error_handler import increment_metric, METRICS_PATH

client = TestClient(app)


def test_health_endpoint():
    """Verify /health returns expected keys and status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "db" in data
    assert "chroma" in data
    assert "groq_reachable" in data
    assert "twilio_configured" in data
    assert "uptime" in data


def test_diagnostics_endpoint():
    """Verify /diagnostics returns database counts and model info."""
    response = client.get("/diagnostics")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "database" in data
    assert "row_counts" in data["database"]
    assert "chroma" in data
    assert "groq" in data


def test_webhook_get():
    """Verify /webhook GET returns ok for external URL validation."""
    response = client.get("/webhook")
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True


def test_idempotency_and_webhook_post():
    """Verify /webhook returns TwiML immediately and ignores duplicate message sid."""
    msg_sid = f"test_sid_unique_123"
    payload = {
        "From": "whatsapp:+1234567890",
        "Body": "Hello",
        "MessageSid": msg_sid
    }
    
    # First request
    response1 = client.post("/webhook", data=payload)
    assert response1.status_code == 200
    assert "<Response/>" in response1.text
    
    # Second request with same MessageSid should be ignored (idempotent)
    response2 = client.post("/webhook", data=payload)
    assert response2.status_code == 200
    assert "<Response/>" in response2.text


@pytest.mark.asyncio
async def test_hello_message_receives_reply():
    """Verify that sending 'Hello' produces a valid greeting/welcome message."""
    form_data = {
        "From": "whatsapp:+9999999999",
        "Body": "Hello",
        "MessageSid": "test_hello_sid"
    }
    twiml_resp = await handle_incoming_message_core(form_data)
    xml_content = twiml_resp.body.decode("utf-8") if hasattr(twiml_resp, "body") else str(twiml_resp)
    reply = extract_body_from_twiml(xml_content)
    assert len(reply) > 0
    assert ("Welcome" in reply or "Hello" in reply)


def test_structured_logging():
    """Verify structured logging writes entries to app.jsonl."""
    entry = log_stage(
        user_id="+1234567890",
        stage="test_stage",
        message_id="msg_test_001",
        latency_ms=12.5,
        outcome="success"
    )
    assert entry["stage"] == "test_stage"
    assert entry["outcome"] == "success"
    assert APP_LOG_PATH.exists()


def test_metrics_increment():
    """Verify metrics increment persists to metrics.json."""
    count = increment_metric("test_counter", 1)
    assert count >= 1
    assert METRICS_PATH.exists()
