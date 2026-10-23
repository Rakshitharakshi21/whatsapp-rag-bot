# Feature Note: F1 - Health & Self-Diagnostic Endpoints

## 1. Problem
When debugging WhatsApp webhook failures or deploying to cloud hosts like Render, there was no visibility into whether the web application was healthy, whether ChromaDB was properly mounted, whether Groq API keys were valid, or if Twilio credentials were configured. Furthermore, developers could not test message handling without sending actual WhatsApp messages through Twilio.

## 2. Design
Implemented three endpoints in `src/main.py`:
- `GET /health`: Fast probe returning overall system state, SQLite connectivity, ChromaDB connection & chunk count, Groq key presence, Twilio configuration, and server uptime.
- `GET /diagnostics`: Detailed breakdown querying Groq for sample accessible models, ChromaDB collections count, and SQLite row counts across tables (`users`, `pdf_metadata`, `quiz_results`, `exam_schedules`, `processed_messages`).
- `GET /webhook`: Verification endpoint returning `{"ok": true}` for external reachability testing.
- `POST /webhook/test`: Local and test simulator (gated by `DEV_MODE=1`) allowing test payloads to be posted directly and returning the bot's text reply without requiring live WhatsApp network traffic.

## 3. Tradeoffs
- **Groq API check in diagnostics:** Makes a lightweight call to Groq's model listing API to verify live credentials, which adds ~200ms latency to `/diagnostics`. The fast `/health` check uses key presence to keep the probe sub-millisecond for container health checks.
- **DEV_MODE gate for test webhook:** `POST /webhook/test` is restricted to non-production environments to avoid unauthorized execution.

## 4. How to Test Manually
1. Verify health check:
   ```bash
   curl http://localhost:10000/health
   ```
   Expect: `{"status": "healthy", "db": true, "chroma": true, ...}`

2. Verify diagnostics:
   ```bash
   curl http://localhost:10000/diagnostics
   ```
   Expect: Detailed JSON with model availability and database counts.

3. Verify webhook endpoint:
   ```bash
   curl http://localhost:10000/webhook
   ```
   Expect: `{"ok": true, "message": "Webhook is active. Use POST for messages."}`

4. Test message processing (with `DEV_MODE=1`):
   ```bash
   curl -X POST http://localhost:10000/webhook/test -H "Content-Type: application/json" -d "{\"message\": \"Hello\"}"
   ```
   Expect: JSON response showing welcome/greeting message.
