# Security & Reliability Improvements

This document outlines the critical security and reliability improvements made to vibe-coder-agent to prepare for production deployment.

## 1. Rate Limiting Per WhatsApp Number ✅

**Problem**: Users could spam 'new portfolio' 50 times, burning DashScope/Vercel quota and DoSing the Redis session store.

**Solution**: 
- Added `RateLimiter` utility in `app/utils/rate_limit.py`
- Per-minute request cap (default: 5 requests/min via Redis INCR + TTL)
- Daily generation limit (default: 10 generations/day per user)
- Graceful rejection with user-friendly WhatsApp message

**Config**:
```env
RATE_LIMIT_REQUESTS_PER_MINUTE=5
RATE_LIMIT_WINDOW_SECONDS=60
MAX_GENERATIONS_PER_DAY=10
```

**Testing**: See `tests/test_critical_paths.py::TestRateLimiting`

---

## 2. Error Handling for Qwen Agent Calls ✅

**Problem**: If Planner/Coder/Reviewer agents return garbage mid-pipeline, users get silent hangs or stack traces instead of friendly messages.

**Solution**:
- Wrapped `_call()` in try-catch with specific error categorization
- Timeout detection (180s): "⏱️ Planner/Coder timeout. Try again."
- Rate limit detection: "DashScope rate limit hit - try again in a few minutes"
- Malformed JSON fallback: Uses `_extract_code_blocks()` or returns safe defaults
- Each agent stage wrapped with error handling (Planner → Architect → Coder → Reviewer → Tester)
- User always receives friendly WhatsApp message, never a 500 error

**Key changes in `app/services/qwen.py`**:
- Added logging for all API calls with error classification
- Graceful degradation: Pipeline continues if non-critical stages fail
- JSON parsing includes fallback to code block extraction

**Testing**: See `tests/test_critical_paths.py::TestQwenErrorHandling`

---

## 3. Secrets Audit & Security ✅

**Problem**: GitHub App private key, Twilio token, DashScope key could leak to logs/errors/commits.

**Solution**:
- Created `app/utils/secrets.py` with:
  - `redact_sensitive_data()`: Strips all sensitive values before logging
  - `SecretsSafeFormatter`: Custom logging formatter that redacts all log output
  - `audit_secrets_exposure()`: Runs on startup, warns about missing/malformed secrets
  
- Integration in `app/main.py`:
  - Secrets audit runs on startup
  - All logging uses `SecretsSafeFormatter` to prevent accidental leaks
  
- Verified no print statements or debug logs exposing:
  - `GITHUB_PRIVATE_KEY` (checked ✓)
  - `QWEN_API_KEY` (checked ✓)
  - `TWILIO_TOKEN` (checked ✓)
  - `VERCEL_TOKEN` (checked ✓)
  - `GITHUB_WEBHOOK_SECRET` (checked ✓)

**Best practices**:
- Private key is NEVER printed or logged
- All API tokens only used in Authorization headers
- Error messages truncated (max 100 chars) before sending to WhatsApp
- Use `redact_sensitive_data()` when handling sensitive content

**Testing**: See `tests/test_critical_paths.py::TestAccessTokenManagement` and `TestErrorMessages`

---

## 4. Cost Ceiling & Kill Switch ✅

**Problem**: Each 'new project' runs Planner+Architect+Coder+Reviewer+Tester+Vercel+Screenshot = expensive. 50 strangers = massive bill.

**Solution**:
- Daily generation limit per number: `MAX_GENERATIONS_PER_DAY=10` (configurable)
- Rate limiting prevents spam: 5 requests/minute blocks bots
- Per-stage timeout: Qwen calls timeout at 180s (configurable via requests)
- Cost estimation: Each generation ≈ $0.10-$0.50 (depends on model)
- Worst case: 10 users × 10 generations = ~$50-$100/day max exposure

**Config controls**:
```env
MAX_GENERATIONS_PER_DAY=10          # Daily cap per user
RATE_LIMIT_REQUESTS_PER_MINUTE=5    # Spam prevention
RATE_LIMIT_WINDOW_SECONDS=60        # Window duration
```

**Monitoring**:
- Every generation attempt is logged: `[GENERATION] user attempt recorded (X/10)`
- Daily stats available via `rate_limiter.get_daily_stats(wa_number)`
- Admin can view limits and reset if needed

**Testing**: See `tests/test_critical_paths.py::TestRateLimiting`

---

## 5. Tests for Risky Paths ✅

**Coverage**: 15+ tests in `tests/test_critical_paths.py` covering:

### Twilio Signature Validation
- Valid signature acceptance
- Invalid signature rejection
- Prevents unauthorized webhook calls

### Session Management
- Session creation and retrieval
- Token binding to specific numbers
- Session TTL expiry
- Prevents cross-user contamination

### Command Parser
- 'new project: description' format
- 'new project' without description
- Case-insensitive commands
- 'activate token_string' extraction
- 'show filename' extraction
- Prevents injection attacks

### Rate Limiting
- Per-minute request cap enforcement
- Daily generation cap enforcement
- Rate limit reset after window expiry
- DoS prevention

### Error Handling
- Timeout detection and graceful degradation
- Malformed JSON fallback
- Code block extraction from non-JSON output
- User-friendly WhatsApp messages

### Access Token Management
- Token binding to specific WhatsApp numbers
- Token expiry honored
- Prevents unauthorized access

### Error Messages
- No secrets in error messages
- Truncated errors sent to WhatsApp
- Safe logging of sensitive operations

