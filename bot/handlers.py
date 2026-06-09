import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, LabeledPrice, PreCheckoutQuery

from bot.config import settings
from bot.keyboards import (
    confirm_keyboard,
    main_menu_keyboard,
    site_actions_keyboard,
    sites_keyboard,
    multi_site_keyboard,
    subscribe_keyboard,
)

from db.repository import authorize_user, get_or_create_user, is_user_authorized
from db.repository import save_site, get_user_sites, delete_site, get_site_by_id
from db.repository import save_message, get_user_history
from db.repository import create_monitor, get_monitor_by_site, deactivate_monitor
from db.repository import get_all_users, set_user_role
from db.repository import get_user_subscription, activate_pro_subscription, check_subscription_expiry

from services.claude import ask_claude, ask_claude_for_clarification
from services.rag import index_site_content, get_relevant_context
from services.cache import get_cached_content, set_cached_content
from services.tasks import scrape_and_index_task
from services.rate_limiter import check_rate_limit

from admin.stats import get_admin_stats_text, promote_user_to_admin

logger = logging.getLogger(__name__)

# Router instance for registering handlers
router = Router()


class BotStates(StatesGroup):
    """FSM states for conversation flow."""

    waiting_for_password = State()  # waiting for user to enter password
    waiting_for_url = State()  # waiting for user to send a URL
    waiting_for_more_urls = State()  # waiting for additional URLs in multi-site mode
    waiting_for_question = State()  # waiting for user to send a question
    waiting_for_clarification = State()  # waiting for clarification from user


# ── Authorization middleware ──────────────────────────────────────────────────

async def check_authorization(message: Message, state: FSMContext) -> bool:
    """Check if user is authorized. If not — ask for password. Returns True if authorized."""
    user_id = message.from_user.id
    authorized = await is_user_authorized(user_id)

    if not authorized:
        await state.set_state(BotStates.waiting_for_password)
        await message.answer(
            "🔒 This bot is password protected.\n\n"
            "Please enter the password to continue:",
        )
        return False
    return True


# ── Command Handlers ──────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Handle /start command — register user and check authorization."""
    await get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    authorized = await check_authorization(message, state)
    if not authorized:
        return

    await state.clear()
    await message.answer(
        f"👋 Hello, <b>{message.from_user.full_name}</b>!\n\n"
        "I am <b>Claude Parser Bot</b> — I can parse any website and answer "
        "your questions based on its content.\n\n"
        "📌 <b>How to use:</b>\n"
        "1. Send me a URL of any website\n"
        "2. Ask me any question about it\n"
        "3. I will find the answer from that site only\n\n"
        "Press <b>Add URL</b> to get started!",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("help"))
@router.message(F.text == "ℹ️ Help")
async def cmd_help(message: Message, state: FSMContext) -> None:
    """Handle /help command — show usage instructions."""
    if not await check_authorization(message, state):
        return

    await message.answer(
        "ℹ️ <b>How Claude Parser Bot works:</b>\n\n"
        "🌐 <b>Add URL</b> — add a website to parse\n"
        "📋 <b>My Sites</b> — view your saved sites\n"
        "❓ <b>Ask Question</b> — ask about the active site\n"
        "📜 <b>History</b> — view your question history\n"
        "⚙️ <b>Settings</b> — manage your preferences\n\n"
        "💡 <b>Tips:</b>\n"
        "• You can add multiple URLs at once\n"
        "• Bot answers only based on the site content\n"
        "• Use /start to reset the session",
    )


# ── Password Handler ──────────────────────────────────────────────────────────

