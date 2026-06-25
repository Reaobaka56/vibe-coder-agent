import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.config import config
from app.routers import webhook, github, health
from app.utils import db

app = FastAPI(title="Vibe-Coder-Agent", version=config.APP_VERSION)

@app.on_event("startup")
async def startup():
    await db.init_db()

os.makedirs(config.SCREENSHOT_OUTPUT_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=config.SCREENSHOT_OUTPUT_DIR), name="static")

# Include routers
app.include_router(webhook.router)
app.include_router(github.router)
app.include_router(health.router)
