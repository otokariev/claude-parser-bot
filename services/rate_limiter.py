import logging

import redis.asyncio as aioredis

from bot.config import settings

logger = logging.getLogger(__name__)

# Initialize async Redis client
redis_client = aioredis.from_url(
    settings.redis_url,
    decode_responses=True,
    ssl_cert_reqs=None,
)

# Rate limit settings
MAX_REQUESTS_PER_MINUTE = 10  # max requests per user per minute
FREE_REQUESTS_PER_DAY = 2     # max requests per day for free users


async def check_rate_limit(user_id: int, subscription: str = "free") -> tuple[bool, str]:
    """
    Check if user has exceeded rate limits.
    Pro users have no daily limit, only per-minute limit.

    Args:
        user_id: Telegram user ID
        subscription: User subscription type — 'free' or 'pro'

    Returns:
        Tuple of (is_allowed, error_message).
        is_allowed is True if user is within limits.
    """
    # Check per-minute limit for all users
    minute_key = f"rate:minute:{user_id}"
    minute_count = await redis_client.incr(minute_key)

    if minute_count == 1:
        await redis_client.expire(minute_key, 60)

    if minute_count > MAX_REQUESTS_PER_MINUTE:
        ttl = await redis_client.ttl(minute_key)
        logger.warning(f"User {user_id} exceeded per-minute rate limit")
        return False, f"⚠️ Too many requests. Please wait {ttl} seconds."

    # Pro users have no daily limit
    if subscription == "pro":
        return True, ""

    # Check per-day limit for free users
    day_key = f"rate:day:{user_id}"
    day_count = await redis_client.incr(day_key)

    if day_count == 1:
        await redis_client.expire(day_key, 86400)

    if day_count > FREE_REQUESTS_PER_DAY:
        ttl = await redis_client.ttl(day_key)
        hours = ttl // 3600
        minutes = (ttl % 3600) // 60
        logger.warning(f"User {user_id} exceeded daily rate limit")
        return False, (
            f"⚠️ Daily limit reached ({FREE_REQUESTS_PER_DAY} requests/day on free plan).\n\n"
            f"Resets in {hours}h {minutes}m.\n\n"
            f"Upgrade to <b>Pro</b> for unlimited requests — /subscribe"
        )

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
        "day_limit": FREE_REQUESTS_PER_DAY,
    }