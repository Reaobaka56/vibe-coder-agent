import os
import re
import uuid
from datetime import datetime
from fastapi import FastAPI, Request, Response, BackgroundTasks
from fastapi.responses import PlainTextResponse, JSONResponse
from app.models import UserSession, WhatsAppMessage
from app.config import config
from app.services.whatsapp import WhatsAppService
from app.services.qwen import QwenService
from app.services.github import GitHubService
from app.services.vercel import VercelService
from app.services.screenshot import ScreenshotService
from app.utils.session import SessionManager

app = FastAPI(title="Raptor-AI", version=config.APP_VERSION)

# Services
wa = WhatsAppService()
qwen = QwenService()
github = GitHubService()
vercel = VercelService()
screenshot = ScreenshotService()
sessions = SessionManager()

# ───────────────────────────────────────────────
# Webhook Entry Point
# ───────────────────────────────────────────────

@app.post("/webhook")
async def webhook(request: Request):
    """Handle incoming WhatsApp messages from Twilio."""
    form = await request.form()

    msg = WhatsAppMessage(
        from_number=form.get("From", "").replace("whatsapp:", ""),
        body=form.get("Body", ""),
        message_id=form.get("MessageSid", ""),
        media_url=form.get("MediaUrl0"),
        media_type=form.get("MediaContentType0")
    )

    # Get or create session
    session = await sessions.get(msg.from_number)
    if not session:
        session = UserSession(wa_number=msg.from_number)

    # Route by intent
    body_lower = msg.body.lower().strip()

    if body_lower.startswith("new "):
        await handle_new_project(session, msg)
    elif body_lower in ("screenshot", "preview", "ss"):
        await handle_screenshot(session, msg)
    elif body_lower == "files":
        await handle_list_files(session, msg)
    elif body_lower.startswith("show "):
        await handle_show_file(session, msg)
    elif body_lower == "push":
        await handle_push(session, msg)
    elif body_lower == "link github":
        await handle_link_github(session, msg)
    elif body_lower in ("help", "start", "hi", "hello"):
        await handle_help(session, msg)
    else:
        # Default: iterate on current project
        await handle_iterate(session, msg)

    # Save session
    await sessions.save(session)

    # Twilio expects 200 OK with empty response
    return PlainTextResponse("OK")


# ───────────────────────────────────────────────
# Command Handlers
# ───────────────────────────────────────────────

async def handle_help(session: UserSession, msg: WhatsAppMessage):
    """Send help message."""
    help_text = """🦅 *Raptor-AI* — Vibecode webapps via WhatsApp

*Commands:*
• `new {name}: {description}` — Create a new project
• `{any text}` — Edit current project
• `screenshot` — Get latest preview
• `files` — List project files
• `show {filename}` — View file contents
• `push` — Commit changes to GitHub
• `link github` — Connect your GitHub
• `help` — Show this message

*Example:*
`new portfolio: landing page with dark mode and animated hero`

Then reply: *make the button bigger* or *add a contact form*"""

    await wa.send_text(msg.from_number, help_text)


