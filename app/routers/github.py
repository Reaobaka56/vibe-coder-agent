from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

router = APIRouter(prefix="/auth/github")

@router.get("/callback")
async def github_callback(code: str, installation_id: str = None):
    """Handle GitHub App installation callback."""
    # Exchange code for token (OAuth flow)
    # In production: implement full OAuth
    return JSONResponse({
        "status": "success",
        "message": "GitHub connected! You can close this window and return to WhatsApp.",
        "installation_id": installation_id
    })


@router.post("/webhook")
async def github_webhook(request: Request):
    """Handle GitHub App webhook events."""
    payload = await request.json()
    event = request.headers.get("X-GitHub-Event")

    if event == "installation" and payload.get("action") == "created":
        installation_id = payload["installation"]["id"]
        # Store installation_id for user (need to map to WA number)
        pass

    return PlainTextResponse("OK")
