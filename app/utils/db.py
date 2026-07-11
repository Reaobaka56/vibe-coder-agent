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
            cur.execute("ALTER TABLE access_tokens ADD COLUMN IF NOT EXISTS bound_wa_number TEXT")
            cur.execute("ALTER TABLE access_tokens ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ")
            cur.execute("ALTER TABLE access_tokens ADD COLUMN IF NOT EXISTS revoked BOOLEAN NOT NULL DEFAULT FALSE")
            cur.execute("ALTER TABLE access_tokens ADD COLUMN IF NOT EXISTS label TEXT")
            
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


async def create_access_token(created_by: str, bound_wa_number: Optional[str] = None, expires_in_hours: Optional[float] = None, label: Optional[str] = None) -> str:
    """Generate a new access token (admin only)."""
    if not config.DATABASE_URL:
        logger.warning("DATABASE_URL not set — token cannot persist")
        return None
    
    try:
        token = secrets.token_urlsafe(8)
        conn = _connect()
        with conn.cursor() as cur:
            if expires_in_hours is not None:
                cur.execute(
                    """
                    INSERT INTO access_tokens (token, created_by, bound_wa_number, expires_at, label) 
                    VALUES (%s, %s, %s, NOW() + %s::interval, %s)
                    """,
                    (token, created_by, bound_wa_number, f"{expires_in_hours} hours", label)
                )
            else:
                cur.execute(
                    """
                    INSERT INTO access_tokens (token, created_by, bound_wa_number, label) 
                    VALUES (%s, %s, %s, %s)
                    """,
                    (token, created_by, bound_wa_number, label)
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
            # Mark token as used, ensuring all rules are met
            cur.execute(
                """
                UPDATE access_tokens 
                SET used_by=%s, used_at=NOW() 
                WHERE token=%s 
                AND used_by IS NULL 
                AND revoked = FALSE
                AND (expires_at IS NULL OR expires_at > NOW())
                AND (bound_wa_number IS NULL OR bound_wa_number = %s)
                RETURNING token
                """,
                (wa_number, token, wa_number)
            )
            
            if cur.fetchone() is None:
                conn.close()
                logger.warning(f"Token redemption failed for {wa_number} — token invalid, used, revoked, expired, or bound to wrong number")
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

async def revoke_access_token(token: str) -> bool:
    if not config.DATABASE_URL:
        return False
    try:
        conn = _connect()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE access_tokens SET revoked = TRUE WHERE token = %s RETURNING token",
                (token,)
            )
            res = cur.fetchone()
        conn.commit()
        conn.close()
        return bool(res)
    except Exception as e:
        logger.error(f"Error revoking token: {e}")
        return False

async def list_access_tokens(limit: int = 10) -> list:
    if not config.DATABASE_URL:
        return []
    try:
        conn = _connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT token, created_by, bound_wa_number, expires_at, revoked, used_by, created_at, label
                FROM access_tokens
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,)
            )
            res = cur.fetchall()
        conn.close()
        return res
    except Exception as e:
        logger.error(f"Error listing tokens: {e}")
        return []


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
