from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime

class UserSession(BaseModel):
    wa_number: str
    github_token: Optional[str] = None
    github_installation_id: Optional[str] = None
    current_repo: Optional[str] = None
    current_branch: Optional[str] = None
    project_type: str = "nextjs"
    files: Dict[str, str] = {}
    last_preview_url: Optional[str] = None
    last_screenshot_path: Optional[str] = None
    conversation: List[Dict] = []
    created_at: datetime = datetime.utcnow()

class WhatsAppMessage(BaseModel):
    from_number: str
    body: str
    message_id: str
    media_url: Optional[str] = None
    media_type: Optional[str] = None

class GeneratedProject(BaseModel):
    repo_name: str
    branch: str
    files: Dict[str, str]
    commit_message: str
    preview_url: Optional[str] = None
