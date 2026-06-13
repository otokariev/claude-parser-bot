# Claude Parser Bot — Development Log

A Telegram bot powered by Claude that scrapes websites and answers questions based strictly on their content (RAG-based).

---

## Step 0 — Create GitHub Repository

- Created repository `claude-parser-bot` on GitHub (with README and Python `.gitignore`)
- Cloned locally via PyCharm terminal

---

## Step 1 — Project Structure, uv, pyproject.toml

- Installed `uv` package manager
- Ran `uv init`
- Created project structure:

```
claude-parser-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── handlers.py
│   └── keyboards.py
├── services/
│   ├── __init__.py
│   ├── scraper.py
│   ├── claude.py
│   ├── cache.py
│   ├── vector_store.py
│   ├── rag.py
│   ├── celery_app.py
│   ├── tasks.py
│   ├── retry.py
│   ├── rate_limiter.py
│   └── monitor.py
├── db/
│   ├── __init__.py
│   ├── models.py
│   └── repository.py
├── admin/
│   ├── __init__.py
│   └── stats.py
├── migrations/        (created by Alembic in Step 2)
├── alembic.ini
├── .env
├── pyproject.toml
└── README.md
```

- Installed core dependencies: `aiogram`, `python-dotenv`, `sqlalchemy`, `alembic`, `asyncpg`, `anthropic`, `firecrawl-py`, `qdrant-client`, `celery`, `redis`, `tenacity`

---

## Step 2 — PostgreSQL Models & Alembic Migrations

- Created SQLAlchemy 2.0 models in `db/models.py`: `User`, `Session`, `Message`, `SavedSite`, `SiteMonitor`
- Set up local PostgreSQL, Redis, Qdrant via `docker-compose.dev.yml`
- Initialized Alembic, created and applied initial migration

### Issues encountered & fixes:

1. **`uliweb-alembic` conflict** — an unrelated package conflicted with SQLAlchemy 2.0, causing `ImportError: cannot import name '_BindParamClause'`. Fixed by removing `uliweb-alembic` from `pyproject.toml` and recreating `.venv`.
2. **`alembic` command not found** — `.venv/bin/alembic` executable wasn't created properly. Fixed by running `uv run python -m alembic ...` instead of `uv run alembic ...`.
3. **Migrations ran but no tables created** — transaction wasn't committed in `migrations/env.py`. Fixed by adding a separate `do_run_migrations()` function with explicit `context.begin_transaction()`.
4. **Docker permission denied** — Docker daemon wasn't running / user lacked permissions. Fixed with `sudo systemctl start docker` and `sudo usermod -aG docker $USER` (required reboot).
5. **`docker compose` not found** — installed via `sudo dnf install docker-compose`.

---

## Step 3 — Basic Bot: /start, /help, Handlers, Keyboards

- Created Telegram bot via @BotFather
- Implemented `bot/main.py` with aiogram 3 polling setup
- Implemented `bot/keyboards.py` with main menu, sites, confirmation keyboards
- Implemented `bot/handlers.py` with FSM states: `waiting_for_url`, `waiting_for_question`, `waiting_for_clarification`
- Commands: `/start`, `/help`, and menu buttons (Add URL, My Sites, Ask Question, History, Settings, Help)
- Tested all buttons successfully

---

## Step 4 — Password Protection

**Reordered in plan**: originally step 30 in a template project, moved to Step 4 (right after basic bot, before any paid API integrations).

- Added `BOT_PASSWORD` to `.env` and `bot/config.py`
- Added `is_active` flag check in `db/repository.py`: `get_or_create_user`, `is_user_authorized`, `authorize_user`
- Added `waiting_for_password` FSM state
- Authorization stored in PostgreSQL (`users.is_active`) instead of `memory.json` — persists across restarts
- Fixed: Docker containers don't restart automatically after reboot — must run `docker compose -f docker-compose.dev.yml up -d` manually each session. Added `restart: always` to docker-compose for resilience (still requires first manual start after host reboot).

---

## Step 5 — Firecrawl Web Scraping

- Got Firecrawl API key, added to `.env`
- Implemented `services/scraper.py` with `scrape_url()` and `scrape_multiple_urls()`

