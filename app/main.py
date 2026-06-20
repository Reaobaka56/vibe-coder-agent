from fastapi import FastAPI
from app.config import config
from app.routers import webhook, github, health

app = FastAPI(title="Vibe-Coder-Agent", version=config.APP_VERSION)

# Include routers
app.include_router(webhook.router)
app.include_router(github.router)
app.include_router(health.router)
