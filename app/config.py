import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Twilio
    TWILIO_SID = os.getenv("TWILIO_SID", "")
    TWILIO_TOKEN = os.getenv("TWILIO_TOKEN", "")
    TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

    # Redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # GitHub (using raw string replacement for multi-line support)
    GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
    GITHUB_PRIVATE_KEY = os.getenv("GITHUB_PRIVATE_KEY", "").replace("\\n", "\n")
    GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")

    # Vercel
    VERCEL_TOKEN = os.getenv("VERCEL_TOKEN")
    VERCEL_TEAM_ID = os.getenv("VERCEL_TEAM_ID", "")

    # Qwen
    QWEN_API_URL = os.getenv("QWEN_API_URL", "http://localhost:11434/api/generate")
    QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen2.5-coder:14b")
    QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")

    # Screenshot
    SCREENSHOT_VIEWPORT_MOBILE = {"width": 390, "height": 844}
    SCREENSHOT_VIEWPORT_DESKTOP = {"width": 1280, "height": 720}
    SCREENSHOT_OUTPUT_DIR = "app/static/screenshots"

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    
    # Auth
    ADMIN_WA_NUMBERS = [n.strip() for n in os.getenv("ADMIN_WA_NUMBERS", "").split(",") if n.strip()]
    REQUIRE_ACCESS_TOKEN = os.getenv("REQUIRE_ACCESS_TOKEN", "true").lower() == "true"

    # App
    APP_NAME = "Vibe-Coder-Agent"
    BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
    APP_VERSION = "0.1.0"
    MAX_MESSAGE_LENGTH = 1500
    MAX_CONVERSATION_HISTORY = 10
    MAX_PROJECTS_PER_NUMBER = int(os.getenv("MAX_PROJECTS_PER_NUMBER", "2"))
    MAX_EDITS_PER_PROJECT = int(os.getenv("MAX_EDITS_PER_PROJECT", "20"))
    
    # Rate limiting & cost controls
    RATE_LIMIT_REQUESTS_PER_MINUTE = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "5"))
    RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    MAX_GENERATIONS_PER_DAY = int(os.getenv("MAX_GENERATIONS_PER_DAY", "10"))
    MAX_GENERATION_ATTEMPTS_BEFORE_COOLDOWN = int(os.getenv("MAX_GENERATION_ATTEMPTS_BEFORE_COOLDOWN", "3"))

config = Config()