### Issues encountered & fixes:

1. `FirecrawlApp` has no `scrape_url` method in v4 SDK — renamed to `scrape()`
2. `result.metadata` is an object, not a dict — used `.title` attribute instead of `.get("title")`
3. Updated `handle_url_input` in `bot/handlers.py` to call scraper and store content in FSM state

---

## Step 6 — Qdrant Vector Store & RAG Chunking

- Implemented `services/vector_store.py`: embeddings via `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim), Qdrant collection `site_chunks`
- Implemented `services/rag.py`: `split_text_into_chunks()` (1000 chars, 100 overlap), `index_site_content()`, `get_relevant_context()`

### Issues encountered & fixes:

1. `qdrant_client.search()` deprecated — replaced with `query_points()`
2. Required correct `Filter`/`FieldCondition`/`MatchValue` imports for filtering by `url` and `user_id`

---

## Step 7 — Claude RAG Integration

- Implemented `services/claude.py`: `ask_claude()` with strict "answer only from context" system prompt, `ask_claude_for_clarification()`
- Connected scraper → Qdrant → Claude → Telegram in `bot/handlers.py`
- Added clarification flow (`waiting_for_clarification` state) — **this also covers Step 16 (clarification questions)**, implemented early.

### Corrections:

1. `bot/main.py` — added `drop_pending_updates=True` and `allowed_updates` so the bot doesn't respond to stale messages on restart
2. Fixed model name `claude-sonnet-4-20250514` → `claude-sonnet-4-5`
3. Updated system prompt to use Telegram-supported HTML tags (`<b>`, `<i>`, `<code>`) instead of Markdown

---

## Step 8 — Redis Caching & FSM Storage

- Implemented `services/cache.py`: `get_cached_content()`, `set_cached_content()` (TTL 1 hour), `delete_cached_content()`, `is_url_cached()`
- Added `RedisStorage` for aiogram FSM state persistence (`bot/main.py`)
- Installed `aiogram[redis]`

---

## Step 9 — Celery Task Queue

- Implemented `services/celery_app.py` (Redis broker/backend) and `services/tasks.py` (`scrape_and_index_task`)
- Connected Celery task to `handle_url_input` via `.delay()` + `task.get()`

### Issues encountered & fixes:

1. `Cannot re-initialize CUDA in forked subprocess` — `sentence-transformers` + Celery's default fork pool conflict. Fixed by adding `worker_pool="solo"` to Celery config.

---

## Step 10 — Retry Mechanism

- Implemented `services/retry.py`: `with_retry()` decorator using `tenacity` (exponential backoff, max 3 attempts)
- Applied `@with_retry()` to `scrape_url()` in `services/scraper.py`
- Verified with standalone test script (3 attempts, exponential delay confirmed)

---

## Step 11 — Rate Limiting

- Implemented `services/rate_limiter.py`: `check_rate_limit()` — per-minute (10/min) and per-day limits via Redis counters with TTL
- Integrated into `handle_url_input` and `handle_question_input`
- Verified with temporarily lowered limits

---

## Step 12 — Saved Sites

- Added repository functions: `save_site()`, `get_user_sites()`, `delete_site()`, `get_site_by_id()`
- Updated `handle_my_sites` to load from DB, added site selection/delete callbacks
- Added `sites_keyboard()` and `site_actions_keyboard()`

### Corrections:

1. Fixed `UnboundLocalError` for `user_id` in `handle_question_input` — moved `user_id = message.from_user.id` to top of function
2. Sites loaded from cache weren't being saved to DB — added `save_site()` call in the cache-hit branch too

---

## Step 13 — Question History

- Added `save_message()`, `get_user_history()`, `clear_user_history()` to `db/repository.py`
- Updated `handle_history` to display last 10 Q&A pairs from DB
- Save Q&A pairs after every Claude response

---

## Step 14 — Site Monitoring (Celery Beat)

- Added `SiteMonitor` repository functions: `create_monitor()`, `get_active_monitors()`, `update_monitor_check()`, `deactivate_monitor()`, `get_monitor_by_site()`
- Implemented `services/monitor.py`: `compute_content_hash()`, `has_content_changed()`, `check_site_for_changes()`
- Added `check_monitors_task` (Celery Beat) — checks all active monitors

### Corrections:

1. Fixed schedule mismatch — text said "24 hours" but `beat_schedule` was set to 1 hour (3600s); corrected to 86400s (24h)
2. Local Celery requires `PYTHONPATH=.` prefix: `PYTHONPATH=. uv run celery -A services.celery_app worker --loglevel=info`

---

## Step 15 — Multi-Site Mode

- Added `multi_site_keyboard()` for managing multiple active URLs
- Added `waiting_for_more_urls` FSM state and handlers: add/remove URL, "done adding URLs"
- Updated `handle_question_input` to search across all active URLs and combine contexts with source attribution

### Corrections:

1. `handle_clarification_input` only searched `current_url`, not `current_urls` — fixed to support multi-site search after clarification too

---

## Step 16 — Clarification Questions

**Already implemented in Step 7** (combined for efficiency). Formal commit added for devlog tracking.

---

## Step 17 — Auto-Summary

- Added `generate_site_summary()` to `services/claude.py`
- `scrape_and_index_task` now generates a summary alongside scraping
- Summary displayed after successful scrape, saved to `SavedSite.summary`

### Corrections:

1. Initial summary prompt used unsupported `<p>` HTML tag → Telegram `TelegramBadRequest`. Restricted to `<b>`, `<i>`, `<code>` only.

---

## Step 18 — Multilingual Responses

**Already implemented in Step 7** via system prompt instruction "Respond in the same language the user asked the question in". Verified working with a Russian-language question. Formal commit added for devlog tracking.

---

## Step 19 — Admin Panel, Roles & Statistics

- Added repository functions: `get_all_users()`, `set_user_role()`, `get_stats()`
- Implemented `admin/stats.py`: `get_admin_stats_text()`, `promote_user_to_admin()`, `demote_admin_to_user()`
- Added admin-only commands: `/admin`, `/promote`, `/demote`, `/users`
- Manually set first admin via direct SQL: `UPDATE users SET role='admin' WHERE id=...`

### Notes:

- `/admin` initially conflicted with `waiting_for_question` FSM state — resolved in Step 20 via regex filter
- Admin commands intentionally have no dedicated keyboard (standard practice for single-admin bots)

---

## Step 20 — Subscriptions & Telegram Stars

- Added `subscription` and `subscription_until` fields to `User` model + migration
- Added repository functions: `get_user_subscription()`, `activate_pro_subscription()`, `deactivate_pro_subscription()`, `check_subscription_expiry()`
- Updated `services/rate_limiter.py`: Free plan = **2 requests/day**, Pro = unlimited (only per-minute limit applies)
- Added `/subscribe` command, `pay_stars` callback, `pre_checkout_query` handler, `successful_payment` handler (Telegram Stars, 50 XTR / 30 days)
- Added `subscribe_keyboard()` to `bot/keyboards.py`

### Issues encountered & fixes:

1. New `subscription`/`subscription_until` fields were accidentally added outside the `User` class in `models.py` — caused Alembic to target the wrong table (`site_monitors`). Fixed by moving fields inside `User`, regenerating migration.
2. `NOT NULL` constraint violation on existing rows when adding `subscription` column — fixed by adding `server_default='free'` to the migration.
3. FSM state `waiting_for_question` intercepted commands like `/subscribe` as questions. Fixed by adding filter `F.text.regexp(r"^(?!\/).*")` to relevant message handlers so commands bypass FSM states entirely.
4. Refactored inline `InlineKeyboardMarkup` construction out of `handlers.py` into `subscribe_keyboard()` in `bot/keyboards.py`.

---

## Step 21 — Deploy Preparation (Neon + Upstash + Qdrant Cloud)

- **Neon (PostgreSQL)**: created project, region US East (Virginia, default). Updated `DATABASE_URL`.
- **Upstash (Redis)**: created database with eviction enabled, region US-East-1. Updated `REDIS_URL` (`rediss://`).
- **Qdrant Cloud**: created cluster, region Frankfurt (AWS eu-central-1). Updated `QDRANT_HOST`, `QDRANT_API_KEY`.
- Created `render.yaml` (initial draft — later revised in Step 24)

