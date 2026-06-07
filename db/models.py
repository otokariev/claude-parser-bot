from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class User(Base):
    """Telegram user model."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user ID
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="user")  # "user" or "admin"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_requests: Mapped[int] = mapped_column(Integer, default=0)
    last_request_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    subscription: Mapped[str] = mapped_column(String(16), default="free")  # "free" or "pro"
    subscription_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sessions: Mapped[list["Session"]] = relationship(back_populates="user")
    saved_sites: Mapped[list["SavedSite"]] = relationship(back_populates="user")
    messages: Mapped[list["Message"]] = relationship(back_populates="user")


class Session(Base):
    """User session — tracks active URLs and context."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    urls: Mapped[str] = mapped_column(Text)  # JSON list of URLs
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(back_populates="session")


class Message(Base):
    """Chat message history."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    session_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sessions.id"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(16))  # "user" or "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="messages")
    session: Mapped["Session"] = relationship(back_populates="messages")


class SavedSite(Base):
    """User's saved/favourite websites."""

    __tablename__ = "saved_sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)  # auto-summary title
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # auto-summary content
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="saved_sites")
    monitor: Mapped["SiteMonitor | None"] = relationship(back_populates="saved_site")


class SiteMonitor(Base):
    """Site monitoring subscription."""

    __tablename__ = "site_monitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    saved_site_id: Mapped[int] = mapped_column(Integer, ForeignKey("saved_sites.id"))
    interval_hours: Mapped[int] = mapped_column(Integer, default=24)  # check interval
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # to detect changes
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    saved_site: Mapped["SavedSite"] = relationship(back_populates="monitor")