@router.message(BotStates.waiting_for_password)
async def handle_password(message: Message, state: FSMContext) -> None:
    """Handle password input — authorize user if correct."""
    if message.text.strip() == settings.bot_password:
        await authorize_user(message.from_user.id)
        await state.clear()
        await message.answer(
            "✅ Password correct! Welcome!\n\n"
            f"👋 Hello, <b>{message.from_user.full_name}</b>!",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await message.answer(
            "❌ Wrong password. Please try again:",
        )


# ── Menu Button Handlers ──────────────────────────────────────────────────────

@router.message(F.text == "🌐 Add URL")
async def handle_add_url(message: Message, state: FSMContext) -> None:
    """Handle Add URL button — ask user for a URL."""
    if not await check_authorization(message, state):
        return

    await state.set_state(BotStates.waiting_for_url)
    await message.answer(
        "🌐 Send me a website URL to parse.\n\n"
        "Example: <code>https://example.com</code>",
    )


@router.message(F.text == "📋 My Sites")
async def handle_my_sites(message: Message, state: FSMContext) -> None:
    """Handle My Sites button — show saved sites from database."""
    if not await check_authorization(message, state):
        return

    user_id = message.from_user.id
    sites = await get_user_sites(user_id)

    if not sites:
        await message.answer(
            "📋 <b>Your saved sites:</b>\n\n"
            "No sites saved yet. Press <b>Add URL</b> to add one!",
        )
        return

    sites_list = [{"id": s.id, "title": s.title, "url": s.url} for s in sites]
    await message.answer(
        "📋 <b>Your saved sites:</b>",
        reply_markup=sites_keyboard(sites_list),
    )


@router.message(F.text == "❓ Ask Question")
async def handle_ask_question(message: Message, state: FSMContext) -> None:
    """Handle Ask Question button — ask user for a question."""
    if not await check_authorization(message, state):
        return

    await state.set_state(BotStates.waiting_for_question)
    await message.answer(
        "❓ What would you like to know?\n\n"
        "Send me your question and I will search for the answer on the site.",
    )


@router.message(F.text == "📜 History")
async def handle_history(message: Message, state: FSMContext) -> None:
    """Handle History button — show question history from database."""
    if not await check_authorization(message, state):
        return

    user_id = message.from_user.id
    messages = await get_user_history(user_id=user_id, limit=10)

    if not messages:
        await message.answer(
            "📜 <b>Your question history:</b>\n\n"
            "No questions asked yet.",
        )
        return

    history_text = "📜 <b>Your last questions:</b>\n\n"
    for msg in messages:
        if msg.role == "user":
            history_text += f"❓ <b>Q:</b> {msg.content}\n"
        else:
            history_text += f"🤖 <b>A:</b> {msg.content[:200]}...\n\n"

    await message.answer(history_text)


@router.message(F.text == "⚙️ Settings")
async def handle_settings(message: Message, state: FSMContext) -> None:
    """Handle Settings button — show settings (placeholder)."""
    if not await check_authorization(message, state):
        return

    # TODO: implement settings in later steps
    await message.answer(
        "⚙️ <b>Settings</b>\n\n"
        "Settings will be available soon.",
    )


# ── URL Input Handler ─────────────────────────────────────────────────────────

@router.message(BotStates.waiting_for_url)
async def handle_url_input(message: Message, state: FSMContext) -> None:
    """Handle URL input — check cache, scrape and optionally add more URLs."""
    url = message.text.strip()
    user_id = message.from_user.id

    # Basic URL validation
    if not url.startswith(("http://", "https://")):
        await message.answer(
            "❌ Invalid URL. Please send a valid URL starting with "
            "<code>http://</code> or <code>https://</code>",
        )
        return

    # Check rate limit
    subscription = await get_user_subscription(user_id)
    await check_subscription_expiry(user_id)
    allowed, error_message = await check_rate_limit(user_id, subscription=subscription)
    if not allowed:
        await message.answer(error_message)
        return

    # Check cache first
    cached = await get_cached_content(url=url, user_id=user_id)

    if cached:
        await state.update_data(
            current_url=url,
            current_urls=[url],
            current_title=cached["title"],
            current_content=cached["content"],
        )
        await state.set_state(BotStates.waiting_for_question)

        await save_site(user_id=user_id, url=url, title=cached["title"])

        await message.answer(
            f"⚡ Loaded from cache!\n\n"
            f"🌐 <b>{cached['title'] or url}</b>\n\n"
            "Now send me your question or add more URLs:",
            reply_markup=multi_site_keyboard([url]),
        )
        return

    # Send scraping task to Celery worker
    await state.update_data(current_url=url, current_urls=[url])

    status_message = await message.answer(
        "⏳ Site is being scraped in the background...",
    )

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: scrape_and_index_task(url=url, user_id=user_id)
        )

        if not result["success"]:
            await status_message.edit_text(
                f"❌ Failed to scrape <code>{url}</code>\n\n"
                f"Error: {result['error']}",
            )
            return

        await set_cached_content(
            url=url,
            user_id=user_id,
            title=result["title"],
            content=result["content"],
        )

        await save_site(
            user_id=user_id,
            url=url,
            title=result["title"],
            summary=result.get("summary"),
        )

        await state.update_data(
            current_title=result["title"],
            current_content=result["content"],
        )

        summary_text = f"\n\n📝 <b>Summary:</b>\n{result['summary']}" if result.get("summary") else ""

        await status_message.edit_text(
            f"✅ Site scraped and saved!\n\n"
            f"🌐 <b>{result['title'] or url}</b>\n"
            f"📄 Chunks indexed: {result['chunks_count']}"
            f"{summary_text}\n\n"
            "Now send me your question or add more URLs:",
            reply_markup=multi_site_keyboard([url]),
        )

    except Exception as e:
        await status_message.edit_text(
            f"❌ Scraping timed out or failed: {str(e)}",
        )


