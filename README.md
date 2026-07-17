# vibe-coder-agent-test

Vibecode webapps through WhatsApp. Generate, edit, and deploy web applications using natural language — all from your phone.

## Architecture

```
WhatsApp → Twilio → FastAPI → Qwen 2.5-Coder → GitHub → Vercel → Screenshot → WhatsApp
```

## Project Structure

```text
vibe-coder-agent/
├── app/
│   ├── routers/        # FastAPI route handlers
│   │   ├── github.py   # GitHub OAuth & webhooks
│   │   ├── health.py   # Health checks
│   │   └── webhook.py  # Twilio WhatsApp entry & command handlers
│   ├── services/       # Core business logic & external APIs
│   │   ├── github.py
│   │   ├── qwen.py     # Planner, Architect, Coder, Reviewer, Tester agents
│   │   ├── screenshot.py
│   │   ├── vercel.py
│   │   └── whatsapp.py
│   ├── utils/          # Utilities
│   │   └── session.py  # Redis session management
│   ├── config.py       # Environment variables
│   ├── dependencies.py # Service singletons
│   ├── main.py         # App entry point
│   └── models.py       # Pydantic data models
├── prompts/            # System prompts for all Qwen agents
│   ├── system_edit_file.txt
│   ├── system_new_project.txt
│   ├── system_plan_architecture.txt
│   ├── system_plan_edit.txt
│   ├── system_plan_project.txt
│   ├── system_review_code.txt
│   └── system_test_code.txt
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Quick Start

### Prerequisites
- Python 3.11+
- Redis (or Upstash)
- Twilio account with WhatsApp sandbox
- GitHub App
- Vercel account
- Ollama (local) or DashScope API key
- Ngrok (for local webhook testing)

### 1. Clone & Install
```bash
cd vibe-coder-agent
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Start Services
```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Ollama (local Qwen)
ollama pull qwen2.5-coder:14b
ollama serve

# Terminal 3: App
uvicorn app.main:app --reload --port 8000

# Terminal 4: Ngrok for Twilio webhook
ngrok http 8000
```

### 4. Configure Webhooks & Base URL
1. Set your Twilio WhatsApp webhook URL to `https://your-ngrok-domain.ngrok-free.app/webhook`
2. Ensure your `.env` has `BASE_URL` set to this exact domain (e.g., `BASE_URL=https://your-ngrok-domain.ngrok-free.app`). This is strictly required for Twilio signature validation and WhatsApp image attachments.

## Usage

| Command | Description |
|---------|-------------|
| `new portfolio: landing page with dark mode` | Create new project |
| `make the button bigger` | Edit current project |
| `screenshot` | Get latest preview |
| `files` | List project files |
| `show app/page.tsx` | View file contents |
| `link github` | Connect GitHub account |

## Docker Deployment

```bash
docker-compose up --build
```

## GitHub App Setup

1. Go to GitHub → Settings → Developer settings → GitHub Apps → New
2. Fill in:
   - **Name**: vibe-coder-agent
   - **Homepage URL**: https://your-domain.com
   - **Callback URL**: https://your-domain.com/auth/github/callback *(Required for OAuth)*
   - **Webhook URL**: https://your-domain.com/auth/github/webhook
   - **Webhook secret**: Generate a random string
   - **Permissions**: 
     - **Administration** (Read & Write) — *Required to create new repositories*
     - **Contents** (Read & Write)
     - **Metadata** (Read-only)
   - **Subscribe to events**: Installation
3. Generate a private key and download the PEM file.
4. Generate a **Client Secret** on the app settings page.
5. Install the app on your account.
6. Copy the App ID, Client ID, Client Secret, Webhook Secret, and PEM contents to your `.env` file.

## License

MIT
