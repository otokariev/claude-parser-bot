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