# ── Question Input Handler ────────────────────────────────────────────────────

@router.message(BotStates.waiting_for_question, F.text.regexp(r"^(?!\/).*"))
async def handle_question_input(message: Message, state: FSMContext) -> None:
    """Handle question input — search across single or multiple sites."""

    data = await state.get_data()
    url = data.get("current_url")
    urls = data.get("current_urls", [])
    user_id = message.from_user.id

    if not url and not urls:
        await state.set_state(BotStates.waiting_for_url)
        await message.answer(
            "⚠️ No URL set. Please send a URL first.",
        )
        return

    # Check rate limit
    subscription = await get_user_subscription(user_id)
    await check_subscription_expiry(user_id)
    allowed, error_message = await check_rate_limit(user_id, subscription=subscription)
    if not allowed:
        await message.answer(error_message)
        return

    question = message.text.strip()

    # Use multi-site mode if multiple URLs
    active_urls = urls if urls else [url]

    # Check if question needs clarification
    clarification = ask_claude_for_clarification(question=question, url=active_urls[0])
    if clarification:
        await state.set_state(BotStates.waiting_for_clarification)
        await state.update_data(pending_question=question)
        await message.answer(
            f"🤔 Could you clarify your question?\n\n{clarification}",
        )
        return

    status_message = await message.answer("🔍 Searching for relevant information...")

    # Index content if available in state
    content = data.get("current_content")
    if content:
        index_site_content(url=active_urls[0], user_id=user_id, content=content)
        await state.update_data(current_content=None)

    # Search across all URLs
    all_contexts = []
    for search_url in active_urls:
        context = get_relevant_context(query=question, url=search_url, user_id=user_id)
        if context:
            all_contexts.append(f"Source: {search_url}\n{context}")

    if not all_contexts:
        await status_message.edit_text(
            "❌ No relevant information found on the site(s) for your question.",
        )
        return

    # Combine contexts from all sites
    combined_context = "\n\n===\n\n".join(all_contexts)
    sources = ", ".join(active_urls)

    await status_message.edit_text("🤖 Claude is thinking...")
    answer = ask_claude(question=question, context=combined_context, url=sources)

    await status_message.edit_text(
        f"💬 <b>Question:</b> {question}\n\n"
        f"🤖 <b>Answer:</b>\n{answer}\n\n"
        f"🌐 <i>Sources: {sources}</i>",
    )

    # Save question and answer to history
    await save_message(user_id=user_id, role="user", content=question)
    await save_message(user_id=user_id, role="assistant", content=answer)


