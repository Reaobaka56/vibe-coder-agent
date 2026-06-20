import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Twilio
    TWILIO_SID = os.getenv("TWILIO_SID", "")
    TWILIO_TOKEN = os.getenv("TWILIO_TOKEN", "")
    TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

    # Redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

    # GitHub App
    GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")
    GITHUB_PRIVATE_KEY = os.getenv("GITHUB_PRIVATE_KEY", "").replace("\n", "\n")
    GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

    # Vercel
    VERCEL_TOKEN = os.getenv("VERCEL_TOKEN", "")
    VERCEL_TEAM_ID = os.getenv("VERCEL_TEAM_ID", "")

    # Qwen
    QWEN_API_URL = os.getenv("QWEN_API_URL", "http://localhost:11434/api/generate")
    QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen2.5-coder:14b")
    QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")

    # Screenshot
    SCREENSHOT_VIEWPORT_MOBILE = {"width": 390, "height": 844}
    SCREENSHOT_VIEWPORT_DESKTOP = {"width": 1280, "height": 800}
    SCREENSHOT_OUTPUT_DIR = "/tmp/screenshots"

    # App
    APP_NAME = "Raptor-AI"
    APP_VERSION = "0.1.0"
    MAX_MESSAGE_LENGTH = 1500
    MAX_CONVERSATION_HISTORY = 10

config = Config()
