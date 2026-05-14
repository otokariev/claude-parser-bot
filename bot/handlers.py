import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.keyboards import (
    back_keyboard,
    confirm_keyboard,
    main_menu_keyboard,
    site_actions_keyboard,
    sites_keyboard,
)

logger = logging.getLogger(__name__)

# Router instance for registering handlers
router = Router()


class BotStates(StatesGroup):
    """FSM states for conversation flow."""

    waiting_for_url = State()        # waiting for user to send a URL
    waiting_for_question = State()   # waiting for user to send a question
    waiting_for_clarification = State()  # waiting for clarification from user


# ── Command Handlers ──────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Handle /start command — greet user and show main menu."""
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
async def cmd_help(message: Message) -> None:
    """Handle /help command — show usage instructions."""
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


# ── Menu Button Handlers ──────────────────────────────────────────────────────

@router.message(F.text == "🌐 Add URL")
async def handle_add_url(message: Message, state: FSMContext) -> None:
    """Handle Add URL button — ask user for a URL."""
    await state.set_state(BotStates.waiting_for_url)
    await message.answer(
        "🌐 Send me a website URL to parse.\n\n"
        "Example: <code>https://example.com</code>",
    )


@router.message(F.text == "📋 My Sites")
async def handle_my_sites(message: Message) -> None:
    """Handle My Sites button — show saved sites (placeholder)."""
    # TODO: load sites from database in Step 11
    await message.answer(
        "📋 <b>Your saved sites:</b>\n\n"
        "No sites saved yet. Press <b>Add URL</b> to add one!",
    )


@router.message(F.text == "❓ Ask Question")
async def handle_ask_question(message: Message, state: FSMContext) -> None:
    """Handle Ask Question button — ask user for a question."""
    await state.set_state(BotStates.waiting_for_question)
    await message.answer(
        "❓ What would you like to know?\n\n"
        "Send me your question and I will search for the answer on the site.",
    )


@router.message(F.text == "📜 History")
async def handle_history(message: Message) -> None:
    """Handle History button — show question history (placeholder)."""
    # TODO: load history from database in Step 12
    await message.answer(
        "📜 <b>Your question history:</b>\n\n"
        "No questions asked yet.",
    )


@router.message(F.text == "⚙️ Settings")
async def handle_settings(message: Message) -> None:
    """Handle Settings button — show settings (placeholder)."""
    # TODO: implement settings in later steps
    await message.answer(
        "⚙️ <b>Settings</b>\n\n"
        "Settings will be available soon.",
    )


# ── URL Input Handler ─────────────────────────────────────────────────────────

@router.message(BotStates.waiting_for_url)
async def handle_url_input(message: Message, state: FSMContext) -> None:
    """Handle URL input from user — validate and save to state."""
    url = message.text.strip()

    # Basic URL validation
    if not url.startswith(("http://", "https://")):
        await message.answer(
            "❌ Invalid URL. Please send a valid URL starting with "
            "<code>http://</code> or <code>https://</code>",
        )
        return

    # Save URL to FSM state
    await state.update_data(current_url=url)
    await state.set_state(BotStates.waiting_for_question)

    await message.answer(
        f"✅ URL saved: <code>{url}</code>\n\n"
        "Now send me your question about this site!",
    )


# ── Question Input Handler ────────────────────────────────────────────────────

@router.message(BotStates.waiting_for_question)
async def handle_question_input(message: Message, state: FSMContext) -> None:
    """Handle question input from user — placeholder for Claude response."""
    data = await state.get_data()
    url = data.get("current_url")

    if not url:
        await state.set_state(BotStates.waiting_for_url)
        await message.answer(
            "⚠️ No URL set. Please send a URL first.",
        )
        return

    question = message.text.strip()

    # TODO: call scraper + Claude in Steps 4-6
    await message.answer(
        f"🔍 Searching on <code>{url}</code>...\n\n"
        f"Question: <i>{question}</i>\n\n"
        "⏳ This feature will be available after Steps 4-6.",
    )


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