# ── Clarification Input Handler ────────────────────────────────────────────────────

@router.message(BotStates.waiting_for_clarification)
async def handle_clarification_input(message: Message, state: FSMContext) -> None:
    """Handle clarification input — combine with original question and answer."""
    data = await state.get_data()
    url = data.get("current_url")
    urls = data.get("current_urls", [])
    original_question = data.get("pending_question", "")
    clarification = message.text.strip()
    user_id = message.from_user.id

    # Combine original question with clarification
    refined_question = f"{original_question} — {clarification}"

    # Use multi-site mode if multiple URLs
    active_urls = urls if urls else [url]

    status_message = await message.answer("🔍 Searching for relevant information...")

    # Search across all URLs
    all_contexts = []
    for search_url in active_urls:
        context = get_relevant_context(query=refined_question, url=search_url, user_id=user_id)
        if context:
            all_contexts.append(f"Source: {search_url}\n{context}")

    if not all_contexts:
        await status_message.edit_text(
            "❌ No relevant information found on the site(s) for your question.",
        )
        await state.set_state(BotStates.waiting_for_question)
        return

    sources = ", ".join(active_urls)
    combined_context = "\n\n===\n\n".join(all_contexts)

    await status_message.edit_text("🤖 Claude is thinking...")
    answer = ask_claude(question=refined_question, context=combined_context, url=sources)

    await status_message.edit_text(
        f"💬 <b>Question:</b> {refined_question}\n\n"
        f"🤖 <b>Answer:</b>\n{answer}\n\n"
        f"🌐 <i>Sources: {sources}</i>",
    )

    await save_message(user_id=user_id, role="user", content=refined_question)
    await save_message(user_id=user_id, role="assistant", content=answer)

    await state.set_state(BotStates.waiting_for_question)


# ── Callback Query Handlers ───────────────────────────────────────────────────

