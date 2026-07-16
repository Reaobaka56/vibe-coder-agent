import os
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.config import config
from app.routers import webhook, github, health
from app.utils import db
from app.utils.secrets import audit_secrets_exposure, SecretsSafeFormatter

# Configure logging with secrets redaction
log_handler = logging.StreamHandler()
log_handler.setFormatter(SecretsSafeFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.root.addHandler(log_handler)
logging.root.setLevel(logging.INFO)

app = FastAPI(title="Vibe-Coder-Agent", version=config.APP_VERSION)

@app.on_event("startup")
async def startup():
    # Audit secrets exposure patterns
    audit_secrets_exposure()
    
    await db.init_db()

os.makedirs(config.SCREENSHOT_OUTPUT_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=config.SCREENSHOT_OUTPUT_DIR), name="static")

# Include routers
app.include_router(webhook.router)
app.include_router(github.router)
app.include_router(health.router)
