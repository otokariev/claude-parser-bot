import logging
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings
from db.models import Message, SavedSite, Session, SiteMonitor, User

import ssl

logger = logging.getLogger(__name__)

# Create SSL context for Neon cloud database
ssl_context = ssl.create_default_context()

# Create async engine and session factory
engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"ssl": ssl_context},
)
async_session = async_sessionmaker(engine, expire_on_commit=False)


# ── User Repository ───────────────────────────────────────────────────────────

async def get_or_create_user(
    user_id: int,
    username: str | None,
    full_name: str,
) -> User:
    """Get existing user or create a new one."""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                id=user_id,
                username=username,
                full_name=full_name,
                role="user",
                is_active=False,  # not authorized yet
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"Created new user: {user_id}")

        return user


async def is_user_authorized(user_id: int) -> bool:
    """Check if user is authorized (has entered correct password)."""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        return user is not None and user.is_active


async def authorize_user(user_id: int) -> None:
    """Mark user as authorized in the database."""
    async with async_session() as session:
        await session.execute(
            update(User).where(User.id == user_id).values(is_active=True)
        )
        await session.commit()
        logger.info(f"User authorized: {user_id}")


# ── SavedSite Repository ──────────────────────────────────────────────────────

async def save_site(user_id: int, url: str, title: str | None = None, summary: str | None = None) -> SavedSite:
    """Save a new site to user's favourites."""
    async with async_session() as session:
        # Check if site already saved
        result = await session.execute(
            select(SavedSite).where(
                SavedSite.user_id == user_id,
                SavedSite.url == url,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            return existing

        site = SavedSite(
            user_id=user_id,
            url=url,
            title=title,
            summary=summary,
        )
        session.add(site)
        await session.commit()
        await session.refresh(site)
        logger.info(f"Saved site {url} for user {user_id}")
        return site


async def get_user_sites(user_id: int) -> list[SavedSite]:
    """Get all saved sites for a user."""
    async with async_session() as session:
        result = await session.execute(
            select(SavedSite).where(SavedSite.user_id == user_id)
        )
        return list(result.scalars().all())


async def delete_site(site_id: int, user_id: int) -> bool:
    """Delete a saved site. Returns True if deleted, False if not found."""
    async with async_session() as session:
        result = await session.execute(
            select(SavedSite).where(
                SavedSite.id == site_id,
                SavedSite.user_id == user_id,
            )
        )
        site = result.scalar_one_or_none()

        if not site:
            return False

        await session.delete(site)
        await session.commit()
        logger.info(f"Deleted site {site_id} for user {user_id}")
        return True


async def get_site_by_id(site_id: int, user_id: int) -> SavedSite | None:
    """Get a saved site by ID."""
    async with async_session() as session:
        result = await session.execute(
            select(SavedSite).where(
                SavedSite.id == site_id,
                SavedSite.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()


# ── Message Repository ────────────────────────────────────────────────────────

async def save_message(
        user_id: int,
        role: str,
        content: str,
        session_id: int | None = None,
) -> Message:
    """
    Save a message to history.

    Args:
        user_id: Telegram user ID
        role: 'user' or 'assistant'
        content: Message content
        session_id: Optional session ID
    """
    async with async_session() as session:
        message = Message(
            user_id=user_id,
            role=role,
            content=content,
            session_id=session_id,
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
        return message


async def get_user_history(user_id: int, limit: int = 10) -> list[Message]:
    """
    Get last N messages for a user.

    Args:
        user_id: Telegram user ID
        limit: Maximum number of messages to return
    """
    async with async_session() as session:
        result = await session.execute(
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = list(result.scalars().all())
        return list(reversed(messages))


async def clear_user_history(user_id: int) -> None:
    """Delete all messages for a user."""
    async with async_session() as session:
        messages = await session.execute(
            select(Message).where(Message.user_id == user_id)
        )
        for message in messages.scalars().all():
            await session.delete(message)
        await session.commit()
        logger.info(f"Cleared history for user {user_id}")


# ── SiteMonitor Repository ────────────────────────────────────────────────────

async def create_monitor(saved_site_id: int, interval_hours: int = 24) -> SiteMonitor:
    """Create a new site monitor."""
    async with async_session() as session:
        monitor = SiteMonitor(
            saved_site_id=saved_site_id,
            interval_hours=interval_hours,
            is_active=True,
        )
        session.add(monitor)
        await session.commit()
        await session.refresh(monitor)
        logger.info(f"Created monitor for site {saved_site_id}")
        return monitor


async def get_active_monitors() -> list[SiteMonitor]:
    """Get all active site monitors."""
    async with async_session() as session:
        result = await session.execute(
            select(SiteMonitor).where(SiteMonitor.is_active == True)
        )
        return list(result.scalars().all())


async def update_monitor_check(
    monitor_id: int,
    content_hash: str,
) -> None:
    """Update monitor's last check time and content hash."""
    async with async_session() as session:
        await session.execute(
            update(SiteMonitor)
            .where(SiteMonitor.id == monitor_id)
            .values(
                last_checked_at=datetime.now(),
                last_content_hash=content_hash,
            )
        )
        await session.commit()


async def deactivate_monitor(monitor_id: int) -> None:
    """Deactivate a site monitor."""
    async with async_session() as session:
        await session.execute(
            update(SiteMonitor)
            .where(SiteMonitor.id == monitor_id)
            .values(is_active=False)
        )
        await session.commit()
        logger.info(f"Deactivated monitor {monitor_id}")


async def get_monitor_by_site(saved_site_id: int) -> SiteMonitor | None:
    """Get monitor for a specific saved site."""
    async with async_session() as session:
        result = await session.execute(
            select(SiteMonitor).where(
                SiteMonitor.saved_site_id == saved_site_id,
                SiteMonitor.is_active == True,
            )
        )
        return result.scalar_one_or_none()


# ── Admin Repository ──────────────────────────────────────────────────────────

async def get_all_users() -> list[User]:
    """Get all registered users."""
    async with async_session() as session:
        result = await session.execute(select(User))
        return list(result.scalars().all())


async def set_user_role(user_id: int, role: str) -> None:
    """Set user role — 'user' or 'admin'."""
    async with async_session() as session:
        await session.execute(
            update(User).where(User.id == user_id).values(role=role)
        )
        await session.commit()
        logger.info(f"Set role {role} for user {user_id}")


async def get_stats() -> dict:
    """Get bot usage statistics for admin."""
    async with async_session() as session:
        # Total users
        users_result = await session.execute(select(User))
        users = list(users_result.scalars().all())
        total_users = len(users)
        active_users = len([u for u in users if u.is_active])

        # Total messages
        messages_result = await session.execute(select(Message))
        messages = list(messages_result.scalars().all())
        total_messages = len(messages)
        user_messages = len([m for m in messages if m.role == "user"])

        # Total saved sites
        sites_result = await session.execute(select(SavedSite))
        total_sites = len(list(sites_result.scalars().all()))

        # Total monitors
        monitors_result = await session.execute(
            select(SiteMonitor).where(SiteMonitor.is_active == True)
        )
        total_monitors = len(list(monitors_result.scalars().all()))

        return {
            "total_users": total_users,
            "active_users": active_users,
            "total_messages": total_messages,
            "user_questions": user_messages,
            "total_saved_sites": total_sites,
            "active_monitors": total_monitors,
        }


# ── Subscription Repository ───────────────────────────────────────────────────

async def get_user_subscription(user_id: int) -> str:
    """Get user subscription type — 'free' or 'pro'."""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        return user.subscription if user else "free"


async def activate_pro_subscription(user_id: int, days: int = 30) -> None:
    """
    Activate Pro subscription for a user.

    Args:
        user_id: Telegram user ID
        days: Number of days to activate subscription for
    """
    until = datetime.now() + timedelta(days=days)
    async with async_session() as session:
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(subscription="pro", subscription_until=until)
        )
        await session.commit()
        logger.info(f"Activated Pro subscription for user {user_id} until {until}")


async def deactivate_pro_subscription(user_id: int) -> None:
    """Deactivate Pro subscription for a user."""
    async with async_session() as session:
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(subscription="free", subscription_until=None)
        )
        await session.commit()
        logger.info(f"Deactivated Pro subscription for user {user_id}")


async def check_subscription_expiry(user_id: int) -> bool:
    """
    Check if Pro subscription has expired and downgrade if needed.

    Returns:
        True if subscription is still active, False if expired
    """
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user or user.subscription == "free":
            return False

        if user.subscription_until and user.subscription_until < datetime.now():
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(subscription="free", subscription_until=None)
            )
            await session.commit()
            logger.info(f"Pro subscription expired for user {user_id}")
            return False

        return True