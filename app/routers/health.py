from fastapi import APIRouter
from app.config import config

router = APIRouter()

@router.get("/")
async def root():
    return {"app": config.APP_NAME, "version": config.APP_VERSION, "status": "🦅 soaring"}

@router.get("/health")
async def health():
    return {"status": "healthy", "services": ["whatsapp", "qwen", "github", "vercel", "screenshot"]}
