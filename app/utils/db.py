from typing import Optional
import psycopg
from psycopg.rows import dict_row
from app.config import config
import secrets
import logging

logger = logging.getLogger("db")


def _connect():
    if not config.DATABASE_URL:
        logger.warning("DATABASE_URL not set — database functions cannot persist")
        return None
    return psycopg.connect(config.DATABASE_URL, row_factory=dict_row)


async def init_db():
    """Create persistence tables used for OAuth, token auth, and quota enforcement."""
    if not config.DATABASE_URL:
        return
    try:
        conn = _connect()
        with conn.cursor() as cur:
            # Users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    wa_number TEXT PRIMARY KEY,
                    github_token TEXT,
                    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            
            # Access tokens table for invite-based auth
            cur.execute("""
                CREATE TABLE IF NOT EXISTS access_tokens (
                    token TEXT PRIMARY KEY,
                    created_by TEXT NOT NULL,
                    used_by TEXT,
                    used_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            
            # Projects table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id BIGSERIAL PRIMARY KEY,
                    owner_wa TEXT NOT NULL REFERENCES users(wa_number) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    repo_full_name TEXT,
                    edit_count INTEGER NOT NULL DEFAULT 0,
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_projects_owner_active
                ON projects(owner_wa, active)
            """)
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")


async def upsert_user(wa_number: str, github_token: Optional[str] = None):
    """Create or update a user."""
    if not config.DATABASE_URL:
        logger.warning("DATABASE_URL not set — user cannot persist")
        return
    
    try:
        conn = _connect()
        with conn.cursor() as cur:
            if github_token:
                cur.execute(
                    """
                    INSERT INTO users (wa_number, github_token, is_verified)
                    VALUES (%s, %s, FALSE)
                    ON CONFLICT (wa_number) DO UPDATE SET github_token=%s, updated_at=NOW()
                    """,
                    (wa_number, github_token, github_token)
                )
            else:
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
    except Exception as e:
        logger.error(f"Error upserting user {wa_number}: {e}")


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
        logger.info(f"Access token created by {created_by}")
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
                logger.warning(f"Token redemption failed for {wa_number} — token invalid or already used")
                return False
            
            # Mark user as verified
            cur.execute(
                "UPDATE users SET is_verified=TRUE WHERE wa_number=%s",
                (wa_number,)
            )
        
        conn.commit()
        conn.close()
        logger.info(f"Token redeemed successfully for {wa_number}")
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
        
        return bool(row and row.get("is_verified"))
    except Exception as e:
        logger.error(f"Error checking verification for {wa_number}: {e}")
        return False

                INSERT INTO users (wa_number, github_token, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (wa_number) DO UPDATE SET
                    github_token = COALESCE(EXCLUDED.github_token, users.github_token),
                    updated_at = NOW()
                """,
                (wa_number, github_token),
            )
        conn.commit()


async def get_github_token(wa_number: str) -> Optional[str]:
    if not config.DATABASE_URL:
        return None
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT github_token FROM users WHERE wa_number = %s", (wa_number,))
            row = cur.fetchone()
            return row["github_token"] if row else None


async def count_projects(wa_number: str) -> int:
    if not config.DATABASE_URL:
        return 0
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM projects WHERE owner_wa = %s", (wa_number,))
            return cur.fetchone()["count"]


async def create_project(wa_number: str, name: str, repo_full_name: str):
    if not config.DATABASE_URL:
        return
    await upsert_user(wa_number)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE projects SET active = FALSE, updated_at = NOW() WHERE owner_wa = %s", (wa_number,))
            cur.execute(
                """
                INSERT INTO projects (owner_wa, name, repo_full_name, edit_count, active)
                VALUES (%s, %s, %s, 0, TRUE)
                """,
                (wa_number, name, repo_full_name),
            )
        conn.commit()


async def get_active_project(wa_number: str, repo_full_name: Optional[str] = None):
    if not config.DATABASE_URL:
        return None
    with _connect() as conn:
        with conn.cursor() as cur:
            if repo_full_name:
                cur.execute(
                    """
                    SELECT id, edit_count FROM projects
                    WHERE owner_wa = %s AND repo_full_name = %s
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (wa_number, repo_full_name),
                )
            else:
                cur.execute(
                    """
                    SELECT id, edit_count FROM projects
                    WHERE owner_wa = %s AND active = TRUE
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (wa_number,),
                )
            return cur.fetchone()


async def increment_edit_count(project_id: int):
    if not config.DATABASE_URL:
        return
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE projects SET edit_count = edit_count + 1, updated_at = NOW() WHERE id = %s",
                (project_id,),
            )
        conn.commit()
