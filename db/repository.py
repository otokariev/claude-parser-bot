import logging
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings
from db.models import Message, SavedSite, Session, SiteMonitor, User

logger = logging.getLogger(__name__)

# Create async engine and session factory
engine = create_async_engine(settings.database_url, echo=False)
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