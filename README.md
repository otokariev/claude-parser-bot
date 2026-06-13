# Claude Parser Bot

A Telegram bot powered by the Anthropic Claude API that scrapes any website and answers questions based **strictly on that site's content** (RAG-based). Give it a URL, ask a question, and it searches only within that site — no external knowledge, no hallucinations.

---

## What the bot can do

| Command / Button | Description |
|---|---|
| `/start` | Register, authorize (password), show main menu |
| `/help` | Show usage instructions |
| `/admin` | Admin panel with bot statistics (admin only) |
| `/promote [user_id]` | Promote a user to admin (admin only) |
| `/demote [user_id]` | Demote an admin to regular user (admin only) |
| `/users` | List all registered users (admin only) |
| `/subscribe` | View subscription plans and pay with Telegram Stars |
| 🌐 Add URL | Scrape a website and start asking questions |
| 📋 My Sites | View, ask, summarize, monitor or delete saved sites |
| ❓ Ask Question | Ask a question about the active site(s) |
| 📜 History | View your last questions and answers |
| ⚙️ Settings | Bot settings |

---

## Key features

- **RAG-based answers** — Claude answers only from scraped website content (no hallucinations)
- **Multi-site mode** — add multiple URLs and search across all of them at once
- **Auto-summary** — every scraped site gets a short AI-generated summary
- **Clarification questions** — Claude asks for clarification on vague questions before searching
- **Multilingual** — responds in the same language as the question
- **Site monitoring** — subscribe to a site and get notified when its content changes (checked daily via Celery Beat)
- **Caching** — Redis cache avoids re-scraping the same URL within an hour
- **Rate limiting** — Free plan: 2 requests/day, Pro: unlimited (via Telegram Stars subscription)
- **Admin panel** — roles, user list, usage statistics
- **Password protection** — single shared password, stored per-user in the database

---

## Tech stack

- **Python 3.12**
- **aiogram 3** — Telegram bot framework (webhook mode)
- **anthropic** — Claude API (`claude-sonnet-4-5`)
- **firecrawl-py** — website scraping (returns clean Markdown)
- **fastembed** — local text embeddings (ONNX, no GPU/API required)
- **qdrant-client** — vector database for RAG search
- **SQLAlchemy + Alembic** — PostgreSQL ORM and migrations
- **Celery** — background task queue (scraping, indexing, monitoring)
- **Redis** — cache + Celery broker/backend + FSM storage
- **aiohttp** — webhook server + health check endpoint
- **uv** — package manager
- **Render** — hosting

---

## Project architecture

```
claude-parser-bot/
├── bot/
│   ├── main.py            # entry point (webhook + polling modes, Celery thread)
│   ├── config.py           # settings from environment variables
│   ├── handlers.py         # all Telegram command/message handlers
│   └── keyboards.py        # reply and inline keyboards
│
├── services/
│   ├── scraper.py          # Firecrawl integration
│   ├── claude.py           # Claude API: answers, clarification, summaries
│   ├── cache.py             # Redis caching for scraped content
│   ├── vector_store.py     # Qdrant + fastembed embeddings
│   ├── rag.py               # text chunking + retrieval
│   ├── celery_app.py        # Celery configuration
│   ├── tasks.py             # background tasks (scrape, index, monitor)
│   ├── retry.py             # retry decorator with exponential backoff
│   ├── rate_limiter.py     # per-minute and per-day rate limits
│   └── monitor.py           # site change detection
│
├── db/
│   ├── models.py            # SQLAlchemy models
│   └── repository.py        # database queries
│
├── admin/
│   └── stats.py              # admin statistics
│
├── migrations/               # Alembic migrations
├── docker-compose.dev.yml    # local Postgres + Redis + Qdrant
├── alembic.ini
├── .env
├── pyproject.toml
└── render.yaml
```

---

## Getting started locally

You can run this project against either **local services (Docker)** or **cloud services (free tiers)**. Both work the same in code — only `.env` values differ.

### 1. Clone the repository

