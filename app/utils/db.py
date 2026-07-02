import psycopg2
import psycopg2.extras
import secrets
import logging
from app.config import config

logger = logging.getLogger("db")

def _connect():
    """Create a database connection."""
    if not config.DATABASE_URL:
        logger.warning("DATABASE_URL not set — database functions cannot persist")
        return None
    return psycopg2.connect(config.DATABASE_URL)

def _ensure_tables():
    """Create tables if they don't exist."""
    if not config.DATABASE_URL:
        return
    
    try:
        conn = _connect()
        with conn.cursor() as cur:
            # Users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    wa_number TEXT PRIMARY KEY,
                    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            
            # Access tokens table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS access_tokens (
                    token TEXT PRIMARY KEY,
                    created_by TEXT,
                    used_by TEXT,
                    used_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error creating tables: {e}")

# Initialize tables on import
_ensure_tables()

async def upsert_user(wa_number: str) -> bool:
    """Create or update a user."""
    if not config.DATABASE_URL:
        logger.warning("DATABASE_URL not set — user cannot persist")
        return False
    
    try:
        conn = _connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (wa_number, is_verified)
                VALUES (%s, FALSE)
                ON CONFLICT (wa_number) DO NOTHING
                """,
                (wa_number,)
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error upserting user {wa_number}: {e}")
        return False

async def create_access_token(created_by: str) -> str:
    """Generate a new access token (admin only)."""
    if not config.DATABASE_URL:
        logger.warning("DATABASE_URL not set — token cannot persist")
        return None
    
    try:
        token = secrets.token_urlsafe(8)
        conn = _connect()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO access_tokens (token, created_by) VALUES (%s, %s)",
                (token, created_by)
            )
        conn.commit()
        conn.close()
        return token
    except Exception as e:
        logger.error(f"Error creating access token: {e}")
        return None

async def redeem_access_token(token: str, wa_number: str) -> bool:
    """Redeem an access token for a WhatsApp number."""
    if not config.DATABASE_URL:
        logger.warning("DATABASE_URL not set — token cannot be redeemed")
        return False
    
    try:
        conn = _connect()
        with conn.cursor() as cur:
            # Mark token as used
            cur.execute(
                "UPDATE access_tokens SET used_by=%s, used_at=NOW() WHERE token=%s AND used_by IS NULL",
                (wa_number, token)
            )
            
            if cur.rowcount == 0:
                conn.close()
                return False
            
            # Mark user as verified
            cur.execute(
                "UPDATE users SET is_verified=TRUE WHERE wa_number=%s",
                (wa_number,)
            )
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error redeeming token for {wa_number}: {e}")
        return False

async def is_verified(wa_number: str) -> bool:
    """Check if a WhatsApp number is verified."""
    if not config.DATABASE_URL:
        logger.warning("DATABASE_URL not set — cannot verify user")
        return False
    
    try:
        conn = _connect()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT is_verified FROM users WHERE wa_number=%s",
                (wa_number,)
            )
            row = cur.fetchone()
        conn.close()
        
        return bool(row and row[0])
    except Exception as e:
        logger.error(f"Error checking verification for {wa_number}: {e}")
        return False