### Issues encountered & fixes:

1. `sslmode` param incompatible with `asyncpg` — replaced with explicit `ssl.create_default_context()` passed via `connect_args={"ssl": ssl_context}` in `db/repository.py`
2. `alembic.ini` still pointed to local Postgres — updated `sqlalchemy.url` to Neon connection string, then re-ran `downgrade base` + `upgrade head` to create tables in Neon
3. Celery + Upstash `rediss://` required explicit SSL config: added `broker_use_ssl`/`redis_backend_use_ssl` with `ssl_cert_reqs: "none"` in `services/celery_app.py`
4. `services/cache.py` and `services/rate_limiter.py` Redis clients needed `ssl_cert_reqs=None` for Upstash
5. `services/vector_store.py` updated to pass `api_key` and `https=True` to `QdrantClient` for Qdrant Cloud

All three cloud services verified working locally before deploy.

---

## Step 22 — Celery in Background Thread (Free Tier Constraint)

- Render free tier doesn't support separate Worker services without a paid plan
- Refactored `bot/main.py`: Celery worker now runs in a background `threading.Thread` within the same process as the bot
- Simplified `render.yaml` to a single service

---

## Step 23 — Webhook Mode for Render

- Replaced polling with **webhook** mode for production (more efficient, required for Render's port-binding requirement on free Web Services)
- Added `aiohttp` web server with `/health` endpoint for Render health checks and UptimeRobot
- Added `WEBHOOK_URL` setting to `bot/config.py`
- `bot/main.py` runs in webhook mode only — sets its own webhook on startup via `on_startup`, runs the aiohttp server, and starts Celery in a background thread

### Note:

This should have been part of the original architecture from the start — webhook deployment is standard practice for production Telegram bots on platforms like Render. A `USE_WEBHOOK` polling/webhook switch was initially considered for local development, but not implemented — the bot runs in webhook mode only. For local testing, a tunneling tool like ngrok is required to expose a public URL to Telegram.

---

## Step 24 — Deployment to Render

### Attempt 1: Celery `task.get()` deadlock

- `task.get()` inside the same process as the Celery worker caused `Never call result.get() within a task!`
- Fixed by calling `scrape_and_index_task(...)` directly (synchronously) instead of `.delay()` + `.get()`

### Attempt 2: Memory limit (512MB)

- `sentence-transformers` + default `torch` (with CUDA, ~700MB) + full stack exceeded Render's 512MB free tier → `Out of memory`
- Also caused `Port scan timeout` due to ~3 min bytecode compilation of `torch`/`transformers` (14,000+ files)

### Attempt 3: Voyage AI embeddings — **FAILED**

- Replaced `sentence-transformers` with Voyage AI API (`voyage-multilingual-2`, 1024-dim) to eliminate local ML dependencies
- Result: **`HTTP code 403 from API`** on every embedding request, despite valid API key (regenerated key twice, issue persisted — likely regional restriction or account verification issue)
- Abandoned this approach

### Attempt 4: fastembed (CPU-only ONNX) — **SUCCESS** ✅

- Replaced Voyage AI with `fastembed` (ONNX-based, model `BAAI/bge-small-en-v1.5`, 384-dim)
- `.venv` size reduced from ~5.2GB (torch+CUDA) to ~150-200MB
- Recreated Qdrant collection with correct vector size (384)
- Added required Qdrant payload indexes: `url` (keyword), `user_id` (integer) — Qdrant Cloud requires explicit indexes for filtered queries
- **Deployment successful** — bot live at `https://claude-parser-bot.onrender.com`, within 512MB free tier

### Final stack on Render:

- Single Web Service (free tier)
- Webhook mode + Celery worker in background thread + health check endpoint
- Neon (PostgreSQL), Upstash (Redis), Qdrant Cloud — all free tiers
- fastembed for local embeddings (no external embedding API)

---

## Project Status: ✅ COMPLETE

All 24 steps (0–24) implemented, tested, and deployed to production on Render's free tier.
