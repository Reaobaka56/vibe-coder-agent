import redis
import logging
from app.config import config
from datetime import datetime, timedelta

logger = logging.getLogger("rate_limit")


class RateLimiter:
    """Redis-backed rate limiter for per-number request and generation caps."""
    
    def __init__(self, redis_url: str = None):
        self.redis = redis.from_url(redis_url or config.REDIS_URL, decode_responses=True)
        self.request_prefix = "vibe-coder:ratelimit:req:"
        self.generation_prefix = "vibe-coder:ratelimit:gen:"
        self.request_window = config.RATE_LIMIT_WINDOW_SECONDS
        self.request_limit = config.RATE_LIMIT_REQUESTS_PER_MINUTE
        self.daily_gen_limit = config.MAX_GENERATIONS_PER_DAY
    
    def check_request_rate_limit(self, wa_number: str) -> tuple[bool, str]:
        """
        Check if user has exceeded request rate limit (e.g., 5 requests/minute).
        Returns (allowed: bool, message: str)
        """
        key = f"{self.request_prefix}{wa_number}"
        try:
            current = int(self.redis.get(key) or 0)
            if current >= self.request_limit:
                logger.warning(f"[RATE_LIMIT] {wa_number} exceeded request limit ({current}/{self.request_limit})")
                ttl = self.redis.ttl(key)
                return False, f"⏱️ Too many requests. Please wait {ttl}s before trying again."
            
            # Increment and set TTL
            self.redis.incr(key)
            if current == 0:  # First request in window
                self.redis.expire(key, self.request_window)
            
            return True, ""
        except Exception as e:
            logger.error(f"[RATE_LIMIT] error checking request limit for {wa_number}: {e}")
            return True, ""  # Fail open on Redis error
    
    def check_daily_generation_limit(self, wa_number: str) -> tuple[bool, str]:
        """
        Check if user has exceeded daily generation limit.
        Returns (allowed: bool, message: str)
        """
        key = f"{self.generation_prefix}{wa_number}:daily"
        try:
            current = int(self.redis.get(key) or 0)
            if current >= self.daily_gen_limit:
                logger.warning(f"[COST_LIMIT] {wa_number} exceeded daily generation limit ({current}/{self.daily_gen_limit})")
                return False, f"📊 Daily generation limit reached ({current}/{self.daily_gen_limit}). Try again tomorrow."
            
            return True, ""
        except Exception as e:
            logger.error(f"[RATE_LIMIT] error checking daily generation limit for {wa_number}: {e}")
            return True, ""  # Fail open on Redis error
    
    def record_generation_attempt(self, wa_number: str):
        """Record a generation attempt (e.g., 'new project' command)."""
        key = f"{self.generation_prefix}{wa_number}:daily"
        try:
            current = int(self.redis.get(key) or 0)
            self.redis.incr(key)
            # Set daily expiry (resets at midnight UTC)
            if current == 0:
                tomorrow = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                ttl = int((tomorrow - datetime.utcnow()).total_seconds())
                self.redis.expire(key, ttl)
            logger.info(f"[GENERATION] {wa_number} attempt recorded ({current + 1}/{self.daily_gen_limit})")
        except Exception as e:
            logger.error(f"[RATE_LIMIT] error recording generation attempt for {wa_number}: {e}")
    
    def get_daily_stats(self, wa_number: str) -> dict:
        """Get current daily generation stats for a user."""
        key = f"{self.generation_prefix}{wa_number}:daily"
        try:
            current = int(self.redis.get(key) or 0)
            ttl = self.redis.ttl(key)
            return {
                "current": current,
                "limit": self.daily_gen_limit,
                "remaining": max(0, self.daily_gen_limit - current),
                "resets_in_seconds": ttl if ttl > 0 else 0
            }
        except Exception as e:
            logger.error(f"[RATE_LIMIT] error getting daily stats for {wa_number}: {e}")
            return {"current": 0, "limit": self.daily_gen_limit, "remaining": self.daily_gen_limit, "resets_in_seconds": 0}
