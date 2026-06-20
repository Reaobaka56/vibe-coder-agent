# 🦅 Raptor-AI

Vibecode webapps through WhatsApp. Generate, edit, and deploy web applications using natural language — all from your phone.

## Architecture

```
WhatsApp → Twilio → FastAPI → Qwen 2.5-Coder → GitHub → Vercel → Screenshot → WhatsApp
```

## Quick Start

### Prerequisites
- Python 3.11+
- Redis (or Upstash)
- Twilio account with WhatsApp sandbox
- GitHub App
- Vercel account
- Ollama (local) or DashScope API key

### 1. Clone & Install
```bash
cd raptor-ai
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

### 4. Configure Twilio Webhook
Set your Twilio WhatsApp webhook URL to `https://your-ngrok.ngrok.io/webhook`

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
   - **Name**: raptor-ai
   - **Homepage URL**: https://your-domain.com
   - **Webhook URL**: https://your-domain.com/auth/github/webhook
   - **Webhook secret**: Generate random string
   - **Permissions**: Contents (Read/Write), Metadata (Read)
   - **Subscribe to events**: Installation
3. Generate private key, download PEM
4. Install app on your account
5. Copy App ID and PEM to `.env`

## License

MIT
