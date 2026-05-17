import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.keyboards import (
    back_keyboard,
    confirm_keyboard,
    main_menu_keyboard,
    site_actions_keyboard,
    sites_keyboard,
)
from db.repository import authorize_user, get_or_create_user, is_user_authorized

from services.scraper import scrape_url
from services.claude import ask_claude, ask_claude_for_clarification
from services.rag import index_site_content, get_relevant_context
from services.cache import get_cached_content, set_cached_content
from services.tasks import scrape_and_index_task
from services.rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)

# Router instance for registering handlers
router = Router()


class BotStates(StatesGroup):
    """FSM states for conversation flow."""

    waiting_for_password = State()       # waiting for user to enter password
    waiting_for_url = State()            # waiting for user to send a URL
    waiting_for_question = State()       # waiting for user to send a question
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
    """Handle My Sites button — show saved sites (placeholder)."""
    if not await check_authorization(message, state):
        return

    # TODO: load sites from database in Step 12
    await message.answer(
        "📋 <b>Your saved sites:</b>\n\n"
        "No sites saved yet. Press <b>Add URL</b> to add one!",
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
    """Handle History button — show question history (placeholder)."""
    if not await check_authorization(message, state):
        return

    # TODO: load history from database in Step 13
    await message.answer(
        "📜 <b>Your question history:</b>\n\n"
        "No questions asked yet.",
    )


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
    """Handle URL input — check cache, then send scraping task to Celery."""
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
    allowed, error_message = await check_rate_limit(user_id)
    if not allowed:
        await message.answer(error_message)
        return

    # Check cache first
    cached = await get_cached_content(url=url, user_id=user_id)

    if cached:
        await state.update_data(
            current_url=url,
            current_title=cached["title"],
            current_content=cached["content"],
        )
        await state.set_state(BotStates.waiting_for_question)
        await message.answer(
            f"⚡ Loaded from cache!\n\n"
            f"🌐 <b>{cached['title'] or url}</b>\n\n"
            "Now send me your question about this site!",
        )
        return

    # Send scraping task to Celery worker
    await state.update_data(current_url=url)
    await state.set_state(BotStates.waiting_for_question)

    status_message = await message.answer(
        "⏳ Site is being scraped in the background...\n\n"
        "You will be notified when it's ready. "
        "You can ask your question now and I will answer once scraping is complete."
    )

    # Run task asynchronously
    task = scrape_and_index_task.delay(url=url, user_id=user_id)

    # Wait for task result (with timeout)
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: task.get(timeout=30)
        )

        if not result["success"]:
            await status_message.edit_text(
                f"❌ Failed to scrape <code>{url}</code>\n\n"
                f"Error: {result['error']}",
            )
            return

        # Save to cache
        await set_cached_content(
            url=url,
            user_id=user_id,
            title=result["title"],
            content=result["content"],
        )

        # Save content to FSM state
        await state.update_data(
            current_title=result["title"],
            current_content=result["content"],
        )

        await status_message.edit_text(
            f"✅ Site scraped successfully!\n\n"
            f"🌐 <b>{result['title'] or url}</b>\n"
            f"📄 Chunks indexed: {result['chunks_count']}\n\n"
            "Now send me your question about this site!",
        )

    except Exception as e:
        await status_message.edit_text(
            f"❌ Scraping timed out or failed: {str(e)}",
        )


# ── Question Input Handler ────────────────────────────────────────────────────

@router.message(BotStates.waiting_for_question)
async def handle_question_input(message: Message, state: FSMContext) -> None:
    """Handle question input — scrape, index, search and answer via Claude."""
    data = await state.get_data()
    url = data.get("current_url")

    if not url:
        await state.set_state(BotStates.waiting_for_url)
        await message.answer(
            "⚠️ No URL set. Please send a URL first.",
        )
        return

    # Check rate limit
    allowed, error_message = await check_rate_limit(user_id)
    if not allowed:
        await message.answer(error_message)
        return

    question = message.text.strip()
    user_id = message.from_user.id

    # Step 1: Check if question needs clarification
    clarification = ask_claude_for_clarification(question=question, url=url)
    if clarification:
        await state.set_state(BotStates.waiting_for_clarification)
        await state.update_data(pending_question=question)
        await message.answer(
            f"🤔 Could you clarify your question?\n\n{clarification}",
        )
        return

    # Step 2: Get content from state
    content = data.get("current_content")

    # Step 3: Index content if not already indexed
    if content:
        status_message = await message.answer("🔍 Searching for relevant information...")
        index_site_content(url=url, user_id=user_id, content=content)
        await state.update_data(current_content=None)  # clear content from state
    else:
        status_message = await message.answer("🔍 Searching for relevant information...")

    # Step 4: Search for relevant chunks
    context = get_relevant_context(query=question, url=url, user_id=user_id)

    if not context:
        await status_message.edit_text(
            "❌ No relevant information found on the site for your question.",
        )
        return

    # Step 5: Get answer from Claude
    await status_message.edit_text("🤖 Claude is thinking...")
    answer = ask_claude(question=question, context=context, url=url)

    await status_message.edit_text(
        f"💬 <b>Question:</b> {question}\n\n"
        f"🤖 <b>Answer:</b>\n{answer}\n\n"
        f"🌐 <i>Source: {url}</i>",
    )


# ── Clarification Input Handler ────────────────────────────────────────────────────

@router.message(BotStates.waiting_for_clarification)
async def handle_clarification_input(message: Message, state: FSMContext) -> None:
    """Handle clarification input — combine with original question and answer."""
    data = await state.get_data()
    url = data.get("current_url")
    original_question = data.get("pending_question", "")
    clarification = message.text.strip()
    user_id = message.from_user.id

    # Combine original question with clarification
    refined_question = f"{original_question} — {clarification}"

    status_message = await message.answer("🔍 Searching for relevant information...")

    # Search for relevant chunks
    context = get_relevant_context(query=refined_question, url=url, user_id=user_id)

    if not context:
        await status_message.edit_text(
            "❌ No relevant information found on the site for your question.",
        )
        await state.set_state(BotStates.waiting_for_question)
        return

    # Get answer from Claude
    await status_message.edit_text("🤖 Claude is thinking...")
    answer = ask_claude(question=refined_question, context=context, url=url)

    await status_message.edit_text(
        f"💬 <b>Question:</b> {refined_question}\n\n"
        f"🤖 <b>Answer:</b>\n{answer}\n\n"
        f"🌐 <i>Source: {url}</i>",
    )
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
    await callback.message.answer(
        "📋 Your saved sites:",
    )
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle cancel callback — clear state."""
    await state.clear()
    await callback.message.answer(
        "❌ Cancelled.",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()