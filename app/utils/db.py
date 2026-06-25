from typing import Optional
import psycopg
from psycopg.rows import dict_row
from app.config import config


def _connect():
    return psycopg.connect(config.DATABASE_URL, row_factory=dict_row)


async def init_db():
    """Create persistence tables used for OAuth and quota enforcement."""
    if not config.DATABASE_URL:
        return
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    wa_number TEXT PRIMARY KEY,
                    github_token TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
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


async def upsert_user(wa_number: str, github_token: Optional[str] = None):
    if not config.DATABASE_URL:
        return
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
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
