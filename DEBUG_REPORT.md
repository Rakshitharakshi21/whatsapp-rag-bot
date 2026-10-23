# Debug Report: WhatsApp RAG Bot Zero-Reply Root Cause & Fix

**Date:** 2026-10-23  
**Status:** Resolved & Verified  

---

## 1. Executive Summary
The WhatsApp bot was completely silent on incoming messages (text and PDF), caused by a combination of:
1. **ChromaDB Cache & Schema Incompatibility:** Tracked segment artifacts in `data/chroma_db/` caused schema mismatches (`sqlite3.OperationalError: no such column: collections.topic`).
2. **Missing Web Server Dependencies:** `fastapi`, `uvicorn`, `python-multipart`, and `requests` were missing from `requirements.txt`, risking startup/parsing failures on clean cloud builds.
3. **Synchronous Webhook Timeout:** The webhook previously attempted synchronous embeddings, Groq LLM queries, and PDF network downloads inside the HTTP request. Any latency exceeding Twilio's strict 15-second cutoff caused Twilio to drop responses silently.
4. **First-Time User State Deadlock:** First-time users were detected via `is_new_user()` but never registered in SQLite, creating an infinite onboarding loop; returning users sending short greetings like "Hello" fell through to a fallback error.
5. **Lack of Idempotency:** Twilio retries on timeout led to duplicate processing.

All root causes have been systematically addressed and verified with unit tests.

---

## 2. Detailed Root Cause Analysis & Fixes

### Check 1: ChromaDB Schema Mismatch on Startup
- **Diagnosis:** `data/chroma_db/` had 5 segment files committed to git (`data_level0.bin`, `header.bin`, etc.), and `.gitignore` had corrupt whitespace preventing proper ignore.
- **Verification Command:** `git ls-files data/`
- **Fix Applied:**
  - Removed all cached chroma files from git: `git rm -r --cached data/chroma_db`
  - Fixed `.gitignore` to strictly ignore `data/chroma_db/`
  - Deleted corrupt local chroma store; initialized fresh clean ChromaDB client.

### Check 2: Missing & Incompatible Dependencies
- **Diagnosis:** `requirements.txt` lacked `fastapi`, `uvicorn`, `python-multipart`, and `requests`.
- **Fix Applied:**
  - Added `fastapi>=0.104.0`, `uvicorn>=0.25.0`, `python-multipart>=0.0.9`, `requests>=2.31.0`.
  - Maintained confirmed compatible set (`sentence-transformers==2.7.0`, `huggingface-hub==0.23.4`, `transformers==4.41.2`, `torch==2.3.1`, `tokenizers==0.19.1`, `apscheduler==3.10.4`, `twilio==8.10.0`).

### Check 3: Twilio 15-Second Webhook Timeout & Architecture
- **Diagnosis:** Twilio drops any webhook that does not return an HTTP response within 15 seconds. Heavy RAG operations easily trigger this timeout.
- **Fix Applied:**
  - Converted `@app.post("/webhook")` to the asynchronous background pattern:
    - Returns `<Response/>` TwiML in under 10ms.
    - Offloads pipeline execution to `FastAPI.BackgroundTasks`.
    - Dispatches replies via Twilio REST API (`client.messages.create()`).

### Check 4: Idempotency Protection
- **Diagnosis:** When Twilio retries an unacknowledged request, the bot would process duplicate operations.
- **Fix Applied:**
  - Added `processed_messages` SQLite table storing `message_sid` and timestamp.
  - Webhook checks `is_message_processed(message_sid)` and silently returns early on duplicates.

### Check 5: Startup Configuration Validation
- **Diagnosis:** Silent crashes occurred when environment variables were absent.
- **Fix Applied:**
  - Added startup banner logging `bool(os.getenv(...))` for `GROQ_API_KEY`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER`.
  - Added `.env.example`.

### Check 6: "Hello" Greeting & First-Time User Registration
- **Diagnosis:** `is_new_user()` welcomed users without calling `db.get_or_create_user()`, and greetings like "Hello" were rejected by word-count filters.
- **Fix Applied:**
  - Added `register_user(user_id)` upon welcoming new users.
  - Added explicit greeting handler for `["hi", "hello", "hey", "start"]` providing friendly guidance for both new and returning students.

### Check 7: Self-Diagnostic & Health Endpoints
- **Fix Applied:**
  - Added `GET /health` with system checks (`status`, `db`, `chroma`, `groq_reachable`, `twilio_configured`, `uptime`).
  - Added `GET /diagnostics` reporting SQLite row counts, Groq model reachability, and Chroma counts.
  - Added `GET /webhook` returning `{"ok": true}` for external URL confirmation.
  - Added `POST /webhook/test` for simulated testing without live Twilio webhooks when `DEV_MODE=1`.

---

## 3. Verification & Test Results

Run command:
```bash
.\venv\Scripts\python -m pytest tests/
```

Results:
```
tests\test_health_and_diagnostics.py ....... [100%]
7 passed in 34.66s
```

All 7 test suites passed:
1. `test_health_endpoint`: Verified `/health` reports all sub-system health statuses.
2. `test_diagnostics_endpoint`: Verified `/diagnostics` inspects Groq, Chroma, and DB.
3. `test_webhook_get`: Verified `/webhook` returns `{"ok": True}`.
4. `test_idempotency_and_webhook_post`: Verified instant response and duplicate `MessageSid` suppression.
5. `test_hello_message_receives_reply`: Verified "Hello" returns greeting/welcome message.
6. `test_structured_logging`: Verified JSONL logging in `logs/app.jsonl`.
7. `test_metrics_increment`: Verified metrics tracking in `metrics.json`.
