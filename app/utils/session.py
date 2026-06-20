import json
import redis
from datetime import datetime
from typing import Optional
from app.models import UserSession
from app.config import config

class SessionManager:
    def __init__(self, redis_url: str = None):
        self.redis = redis.from_url(redis_url or config.REDIS_URL, decode_responses=True)
        self.prefix = "vibe-coder:session:"
        self.ttl = 86400 * 7  # 7 days

    def _key(self, wa_number: str) -> str:
        return f"{self.prefix}{wa_number}"

    async def get(self, wa_number: str) -> Optional[UserSession]:
        """Get session by WhatsApp number."""
        data = self.redis.get(self._key(wa_number))
        if data:
            return UserSession.parse_raw(data)
        return None

    async def save(self, session: UserSession):
        """Save session to Redis."""
        self.redis.setex(
            self._key(session.wa_number),
            self.ttl,
            session.json()
        )

    async def delete(self, wa_number: str):
        """Delete session."""
        self.redis.delete(self._key(wa_number))

    async def add_to_conversation(self, wa_number: str, role: str, content: str):
        """Append to conversation history."""
        session = await self.get(wa_number)
        if session:
            session.conversation.append({
                "role": role,
                "content": content,
                "timestamp": str(datetime.utcnow())
            })
            # Trim to last N messages
            if len(session.conversation) > config.MAX_CONVERSATION_HISTORY:
                session.conversation = session.conversation[-config.MAX_CONVERSATION_HISTORY:]
            await self.save(session)