async def handle_new_project(session: UserSession, msg: WhatsAppMessage):
    """Create new project from description."""
    # Parse: "new portfolio: landing page with neon gradient"
    text = msg.body[4:].strip()  # Remove "new "

    if ":" in text:
        parts = text.split(":", 1)
        project_name = parts[0].strip().replace(" ", "-").lower()
        description = parts[1].strip()
    else:
        project_name = text.replace(" ", "-").lower()[:30]
        description = text

    # Sanitize project name
    project_name = re.sub(r'[^a-z0-9-]', '', project_name)
    if not project_name:
        project_name = f"project-{uuid.uuid4().hex[:6]}"

    # Check GitHub link
    if not session.github_token:
        await wa.send_text(msg.from_number, 
            "🔗 *Link GitHub first!*\n"
            "Visit: https://github.com/apps/raptor-ai/installations\n"
            "Then reply `link github`")
        return

    await wa.send_text(msg.from_number, f"🚀 Generating *{project_name}*...")

    try:
        # Generate code with Qwen
        files = qwen.generate_project(description, session.project_type)

        if not files:
            await wa.send_text(msg.from_number, 
                "❌ Failed to generate code. Try again with a clearer description.")
            return

        # Create GitHub repo
        await wa.send_text(msg.from_number, "📁 Creating GitHub repo...")
        repo_full_name = await github.create_repo(
            session.github_token, 
            project_name, 
            description
        )

        session.current_repo = repo_full_name
        session.current_branch = "main"
        session.files = {k: hash(v) for k, v in files.items()}

        # Push to GitHub
        await wa.send_text(msg.from_number, "📤 Pushing code to GitHub...")
        await github.commit_files(
            session.github_token,
            repo_full_name,
            "main",
            files,
            f"🦅 Raptor-AI initial commit: {description[:50]}"
        )

        # Deploy to Vercel
        await wa.send_text(msg.from_number, "🌐 Deploying to Vercel...")
        preview_url = await vercel.deploy_repo(repo_full_name, project_name, "main")
        session.last_preview_url = preview_url

        # Screenshot
        await wa.send_text(msg.from_number, "📸 Capturing preview...")
        img_path = await screenshot.capture(preview_url)

        caption = (f"✅ *{project_name}* is live!\n"
                   f"🔗 {preview_url}\n"
                   f"📁 github.com/{repo_full_name}\n\n"
                   f"Reply to iterate (e.g., *make the button bigger*)")

        await wa.send_image(msg.from_number, img_path, caption=caption)

    except Exception as e:
        await wa.send_text(msg.from_number, 
            f"❌ Error: {str(e)[:200]}\nTry again or type `help`.")


async def handle_iterate(session: UserSession, msg: WhatsAppMessage):
    """Edit existing project based on natural language."""
    if not session.current_repo:
        await wa.send_text(msg.from_number,
            "No active project. Start with: `new {name}: {description}`")
        return

    if not session.github_token:
        await wa.send_text(msg.from_number, "🔗 Link GitHub first: `link github`")
        return

    await wa.send_text(msg.from_number, "🧠 Understanding your edit...")

    try:
        # Determine target file
        target_file = None
        for fname in session.files.keys():
            if fname.lower() in msg.body.lower():
                target_file = fname
                break

        if not target_file:
            # Use Qwen to identify target
            file_list = "\n".join(session.files.keys())
            target_file = qwen.identify_target_file(file_list, msg.body)

            # Validate
            if target_file not in session.files:
                # Default to most likely file
                candidates = [f for f in session.files.keys() 
                            if any(ext in f for ext in [".tsx", ".jsx", ".css"])]
                target_file = candidates[0] if candidates else list(session.files.keys())[0]

        # Get current content
        current = await github.get_file(
            session.github_token,
            session.current_repo,
            session.current_branch,
            target_file
        )

        await wa.send_text(msg.from_number, f"✏️ Editing *{target_file}*...")

        # Generate edit
        new_content = qwen.edit_file(target_file, current, msg.body)

        # Commit
        commit_msg = f"🦅 {msg.body[:50]}"
        await github.commit_files(
            session.github_token,
            session.current_repo,
            session.current_branch,
            {target_file: new_content},
            commit_msg
        )

        session.files[target_file] = hash(new_content)

        # Screenshot updated state
        preview_url = session.last_preview_url or await vercel.get_preview_url(
            session.current_repo, session.current_branch
        )

        await wa.send_text(msg.from_number, "📸 Capturing updated preview...")
        img_path = await screenshot.capture(preview_url)

        caption = (f"🔄 Updated *{target_file}*\n"
                   f"🔗 {preview_url}\n\n"
                   f"Keep replying to iterate, or `screenshot` for fresh preview.")

        await wa.send_image(msg.from_number, img_path, caption=caption)

    except Exception as e:
        await wa.send_text(msg.from_number,
            f"❌ Edit failed: {str(e)[:200]}\nTry rephrasing or type `help`.")


