from app.services.whatsapp import WhatsAppService
from app.services.qwen import QwenService
from app.services.github import GitHubService
from app.services.vercel import VercelService
from app.services.screenshot import ScreenshotService
from app.utils.session import SessionManager
from app.utils.rate_limit import RateLimiter

# Initialize service singletons
wa = WhatsAppService()
qwen = QwenService()
github = GitHubService()
vercel = VercelService()
screenshot = ScreenshotService()
sessions = SessionManager()
rate_limiter = RateLimiter()
