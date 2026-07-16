# Operational Quick Reference

## For Developers

### Running Tests
```bash
pip install -r requirements-test.txt
pytest tests/test_critical_paths.py -v
pytest tests/test_critical_paths.py::TestRateLimiting -v  # Run specific test class
```

### Checking for Secret Leaks
```bash
grep -r "PRIVATE_KEY\|API_KEY\|AUTH_TOKEN" app/ --include="*.py" | grep -v "config.py\|.env"
```

### Building Docker Image
```bash
docker build -t vibe-coder-agent .
docker run -it --env-file .env vibe-coder-agent
```

---

## For DevOps / Operations

### Monitoring Rate Limits
```bash
# Check current generation count for a user
redis-cli GET "vibe-coder:ratelimit:gen:{wa_number}:daily"

# Get all active rate limit keys
redis-cli KEYS "vibe-coder:ratelimit:*"

# Reset a user's daily limit (if needed)
redis-cli DEL "vibe-coder:ratelimit:gen:{wa_number}:daily"

# Reset all rate limits
redis-cli EVAL "return redis.call('del', unpack(redis.call('keys', 'vibe-coder:ratelimit:*')))" 0
```

### Monitoring Logs

#### Real-time error monitoring
```bash
tail -f logs/app.log | grep "\[ERROR\]\|\[WEBHOOK\]"
```

#### Track generation attempts
```bash
grep "\[NEW_PROJECT\]" logs/app.log | tail -20
```

#### Find failed operations
```bash
grep -E "\[ERROR\]|\[.*\] failed|\[.*\] Failed" logs/app.log
```

#### Find rate limit violations
```bash
grep "\[RATE_LIMIT\]\|\[COST_LIMIT\]" logs/app.log
```

#### Find security events
```bash
grep "\[SECURITY\]\|\[AUTH\]" logs/app.log
```

### Database Queries

#### Check user activity
```sql
SELECT wa_number, COUNT(*) as projects, MAX(created_at) as last_active
FROM users u
LEFT JOIN projects p ON u.wa_number = p.owner_wa
GROUP BY wa_number
ORDER BY last_active DESC;
```

#### Check project creation rate
```sql
SELECT DATE(created_at) as date, COUNT(*) as projects
FROM projects
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

#### Find stuck projects (edits > limit)
```sql
SELECT id, owner_wa, name, edit_count, created_at
FROM projects
WHERE edit_count >= 20
ORDER BY created_at DESC;
```

---

## For Admins / Support

### Generate Access Token (WhatsApp)
Send message to admin number:
```
gen token +12025551234 24h Test User Token
```

Response:
```
🔑 New access token: ABC123XYZ
Bound to: +12025551234
Expires in: 24h
Label: Test User Token
```

### List Access Tokens
Send message:
```
tokens
```

### Revoke Access Token
Send message:
```
revoke ABC123XYZ
```

### Monitor User Usage

Send message to get daily stats (requires code update to expose endpoint):
```bash
# Use admin endpoint (future feature)
curl -H "Authorization: Bearer {admin_token}" \
  http://localhost:8000/admin/stats/{wa_number}
```

### Emergency Operations

#### Stop accepting new projects (one user)
1. Revoke their access token: `revoke {token}`
2. Or set `MAX_GENERATIONS_PER_DAY=0` temporarily (requires restart)

#### Stop all projects (global)
Set in environment and restart:
```env
MAX_GENERATIONS_PER_DAY=0
REQUIRE_ACCESS_TOKEN=true
```

#### Reset a user's session (clear errors)
```bash
redis-cli DEL "vibe-coder:session:{wa_number}"
```

---

## Cost Estimation

### Per-Generation Costs
- **Qwen Planner**: ~$0.005-0.01
- **Qwen Architect**: ~$0.005-0.01
- **Qwen Coder**: ~$0.02-0.05
- **Qwen Reviewer**: ~$0.01-0.02
- **Qwen Tester**: ~$0.01-0.02
- **Vercel Deploy**: $0 (free tier)
- **Playwright Screenshot**: $0.001-0.005
- **Total per generation**: ~$0.055-0.15

### Daily Cost Estimates
- **10 users × 1 gen/day**: ~$0.55-1.50
- **10 users × 5 gen/day**: ~$2.75-7.50
- **10 users × 10 gen/day**: ~$5.50-15.00
- **50 users × 5 gen/day**: ~$13.75-37.50
- **100 users × 5 gen/day**: ~$27.50-75.00

### Budget Recommendation
- **MVP**: $50-100/day (10 users, 5 gen/day each)
- **Growth**: $200-500/day (50 users, 5 gen/day each)
- **Scale**: Contact vendor for enterprise pricing

---

## Alerts to Set Up

### Critical
- `[WEBHOOK] Unhandled exception` - Any unhandled error
- Rate of `[ERROR]` > 5% of requests
- `[SECURITY] Invalid Twilio signature` - Potential attack

### Warning
- `[RATE_LIMIT] Rejected request` - User hitting rate limit (check for abuse)
- `[COST_LIMIT] Daily generation limit` - User at cap
- `[QWEN] ... timeout` - Slow responses

### Info (for trending)
- `[NEW_PROJECT] Success` - Track new projects
- `[GENERATION] attempt recorded` - Track usage
- `[GITHUB] Repo created` - Track GitHub integration usage

---

## Troubleshooting

### User can't generate projects
1. Check rate limits: `redis-cli GET "vibe-coder:ratelimit:gen:{wa_number}:daily"`
2. Check access token: Send "tokens" command
3. Check logs for errors: `grep {wa_number} logs/app.log | tail -20`
4. Verify GitHub is connected: Look for `[GITHUB] token saved`

### Projects get stuck
1. Check Redis session: `redis-cli GET "vibe-coder:session:{wa_number}"`
2. Check Vercel status: Look for `[VERCEL] Deployed` logs
3. If stuck, reset: `redis-cli DEL "vibe-coder:session:{wa_number}"`

### Slow generation
1. Check LLM API latency
2. Check database connection
3. Check Vercel API rate limits
4. Consider scaling up LLM capacity

### Memory issues
- Monitor Redis: `redis-cli INFO memory`
- Check session retention: Default is 7 days
- Clear old sessions: Implement expiration policy

---

## Performance Baselines

- **Request latency**: 100-500ms (webhook validation)
- **Generation latency**: 30-120s (full pipeline)
- **Database query**: 10-50ms
- **Redis latency**: 1-5ms
- **LLM API**: 5-30s (Qwen)
- **Vercel Deploy**: 10-60s
- **Screenshot capture**: 5-15s

---

## Backup & Recovery

### Backup Strategy
```bash
# PostgreSQL
pg_dump -h localhost -U user vibecoder > backup.sql

# Redis
redis-cli BGSAVE
cp /var/lib/redis/dump.rdb backup.rdb

# GitHub repos (automatic)
# Backed up to user's GitHub account
```

### Recovery
```bash
# PostgreSQL
psql -h localhost -U user vibecoder < backup.sql

# Redis
redis-cli SHUTDOWN
cp backup.rdb /var/lib/redis/dump.rdb
redis-server
```

---

## Contact Points

- **Twilio**: https://console.twilio.com
- **GitHub App**: https://github.com/apps/vibe-coder-agent
- **DashScope**: https://dashscope.console.aliyun.com
- **Vercel**: https://vercel.com/dashboard
- **Redis Cloud** (if used): https://app.redislabs.com/

---

Last Updated: 2026-07-16
