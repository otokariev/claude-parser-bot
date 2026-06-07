import json
import logging

import redis.asyncio as aioredis

from bot.config import settings

logger = logging.getLogger(__name__)

# Cache TTL in seconds (1 hour)
CACHE_TTL = 3600

# Initialize async Redis client
redis_client = aioredis.from_url(
    settings.redis_url,
    decode_responses=True,
    ssl_cert_reqs=None,
)


async def get_cached_content(url: str, user_id: int) -> dict | None:
    """
    Get cached scrape result for a URL.
    Returns dict with title and content, or None if not cached.
    """
    try:
        key = f"scrape:{user_id}:{url}"
        data = await redis_client.get(key)

        if data:
            logger.info(f"Cache hit for {url}")
            return json.loads(data)

        logger.info(f"Cache miss for {url}")
        return None

    except Exception as e:
        logger.error(f"Redis get error: {e}")
        return None


async def set_cached_content(url: str, user_id: int, title: str | None, content: str) -> None:
    """
    Cache scrape result for a URL.
    TTL is set to CACHE_TTL seconds.
    """
    try:
        key = f"scrape:{user_id}:{url}"
        data = json.dumps({"title": title, "content": content})
        await redis_client.set(key, data, ex=CACHE_TTL)
        logger.info(f"Cached content for {url} — TTL {CACHE_TTL}s")

    except Exception as e:
        logger.error(f"Redis set error: {e}")


async def delete_cached_content(url: str, user_id: int) -> None:
    """Delete cached content for a specific URL and user."""
    try:
        key = f"scrape:{user_id}:{url}"
        await redis_client.delete(key)
        logger.info(f"Deleted cache for {url}")

    except Exception as e:
        logger.error(f"Redis delete error: {e}")


async def is_url_cached(url: str, user_id: int) -> bool:
    """Check if URL content is cached."""
    try:
        key = f"scrape:{user_id}:{url}"
        return await redis_client.exists(key) > 0

    except Exception as e:
        logger.error(f"Redis exists error: {e}")
        return False