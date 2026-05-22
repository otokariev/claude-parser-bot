from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Main menu keyboard with primary commands."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🌐 Add URL"),
                KeyboardButton(text="📋 My Sites"),
            ],
            [
                KeyboardButton(text="❓ Ask Question"),
                KeyboardButton(text="📜 History"),
            ],
            [
                KeyboardButton(text="⚙️ Settings"),
                KeyboardButton(text="ℹ️ Help"),
            ],
        ],
        resize_keyboard=True,
        persistent=True,
    )
    return keyboard


def sites_keyboard(sites: list[dict]) -> InlineKeyboardMarkup:
    """Inline keyboard with user's saved sites."""
    buttons = []
    for site in sites:
        buttons.append(
            [InlineKeyboardButton(text=f"🌐 {site['title'] or site['url']}", callback_data=f"site_{site['id']}")]
        )
    buttons.append(
        [InlineKeyboardButton(text="➕ Add new site", callback_data="add_site")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def site_actions_keyboard(site_id: int) -> InlineKeyboardMarkup:
    """Inline keyboard with actions for a specific site."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❓ Ask Question", callback_data=f"ask_{site_id}"),
                InlineKeyboardButton(text="📋 Summary", callback_data=f"summary_{site_id}"),
            ],
            [
                InlineKeyboardButton(text="🔔 Monitor", callback_data=f"monitor_{site_id}"),
                InlineKeyboardButton(text="🗑 Delete", callback_data=f"delete_{site_id}"),
            ],
            [
                InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_sites"),
            ],
        ]
    )
    return keyboard


def confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    """Inline keyboard for confirmation dialogs."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Confirm", callback_data=f"confirm_{action}"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="cancel"),
            ]
        ]
    )
    return keyboard


def back_keyboard() -> InlineKeyboardMarkup:
    """Simple back button keyboard."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_sites")]
        ]
    )
    return keyboard


def multi_site_keyboard(urls: list[str]) -> InlineKeyboardMarkup:
    """Inline keyboard showing active URLs in multi-site mode."""
    buttons = []
    for i, url in enumerate(urls):
        short_url = url.replace("https://", "").replace("http://", "")[:30]
        buttons.append(
            [InlineKeyboardButton(
                text=f"❌ {short_url}",
                callback_data=f"remove_url_{i}",
            )]
        )
    buttons.append(
        [InlineKeyboardButton(text="➕ Add another URL", callback_data="add_more_url")]
    )
    buttons.append(
        [InlineKeyboardButton(text="✅ Done, ask question", callback_data="done_adding_urls")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)