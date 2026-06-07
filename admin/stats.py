import logging

from db.repository import get_stats, set_user_role

logger = logging.getLogger(__name__)


async def get_admin_stats_text() -> str:
    """
    Get formatted statistics text for admin.

    Returns:
        HTML formatted statistics string
    """
    stats = await get_stats()

    return (
        "📊 <b>Bot Statistics</b>\n\n"
        f"👥 <b>Users:</b>\n"
        f"  • Total: {stats['total_users']}\n"
        f"  • Authorized: {stats['active_users']}\n\n"
        f"💬 <b>Messages:</b>\n"
        f"  • Total: {stats['total_messages']}\n"
        f"  • User questions: {stats['user_questions']}\n\n"
        f"🌐 <b>Sites:</b>\n"
        f"  • Total saved: {stats['total_saved_sites']}\n"
        f"  • Active monitors: {stats['active_monitors']}\n"
    )


async def promote_user_to_admin(user_id: int) -> None:
    """Promote user to admin role."""
    await set_user_role(user_id=user_id, role="admin")
    logger.info(f"Promoted user {user_id} to admin")


async def demote_admin_to_user(user_id: int) -> None:
    """Demote admin to regular user role."""
    await set_user_role(user_id=user_id, role="user")
    logger.info(f"Demoted user {user_id} to regular user")