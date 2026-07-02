import hmac
import hashlib
import urllib.parse
import asyncio
import requests
import logging
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from app.config import config
from app.dependencies import sessions

logger = logging.getLogger("github")

router = APIRouter(prefix="/auth/github")

@router.get("/login")
async def github_login(wa_number: str):
    """Redirect to GitHub OAuth login."""
    client_id = config.GITHUB_CLIENT_ID
    redirect_uri = urllib.parse.quote_plus(f"{config.BASE_URL}/auth/github/callback")
    # Store wa_number in state to map back after auth
    state = urllib.parse.quote_plus(wa_number)
    
    # Add scope so token has repo access
    url = f"https://github.com/login/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&state={state}&scope=repo,read:user"
    return RedirectResponse(url)

@router.get("/callback")
async def github_callback(code: str, state: str = None, error: str = None):
    """Handle GitHub OAuth callback and exchange code for token."""
    if error:
        logger.warning(f"GitHub OAuth error: {error}")
        return PlainTextResponse(f"OAuth Error: {error}", status_code=400)
    
    if not state:
        logger.error("Missing state parameter in callback")
        return PlainTextResponse("Missing state parameter", status_code=400)
        
    wa_number = urllib.parse.unquote_plus(state)
    
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
        logger.error(f"[github_callback] token exchange failed for {wa_number}: {data}")
        return JSONResponse({"error": "Failed to get access token", "details": data}, status_code=400)
    
    logger.info(f"[github_callback] token exchange successful for {wa_number}")
    access_token = data["access_token"]
    
    # Get user session
    session = await sessions.get(wa_number)
    if not session:
        logger.error(f"No active session for WhatsApp number {wa_number}")
        return PlainTextResponse(f"No active session for WhatsApp number {wa_number}. Text the bot first.", status_code=400)
        
    # Store token
    session.github_token = access_token
    await sessions.save(session)
    
    logger.info(f"[github_callback] token saved for {wa_number}")
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
