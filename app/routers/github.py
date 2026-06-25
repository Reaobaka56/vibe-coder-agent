import hmac
import hashlib
import urllib.parse
import asyncio
import requests
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from app.config import config
from app.dependencies import sessions
from app.models import UserSession
from app.utils import db
from app.utils.wa import normalise_wa

router = APIRouter(prefix="/auth/github")

@router.get("/login")
async def github_login(wa_number: str):
    """Redirect to GitHub OAuth login."""
    client_id = config.GITHUB_CLIENT_ID
    redirect_uri = urllib.parse.quote_plus(f"{config.BASE_URL}/auth/github/callback")
    # Store wa_number in state to map back after auth
    state = urllib.parse.quote_plus(normalise_wa(wa_number))
    
    url = f"https://github.com/login/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&state={state}"
    return RedirectResponse(url)

@router.get("/callback")
async def github_callback(code: str, state: str = None, error: str = None):
    """Handle GitHub OAuth callback and exchange code for token."""
    if error:
        return PlainTextResponse(f"OAuth Error: {error}", status_code=400)
    
    if not state:
        return PlainTextResponse("Missing state parameter", status_code=400)
        
    wa_number = normalise_wa(urllib.parse.unquote_plus(state))
    
    # Exchange code for access token
    payload = {
        "client_id": config.GITHUB_CLIENT_ID,
        "client_secret": config.GITHUB_CLIENT_SECRET,
        "code": code,
        "redirect_uri": f"{config.BASE_URL}/auth/github/callback"
    }
    headers = {"Accept": "application/json"}
    
    resp = await asyncio.to_thread(requests.post, "https://github.com/login/oauth/access_token", data=payload, headers=headers)
    data = resp.json()
    
    if "access_token" not in data:
        return JSONResponse({"error": "Failed to get access token", "details": data}, status_code=400)
        
    access_token = data["access_token"]
    
    # Persist the token to Postgres so fresh workers can authorize future messages.
    await db.upsert_user(wa_number, access_token)

    # Also refresh Redis session state for the active conversation cache.
    session = await sessions.get(wa_number) or UserSession(wa_number=wa_number)
    session.github_token = access_token
    await sessions.save(session)
    
    return PlainTextResponse("GitHub connected! You can close this window and return to WhatsApp to start generating projects.")

@router.post("/webhook")
async def github_webhook(request: Request):
    """Handle GitHub App webhook events with signature validation."""
    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature")
        
    payload = await request.body()
    
    # Verify signature
    secret = config.GITHUB_WEBHOOK_SECRET.encode()
    expected_signature = "sha256=" + hmac.new(secret, payload, hashlib.sha256).hexdigest()
    
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    # The payload is now verified
    try:
        data = await request.json()
    except:
        return PlainTextResponse("OK")
        
    event = request.headers.get("X-GitHub-Event")

    if event == "installation" and data.get("action") == "created":
        installation_id = data["installation"]["id"]
        # In a real app we'd map this installation to a user if needed, 
        # but since we use user-to-server OAuth for repos, we just acknowledge.
        pass

    return PlainTextResponse("OK")