```bash
git clone https://github.com/your-username/claude-parser-bot.git
cd claude-parser-bot
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Set up databases — choose one option

#### Option A: Local (Docker)

Start PostgreSQL, Redis and Qdrant locally:

```bash
docker compose -f docker-compose.dev.yml up -d
```

Use these values in `.env`:

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/claude_parser_bot
REDIS_URL=redis://localhost:6379/0
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=
```

#### Option B: Cloud (free tiers, no Docker needed)

- **PostgreSQL** → [Neon](https://neon.tech) — create a project, copy the connection string
- **Redis** → [Upstash](https://upstash.com) — create a database, copy the `rediss://` URL
- **Qdrant** → [Qdrant Cloud](https://cloud.qdrant.io) — create a cluster, copy the endpoint and API key

```
DATABASE_URL=postgresql+asyncpg://user:password@host.neon.tech/dbname
REDIS_URL=rediss://default:password@host.upstash.io:6379
QDRANT_HOST=your-cluster.cloud.qdrant.io
QDRANT_PORT=6333
QDRANT_API_KEY=your_qdrant_api_key
```

### 4. Create `.env` file

```
# Telegram
BOT_TOKEN=your_telegram_bot_token
BOT_PASSWORD=your_password

# Anthropic
ANTHROPIC_API_KEY=your_anthropic_api_key

# Firecrawl
FIRECRAWL_API_KEY=your_firecrawl_api_key

# Database / Cache / Vector store (see step 3 above)
DATABASE_URL=...
REDIS_URL=...
QDRANT_HOST=...
QDRANT_PORT=6333
QDRANT_API_KEY=...

# Webhook (leave empty for local development)
WEBHOOK_URL=https://your-ngrok-or-render-url
```

### 5. Apply database migrations

```bash
uv run python -m alembic upgrade head
```

### 6. Run the bot

This bot always runs in webhook mode. For local testing, Telegram needs a public HTTPS URL to send updates to — use a tool like [ngrok](https://ngrok.com) to expose your local port:

```bash
ngrok http 10000
```

Set `WEBHOOK_URL` in `.env` to the ngrok URL (e.g. `https://xxxx.ngrok-free.app`), then run:

```bash
uv run python -m bot.main
```

Celery runs in a background thread automatically.

Alternatively, skip local testing entirely and test against your deployed Render instance.

---

## Deploying to Render

**1.** Push your code to GitHub.

**2.** Go to [render.com](https://render.com) → **New** → **Web Service** → connect your repository.

**3.** Configure the service:
- **Build Command:** `uv sync --frozen && uv cache prune --ci`
- **Start Command:** `uv run python -m bot.main`
- **Instance Type:** Free
- **Health Check Path:** `/health`

**4.** Add environment variables — use **cloud** values for `DATABASE_URL`, `REDIS_URL`, `QDRANT_*` (Neon / Upstash / Qdrant Cloud), plus:
```
BOT_TOKEN=...
BOT_PASSWORD=...
ANTHROPIC_API_KEY=...
FIRECRAWL_API_KEY=...
WEBHOOK_URL=https://your-service.onrender.com
```

**5.** Deploy and wait for the service to go live. The bot automatically sets its own webhook on startup.

**6.** Set up [UptimeRobot](https://uptimerobot.com) to ping `https://your-service.onrender.com/health` every 5 minutes — prevents the free tier from sleeping.

---

## Environment variables reference

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `BOT_PASSWORD` | Shared password required to use the bot |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `FIRECRAWL_API_KEY` | Firecrawl API key |
| `DATABASE_URL` | PostgreSQL connection string (async, `postgresql+asyncpg://`) |
| `REDIS_URL` | Redis connection string (`redis://` or `rediss://`) |
| `QDRANT_HOST` | Qdrant host (without `https://`) |
| `QDRANT_PORT` | Qdrant port (default `6333`) |
| `QDRANT_API_KEY` | Qdrant Cloud API key (empty for local Docker) |
| `WEBHOOK_URL` | Public HTTPS URL (Render or ngrok) where Telegram sends updates |

---

## Notes on memory & free-tier constraints

This project runs the Celery worker **in a background thread** inside the same process as the bot, and uses **fastembed** (ONNX-based, ~150-200MB) instead of `sentence-transformers`+`torch` (~1.2GB) for embeddings. This keeps the entire stack within Render's 512MB free tier RAM limit.