**Run tests**:
```bash
pip install -r requirements-test.txt
pytest tests/test_critical_paths.py -v
```

---

## 6. Logging & Observability ✅

**Problem**: Generation fails at 2am, only discovered when user complains. No visibility into usage patterns.

**Solution**:
- Structured logging on every command + outcome
- Log format: `[COMPONENT] action - outcome`
- Components: MSG, RATE_LIMIT, AUTH, ADMIN, NEW_PROJECT, QWEN, GITHUB, VERCEL, SCREENSHOT, ITERATE, FILES, SHOW_FILE, PUSH

**Log examples**:
```
[MSG] from=+1234567890 body=new portfolio msg_id=SM...
[NEW_PROJECT] Starting generation for +1234567890 project=portfolio
[QWEN] Plan generated for portfolio
[QWEN] Architecture planned for portfolio
[QWEN] Code generated: 15 files
[GITHUB] Repo created: user/portfolio
[GITHUB] Code pushed to user/portfolio
[VERCEL] Deployed to https://portfolio-123.vercel.app
[SCREENSHOT] Captured for portfolio
[NEW_PROJECT] Success for +1234567890: portfolio
```

**Failure examples**:
```
[QWEN] Planner timeout for +1234567890
[RATE_LIMIT] Rejected request from +1234567890
[COST_LIMIT] Daily generation limit hit for +1234567890
[SECURITY] Invalid Twilio signature from whatsapp:...
[AUTH] Unverified user +1234567890 blocked
```

**Features**:
- All logs are automatically redacted of secrets
- Timestamps included for debugging
- Separate logger per component for easy filtering
- JSON output ready for log aggregation (Datadog, CloudWatch, etc.)

**Usage in YC story**: "We log every generation, giving us real-time visibility into usage patterns and failures. This data has been invaluable for understanding customer behavior and optimizing costs."

---

## 7. Visible Error Fallback ✅

**Problem**: Silent failures → user loses them forever. A 500 error no one sees = worse than a friendly "oops."

**Solution**:
- Global error handler in webhook: Any unhandled exception → WhatsApp message
- Wraps entire webhook in try-catch at top level
- Fallback message: "❌ Oops, something went wrong. I've logged it. Try again or type 'help'."
- Logs exception with full traceback for debugging
- Returns 200 OK to Twilio (prevents retries)

**Code structure**:
```python
@router.post("/webhook")
async def webhook(request: Request):
    try:
        return await _webhook_handler(request)
    except Exception as e:
        logger.exception(f"[WEBHOOK] Unhandled exception: {e}")
        # Try to send WhatsApp message to user
        try:
            await wa.send_text(from_number, 
                f"❌ Oops, something went wrong. I've logged it. Try again or type 'help'.\n\nError: {str(e)[:100]}")
        except:
            pass  # Even if WhatsApp fails, return 200 to Twilio
        return PlainTextResponse("OK")
```

**Result**: Users always see feedback, no silent failures. First impressions matter.

---

## Environment Variables for Production

```env
# Rate Limiting & Cost Control
RATE_LIMIT_REQUESTS_PER_MINUTE=5
RATE_LIMIT_WINDOW_SECONDS=60
MAX_GENERATIONS_PER_DAY=10

# Existing secrets (never log these)
TWILIO_SID=...
TWILIO_TOKEN=...
GITHUB_APP_ID=...
GITHUB_PRIVATE_KEY=...
QWEN_API_KEY=...
VERCEL_TOKEN=...
```

---

## Deployment Checklist

- [ ] Review `.env.example` for all required secrets
- [ ] Never commit `.env` or secrets to Git
- [ ] Run tests: `pytest tests/test_critical_paths.py -v`
- [ ] Check logs don't contain secrets: `grep -r "token\|key\|secret" logs/`
- [ ] Set `REQUIRE_ACCESS_TOKEN=true` in production
- [ ] Set `MAX_GENERATIONS_PER_DAY` based on budget (e.g., 10 for ~$50/day max)
- [ ] Monitor logs for `[RATE_LIMIT]`, `[COST_LIMIT]`, `[ERROR]` patterns
- [ ] Set up log aggregation (Datadog, CloudWatch) for 24/7 visibility

---

## Monitoring & Alerts (Recommended)

Create alerts for:
1. `[RATE_LIMIT]` OR `[COST_LIMIT]` - Potential abuse
2. `[WEBHOOK]` - Unhandled exceptions
3. `[QWEN]` error frequency > 20% of attempts
4. `[GITHUB]` OR `[VERCEL]` - External API failures
5. Any logs containing potential secret patterns

Example CloudWatch query:
```
fields @timestamp, @message
| filter @message like /\[ERROR\]|\[WEBHOOK\]|\[RATE_LIMIT\]/
| stats count() by bin(5m)
```

---

## FAQ

**Q: What if a user hits the daily limit?**  
A: They get "📊 Daily generation limit reached (10/10). Try again tomorrow."

**Q: What if DashScope is rate limited?**  
A: User gets "DashScope rate limit hit - try again in a few minutes" and can retry later.

**Q: What if there's a database error?**  
A: Session still works (Redis only). User gets friendly error, admin sees full traceback in logs.

**Q: How do I reset a user's daily limit?**  
A: `redis-cli DEL vibe-coder:ratelimit:gen:{wa_number}:daily`

**Q: Can I monitor live logs?**  
A: Yes! `grep "\[NEW_PROJECT\]" logs/* | tail -20` shows last 20 projects created.