@router.callback_query(F.data == "add_site")
async def callback_add_site(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle add site callback."""
    await state.set_state(BotStates.waiting_for_url)
    await callback.message.answer(
        "🌐 Send me a website URL to parse.",
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_sites")
async def callback_back_to_sites(callback: CallbackQuery) -> None:
    """Handle back to sites callback."""
    user_id = callback.from_user.id
    sites = await get_user_sites(user_id)
    sites_list = [{"id": s.id, "title": s.title, "url": s.url} for s in sites]

    await callback.message.answer(
        "📋 <b>Your saved sites:</b>",
        reply_markup=sites_keyboard(sites_list),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("site_"))
async def callback_site_selected(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle site selection from My Sites list."""
    site_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    site = await get_site_by_id(site_id=site_id, user_id=user_id)
    if not site:
        await callback.answer("Site not found.")
        return

    await state.update_data(current_url=site.url, current_title=site.title)
    await state.set_state(BotStates.waiting_for_question)

    await callback.message.answer(
        f"🌐 <b>{site.title or site.url}</b>\n\n"
        "Send me your question about this site!",
        reply_markup=site_actions_keyboard(site_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_"))
async def callback_delete_site(callback: CallbackQuery) -> None:
    """Handle site deletion."""
    site_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    await callback.message.answer(
        "🗑 Are you sure you want to delete this site?",
        reply_markup=confirm_keyboard(f"delete_{site_id}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete_"))
async def callback_confirm_delete(callback: CallbackQuery) -> None:
    """Handle delete confirmation."""
    site_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id

    deleted = await delete_site(site_id=site_id, user_id=user_id)

    if deleted:
        await callback.message.answer("✅ Site deleted successfully!")
    else:
        await callback.message.answer("❌ Site not found.")

    await callback.answer()


@router.callback_query(F.data.startswith("monitor_"))
async def callback_monitor_site(callback: CallbackQuery) -> None:
    """Handle monitor button — toggle site monitoring."""
    site_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    # Check if monitor already exists
    existing_monitor = await get_monitor_by_site(saved_site_id=site_id)

    if existing_monitor:
        # Deactivate existing monitor
        await deactivate_monitor(monitor_id=existing_monitor.id)
        await callback.message.answer(
            "🔕 Monitoring disabled for this site.",
        )
    else:
        # Create new monitor with default 24h interval
        await create_monitor(saved_site_id=site_id, interval_hours=24)
        await callback.message.answer(
            "🔔 Monitoring enabled!\n\n"
            "I will check this site every <b>24 hours</b> and notify you if content changes.",
        )

    await callback.answer()


@router.callback_query(F.data.startswith("ask_"))
async def callback_ask_about_site(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle ask button from site actions keyboard."""
    site_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    site = await get_site_by_id(site_id=site_id, user_id=user_id)
    if not site:
        await callback.answer("Site not found.")
        return

    await state.update_data(current_url=site.url, current_title=site.title)
    await state.set_state(BotStates.waiting_for_question)

    await callback.message.answer(
        f"❓ Ask your question about <b>{site.title or site.url}</b>:",
    )
    await callback.answer()


@router.callback_query(F.data == "add_more_url")
async def callback_add_more_url(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle add more URL button in multi-site mode."""
    await state.set_state(BotStates.waiting_for_more_urls)
    await callback.message.answer(
        "🌐 Send me another URL to add:",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remove_url_"))
async def callback_remove_url(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle remove URL button in multi-site mode."""
    index = int(callback.data.split("_")[2])
    data = await state.get_data()
    urls = data.get("current_urls", [])

    if index < len(urls):
        removed = urls.pop(index)
        await state.update_data(current_urls=urls)
        await callback.message.answer(
            f"❌ Removed: <code>{removed}</code>\n\n"
            f"Active URLs: {len(urls)}",
            reply_markup=multi_site_keyboard(urls) if urls else None,
        )
    await callback.answer()


@router.callback_query(F.data == "done_adding_urls")
async def callback_done_adding_urls(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle done adding URLs — switch to question mode."""
    data = await state.get_data()
    urls = data.get("current_urls", [])

    if not urls:
        await callback.message.answer("⚠️ No URLs added. Please add at least one URL.")
        await callback.answer()
        return

    await state.set_state(BotStates.waiting_for_question)
    await callback.message.answer(
        f"✅ <b>{len(urls)} sites ready!</b>\n\n"
        "Now send me your question — I will search across all sites.",
    )
    await callback.answer()


@router.message(BotStates.waiting_for_more_urls)
async def handle_more_url_input(message: Message, state: FSMContext) -> None:
    """Handle additional URL input in multi-site mode."""
    url = message.text.strip()
    user_id = message.from_user.id

    if not url.startswith(("http://", "https://")):
        await message.answer(
            "❌ Invalid URL. Please send a valid URL starting with "
            "<code>http://</code> or <code>https://</code>",
        )
        return

    data = await state.get_data()
    urls = data.get("current_urls", [])

    if url in urls:
        await message.answer("⚠️ This URL is already added.")
        return

    # Scrape and index new URL
    status_message = await message.answer(f"⏳ Scraping <code>{url}</code>...")

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: scrape_and_index_task(url=url, user_id=user_id)
        )

        if not result["success"]:
            await status_message.edit_text(
                f"❌ Failed to scrape <code>{url}</code>\n\n"
                f"Error: {result['error']}",
            )
            return

        urls.append(url)
        await state.update_data(current_urls=urls)

        await set_cached_content(
            url=url,
            user_id=user_id,
            title=result["title"],
            content=result["content"],
        )

        await save_site(user_id=user_id, url=url, title=result["title"])

        await status_message.edit_text(
            f"✅ Added: <b>{result['title'] or url}</b>\n\n"
            f"Total URLs: {len(urls)}",
            reply_markup=multi_site_keyboard(urls),
        )

    except Exception as e:
        await status_message.edit_text(
            f"❌ Failed: {str(e)}",
        )

        
# ── Admin Handlers ────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    """Handle /admin command — show admin panel (admin only)."""
    user = await get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    if user.role != "admin":
        await message.answer("❌ Access denied.")
        return

    stats_text = await get_admin_stats_text()
    await message.answer(
        f"👑 <b>Admin Panel</b>\n\n{stats_text}\n\n"
        "Commands:\n"
        "/promote [user_id] — promote user to admin\n"
        "/demote [user_id] — demote admin to user\n"
        "/users — list all users",
    )


@router.message(Command("promote"))
async def cmd_promote(message: Message) -> None:
    """Handle /promote command — promote user to admin (admin only)."""
    user = await get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    if user.role != "admin":
        await message.answer("❌ Access denied.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /promote [user_id]")
        return

    target_id = int(args[1])
    await promote_user_to_admin(user_id=target_id)
    await message.answer(f"✅ User {target_id} promoted to admin.")


@router.message(Command("demote"))
async def cmd_demote(message: Message) -> None:
    """Handle /demote command — demote admin to user (admin only)."""
    user = await get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    if user.role != "admin":
        await message.answer("❌ Access denied.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: /demote [user_id]")
        return

    target_id = int(args[1])
    await set_user_role(user_id=target_id, role="user")
    await message.answer(f"✅ User {target_id} demoted to regular user.")


@router.message(Command("users"))
async def cmd_users(message: Message) -> None:
    """Handle /users command — list all users (admin only)."""
    user = await get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    if user.role != "admin":
        await message.answer("❌ Access denied.")
        return

    users = await get_all_users()

    if not users:
        await message.answer("No users found.")
        return

    users_text = "👥 <b>All users:</b>\n\n"
    for u in users:
        status = "✅" if u.is_active else "❌"
        role_icon = "👑" if u.role == "admin" else "👤"
        users_text += f"{status} {role_icon} <b>{u.full_name}</b> (@{u.username}) — ID: <code>{u.id}</code>\n"

    await message.answer(users_text)


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message) -> None:
    """Handle /subscribe command — show subscription options."""
    user_id = message.from_user.id
    subscription = await get_user_subscription(user_id)

    if subscription == "pro":
        is_active = await check_subscription_expiry(user_id)
        if is_active:
            await message.answer(
                "✅ You already have <b>Pro</b> subscription!\n\n"
                "Enjoy unlimited requests.",
            )
            return

    await message.answer(
        "⭐ <b>Upgrade to Pro</b>\n\n"
        "Free plan: <b>2 requests/day</b>\n"
        "Pro plan: <b>Unlimited requests</b>\n\n"
        "Price: <b>50 Telegram Stars</b> / month\n\n"
        "Press the button below to subscribe:",
        reply_markup=subscribe_keyboard()
    )


@router.callback_query(F.data == "pay_stars")
async def callback_pay_stars(callback: CallbackQuery) -> None:
    """Handle pay stars button — send invoice."""
    await callback.message.answer_invoice(
        title="Pro Subscription",
        description="Unlimited requests for 30 days",
        payload="pro_subscription_30days",
        currency="XTR",  # Telegram Stars currency code
        prices=[LabeledPrice(label="Pro Subscription", amount=50)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery) -> None:
    """Handle pre-checkout query — always approve."""
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message) -> None:
    """Handle successful payment — activate Pro subscription."""
    user_id = message.from_user.id
    await activate_pro_subscription(user_id=user_id, days=30)
    await message.answer(
        "🎉 <b>Payment successful!</b>\n\n"
        "Your <b>Pro</b> subscription is now active for <b>30 days</b>.\n\n"
        "Enjoy unlimited requests!",
    )


@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle cancel callback — clear state."""
    await state.clear()
    await callback.message.answer(
        "❌ Cancelled.",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()