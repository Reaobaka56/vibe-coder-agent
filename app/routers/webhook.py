import re
import uuid
from fastapi import APIRouter, Request, HTTPException, status, Response
from fastapi.responses import PlainTextResponse
from app.models import UserSession, WhatsAppMessage
from app.dependencies import wa, qwen, github, vercel, screenshot, sessions
from app.utils import db
from twilio.request_validator import RequestValidator
from app.config import config
from app.utils.wa import normalise_wa
import hashlib
import asyncio
import datetime

router = APIRouter()

@router.post("/webhook")
async def webhook(request: Request):
    """Handle incoming WhatsApp messages from Twilio."""
    # Twilio signature validation
    validator = RequestValidator(config.TWILIO_TOKEN)
    signature = request.headers.get("X-Twilio-Signature", "")
    
    form = await request.form()
    
    # Twilio sends delivery/status callbacks to the same URL.
    # These have MessageStatus/SmsStatus set or match our own sender number — bail early to avoid loops.
    from_raw = form.get("From", "")
    if (
        form.get("MessageStatus")
        or form.get("SmsStatus")
        or (from_raw and normalise_wa(from_raw) == normalise_wa(config.TWILIO_WHATSAPP_NUMBER))
    ):
        return Response(status_code=200)

    form_dict = {k: v for k, v in form.items()}
    
    # Validate signature (checking both raw URL and configured BASE_URL for ngrok support)
    url = str(request.url)
    if not validator.validate(url, form_dict, signature):
        constructed_url = f"{config.BASE_URL.rstrip('/')}{request.url.path}"
        if request.url.query:
            constructed_url += f"?{request.url.query}"
            
        if not validator.validate(constructed_url, form_dict, signature):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Twilio signature")

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
    
    # Ensure user exists in database
    await db.upsert_user(msg.from_number)

    # Route by intent
    body_lower = msg.body.lower().strip()
    
    # === AUTH GATE ===
    # Admin token commands
    if msg.from_number in config.ADMIN_WA_NUMBERS:
        if body_lower.startswith("gen token"):
            parts = msg.body.strip().split()[2:] # Skip 'gen' and 'token'
            bound_number = None
            expiry = None
            label_parts = []
            
            for part in parts:
                if part.startswith('+') or part.isdigit():
                    bound_number = normalise_wa(part)
                elif part.endswith('h') and part[:-1].replace('.', '', 1).isdigit():
                    expiry = float(part[:-1])
                else:
                    label_parts.append(part)
            
            label = " ".join(label_parts) if label_parts else None

            token = await db.create_access_token(
                msg.from_number, 
                bound_wa_number=bound_number, 
                expires_in_hours=expiry, 
                label=label
            )
            
            if token:
                response = f"🔑 New access token: {token}"
                if bound_number: response += f"\nBound to: {bound_number}"
                if expiry: response += f"\nExpires in: {expiry}h"
                if label: response += f"\nLabel: {label}"
                await wa.send_text(msg.from_number, response)
            else:
                await wa.send_text(msg.from_number, "❌ Failed to generate token. Check DATABASE_URL env var.")
            await sessions.save(session)
            return PlainTextResponse("OK")
            
        elif body_lower == "tokens":
            tokens = await db.list_access_tokens()
            if not tokens:
                await wa.send_text(msg.from_number, "No tokens found.")
            else:
                lines = ["*Access Tokens:*"]
                for t in tokens:
                    status = "🟢 Open"
                    if t["used_by"]: 
                        status = f"🔴 Used by {t['used_by']}"
                    elif t["revoked"]: 
                        status = "⚫ Revoked"
                    elif t["expires_at"] and t["expires_at"] < datetime.datetime.now(datetime.timezone.utc):
                        status = "🟡 Expired"
                    
                    line = f"`{t['token']}` - {status}"
                    if t["bound_wa_number"]: line += f" (Bound: {t['bound_wa_number']})"
                    if t["label"]: line += f" [{t['label']}]"
                    lines.append(line)
                    
                await wa.send_text(msg.from_number, "\n".join(lines))
            await sessions.save(session)
            return PlainTextResponse("OK")
            
        elif body_lower.startswith("revoke "):
            token_to_revoke = msg.body[7:].strip()
            ok = await db.revoke_access_token(token_to_revoke)
            await wa.send_text(msg.from_number, f"✅ Token {token_to_revoke} revoked." if ok else "❌ Failed to revoke token (not found).")
            await sessions.save(session)
            return PlainTextResponse("OK")
    
    # Token activation command
    if body_lower.startswith("activate "):
        token = msg.body[9:].strip()
        ok = await db.redeem_access_token(token, msg.from_number)
        await wa.send_text(msg.from_number, "✅ Access granted." if ok else "❌ Invalid or used token.")
        await sessions.save(session)
        return PlainTextResponse("OK")
    
    # Access control: if access tokens are required and user is not admin or verified
    if config.REQUIRE_ACCESS_TOKEN and msg.from_number not in config.ADMIN_WA_NUMBERS:
        is_verified = await db.is_verified(msg.from_number)
        if not is_verified:
            await wa.send_text(msg.from_number, "🔒 Access required. Reply `activate <token>` to unlock.")
            return PlainTextResponse("OK")

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


