import logging

import redis.asyncio as aioredis

from bot.config import settings

logger = logging.getLogger(__name__)

# Initialize async Redis client
redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

# Rate limit settings
MAX_REQUESTS_PER_MINUTE = 10  # max requests per user per minute
MAX_REQUESTS_PER_DAY = 50  # max requests per user per day


async def check_rate_limit(user_id: int) -> tuple[bool, str]:
    """
    Check if user has exceeded rate limits.

    Args:
        user_id: Telegram user ID

    Returns:
        Tuple of (is_allowed, error_message).
        is_allowed is True if user is within limits.
    """
    # Check per-minute limit
    minute_key = f"rate:minute:{user_id}"
    minute_count = await redis_client.incr(minute_key)

    if minute_count == 1:
        # Set TTL on first request
        await redis_client.expire(minute_key, 60)

    if minute_count > MAX_REQUESTS_PER_MINUTE:
        ttl = await redis_client.ttl(minute_key)
        logger.warning(f"User {user_id} exceeded per-minute rate limit")
        return False, f"⚠️ Too many requests. Please wait {ttl} seconds."

    # Check per-day limit
    day_key = f"rate:day:{user_id}"
    day_count = await redis_client.incr(day_key)

    if day_count == 1:
        # Set TTL on first request (24 hours)
        await redis_client.expire(day_key, 86400)

    if day_count > MAX_REQUESTS_PER_DAY:
        ttl = await redis_client.ttl(day_key)
        hours = ttl // 3600
        minutes = (ttl % 3600) // 60
        logger.warning(f"User {user_id} exceeded per-day rate limit")
        return False, f"⚠️ Daily limit reached. Resets in {hours}h {minutes}m."

    return True, ""


async def get_user_usage(user_id: int) -> dict:
    """
    Get current usage stats for a user.

    Args:
        user_id: Telegram user ID

    Returns:
        Dict with minute and day usage counts.
    """
    minute_key = f"rate:minute:{user_id}"
    day_key = f"rate:day:{user_id}"

    minute_count = await redis_client.get(minute_key)
    day_count = await redis_client.get(day_key)

    return {
        "minute": int(minute_count or 0),
        "day": int(day_count or 0),
        "minute_limit": MAX_REQUESTS_PER_MINUTE,
        "day_limit": MAX_REQUESTS_PER_DAY,
    }