async def handle_screenshot(session: UserSession, msg: WhatsAppMessage):
    """Force new screenshot."""
    if not session.last_preview_url:
        await wa.send_text(msg.from_number, "No active preview. Create a project first: `new ...`")
        return

    try:
        await wa.send_text(msg.from_number, "📸 Capturing...")
        img_path = await screenshot.capture(session.last_preview_url)

        caption = f"📸 Current preview\n🔗 {session.last_preview_url}"
        await wa.send_image(msg.from_number, img_path, caption=caption)
    except Exception as e:
        await wa.send_text(msg.from_number, f"❌ Screenshot failed: {str(e)[:200]}")


async def handle_list_files(session: UserSession, msg: WhatsAppMessage):
    """List project files."""
    if not session.current_repo:
        await wa.send_text(msg.from_number, "No active project.")
        return

    try:
        files = await github.list_files(
            session.github_token,
            session.current_repo,
            session.current_branch
        )

        file_list = []
        for f in files:
            icon = "📁" if f["type"] == "dir" else "📄"
            file_list.append(f"{icon} {f['path']}")

        text = "*Project files:*\n\n" + "\n".join(file_list[:50])
        text += "\n\nReply `show {filename}` to view contents."

        await wa.send_text(msg.from_number, text)
    except Exception as e:
        await wa.send_text(msg.from_number, f"❌ {str(e)[:200]}")


async def handle_show_file(session: UserSession, msg: WhatsAppMessage):
    """Show file contents."""
    if not session.current_repo:
        await wa.send_text(msg.from_number, "No active project.")
        return

    filename = msg.body[5:].strip()  # Remove "show "

    try:
        content = await github.get_file(
            session.github_token,
            session.current_repo,
            session.current_branch,
            filename
        )

        # Truncate if too long
        if len(content) > 3000:
            content = content[:3000] + "\n\n... (truncated)"

        text = f"📄 *{filename}*\n```\n{content}\n```"
        await wa.send_text(msg.from_number, text)
    except Exception as e:
        await wa.send_text(msg.from_number, f"❌ Couldn't read file: {str(e)[:200]}")


async def handle_push(session: UserSession, msg: WhatsAppMessage):
    """Commit current working tree."""
    await wa.send_text(msg.from_number,
        "✅ Changes are auto-committed on each edit. No manual push needed!")


async def handle_link_github(session: UserSession, msg: WhatsAppMessage):
    """Send GitHub App installation link."""
    # In production, implement OAuth callback flow
    # For MVP, manual token exchange

    text = ("🔗 *Connect GitHub*\n\n"
            "1. Install the Raptor-AI GitHub App:\n"
            "https://github.com/apps/raptor-ai/installations\n\n"
            "2. After installing, reply with your installation ID:\n"
            "`github {installation_id}`\n\n"
            "(Find it in the URL after installing)")

    await wa.send_text(msg.from_number, text)


# ───────────────────────────────────────────────
# GitHub OAuth Callback
# ───────────────────────────────────────────────

@app.get("/auth/github/callback")
async def github_callback(code: str, installation_id: str = None):
    """Handle GitHub App installation callback."""
    # Exchange code for token (OAuth flow)
    # In production: implement full OAuth
    return JSONResponse({
        "status": "success",
        "message": "GitHub connected! You can close this window and return to WhatsApp.",
        "installation_id": installation_id
    })


@app.post("/auth/github/webhook")
async def github_webhook(request: Request):
    """Handle GitHub App webhook events."""
    payload = await request.json()
    event = request.headers.get("X-GitHub-Event")

    if event == "installation" and payload.get("action") == "created":
        installation_id = payload["installation"]["id"]
        # Store installation_id for user (need to map to WA number)
        pass

    return PlainTextResponse("OK")


# ───────────────────────────────────────────────
# Health & Status
# ───────────────────────────────────────────────

@app.get("/")
async def root():
    return {"app": config.APP_NAME, "version": config.APP_VERSION, "status": "🦅 soaring"}

@app.get("/health")
async def health():
    return {"status": "healthy", "services": ["whatsapp", "qwen", "github", "vercel", "screenshot"]}