async def handle_help(session: UserSession, msg: WhatsAppMessage):
    """Send help message."""
    help_text = """🦅 *Vibe-Coder-Agent* — Vibecode webapps via WhatsApp

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
    text = msg.body[4:].strip()  # Remove "new "

    if ":" in text:
        parts = text.split(":", 1)
        project_name = parts[0].strip().replace(" ", "-").lower()
        description = parts[1].strip()
    else:
        project_name = text.replace(" ", "-").lower()[:30]
        description = text

    project_name = re.sub(r'[^a-z0-9-]', '', project_name)
    if not project_name:
        project_name = f"project-{uuid.uuid4().hex[:6]}"

    project_count = await db.count_projects(msg.from_number)
    if project_count >= config.MAX_PROJECTS_PER_NUMBER:
        await wa.send_text(
            msg.from_number,
            f"🚫 You already have {config.MAX_PROJECTS_PER_NUMBER} projects. Delete one before creating another.",
        )
        return

    if not session.github_token:
        await wa.send_text(msg.from_number, 
            "🔗 *Link GitHub first!*\n"
            "Visit: https://github.com/apps/vibe-coder-agent/installations\n"
            "Then reply `link github`")
        return

    await wa.send_text(msg.from_number, f"🚀 Generating *{project_name}*...")

    try:
        # Plan with Planner Agent
        await wa.send_text(msg.from_number, "🧠 Planning project requirements...")
        plan = await asyncio.to_thread(qwen.plan_project, description)
        session.project_memory = plan.get("project_memory", {})
        plan_desc = plan.get("plan_description", description)

        # Plan with Architect Agent
        await wa.send_text(msg.from_number, "🏗️ Designing architecture and file tree...")
        arch_plan = await asyncio.to_thread(qwen.plan_architecture, plan_desc, session.project_memory)

        # Generate code with Qwen
        await wa.send_text(msg.from_number, "💻 Writing code...")
        files = await asyncio.to_thread(qwen.generate_project, plan_desc, arch_plan, session.project_memory, session.project_type)

        if not files:
            await wa.send_text(msg.from_number, 
                "❌ Failed to generate code. Try again with a clearer description.")
            return

        # Test code with Tester Agent
        await wa.send_text(msg.from_number, "🧪 Testing codebase...")
        files = await asyncio.to_thread(qwen.test_code, files, plan_desc)

        # Create GitHub repo
        await wa.send_text(msg.from_number, "📁 Creating GitHub repo...")
        repo_full_name = await github.create_repo(
            session.github_token, 
            project_name, 
            description
        )

        await db.create_project(msg.from_number, project_name, repo_full_name)

        session.current_repo = repo_full_name
        session.current_branch = "main"
        session.files = {k: hashlib.sha256(v.encode()).hexdigest() for k, v in files.items()}

        # Push to GitHub
        await wa.send_text(msg.from_number, "📤 Pushing code to GitHub...")
        await github.commit_files(
            session.github_token,
            repo_full_name,
            "main",
            files,
            f"🦅 Vibe-Coder-Agent initial commit: {description[:50]}"
        )

        # Deploy to Vercel
        await wa.send_text(msg.from_number, "🌐 Deploying to Vercel...")
        repo_id = await github.get_repo_id(session.github_token, repo_full_name)
        preview_url = await vercel.deploy_repo(repo_full_name, project_name, "main", repo_id)
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

    project = await db.get_active_project(msg.from_number, session.current_repo)
    if project and project["edit_count"] >= config.MAX_EDITS_PER_PROJECT:
        await wa.send_text(
            msg.from_number,
            f"🚫 Edit limit reached ({config.MAX_EDITS_PER_PROJECT} edits) for this project.",
        )
        return

    await wa.send_text(msg.from_number, "🧠 Understanding your edit...")

    try:
        # Plan the edit
        await wa.send_text(msg.from_number, "🧠 Planning changes...")
        plan = await asyncio.to_thread(qwen.plan_edit, msg.body, session.files, session.project_memory, msg.media_url)
        files_to_edit = plan.get("files_to_edit", [])

        if not files_to_edit:
            await wa.send_text(msg.from_number, "No file changes needed based on instruction.")
            return

        updated_files = {}
        for file_plan in files_to_edit:
            target_file = file_plan.get("filename")
            instruction = file_plan.get("instruction", msg.body)

            if not target_file:
                continue

            # Get current content
            current = ""
            if target_file in session.files:
                try:
                    current = await github.get_file(
                        session.github_token,
                        session.current_repo,
                        session.current_branch,
                        target_file
                    )
                except Exception:
                    pass # Keep as empty string

            await wa.send_text(msg.from_number, f"✏️ Editing *{target_file}*...")

            # Generate edit (Coder)
            new_content = await asyncio.to_thread(qwen.edit_file, target_file, current, instruction, session.project_memory)

            # Review code (Reviewer)
            await wa.send_text(msg.from_number, f"🔍 Reviewing *{target_file}*...")
            reviewed_content = await asyncio.to_thread(qwen.review_code, target_file, current, new_content, instruction)

            updated_files[target_file] = reviewed_content
            session.files[target_file] = hashlib.sha256(reviewed_content.encode()).hexdigest()

        if not updated_files:
            return

        # Commit all changed files
        commit_msg = f"🦅 {msg.body[:50]}"
        await wa.send_text(msg.from_number, "📤 Committing changes...")
        await github.commit_files(
            session.github_token,
            session.current_repo,
            session.current_branch,
            updated_files,
            commit_msg
        )
        if project:
            await db.increment_edit_count(project["id"])

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
    """Send GitHub App installation link and OAuth login link."""
    login_url = f"{config.BASE_URL}/auth/github/login?wa_number={normalise_wa(msg.from_number)}"
    
    text = ("🔗 *Connect GitHub*\n\n"
            "1. Install the Vibe-Coder-Agent GitHub App:\n"
            "https://github.com/apps/vibe-coder-agent/installations\n\n"
            "2. After installing, authorize the app to link your account:\n"
            f"{login_url}")

    await wa.send_text(msg.from_number, text)
