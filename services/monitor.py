import hashlib
import logging

from services.scraper import scrape_url

logger = logging.getLogger(__name__)


def compute_content_hash(content: str) -> str:
    """
    Compute MD5 hash of content to detect changes.

    Args:
        content: Website content as string

    Returns:
        MD5 hash string
    """
    return hashlib.md5(content.encode()).hexdigest()


def has_content_changed(new_content: str, old_hash: str | None) -> bool:
    """
    Check if content has changed by comparing hashes.

    Args:
        new_content: Freshly scraped content
        old_hash: Previously stored content hash

    Returns:
        True if content has changed or no previous hash exists
    """
    if not old_hash:
        return True

    new_hash = compute_content_hash(new_content)
    return new_hash != old_hash


async def check_site_for_changes(
        url: str,
        old_hash: str | None,
) -> tuple[bool, str, str]:
    """
    Scrape site and check if content has changed.

    Args:
        url: Website URL to check
        old_hash: Previously stored content hash

    Returns:
        Tuple of (has_changed, new_content, new_hash)
    """
    result = scrape_url(url)

    if not result.success:
        logger.error(f"Failed to scrape {url} for monitoring: {result.error}")
        return False, "", old_hash or ""

    new_hash = compute_content_hash(result.content)
    changed = has_content_changed(result.content, old_hash)

    logger.info(f"Monitor check for {url} — changed: {changed}")
    return changed, result.content, new_hash