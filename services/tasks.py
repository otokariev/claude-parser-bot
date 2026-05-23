import asyncio
import logging

from services.celery_app import celery_app
from services.scraper import scrape_url
from services.rag import index_site_content
from services.claude import generate_site_summary

from db.repository import get_active_monitors, update_monitor_check

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.scrape_and_index")
def scrape_and_index_task(self, url: str, user_id: int) -> dict:
    """
    Celery task: scrape URL, generate summary and index content to Qdrant.
    Runs in background worker, not in the main bot process.

    Args:
        self: Celery task instance (used for retry)
        url: Website URL to scrape
        user_id: Telegram user ID for filtering in Qdrant

    Returns:
        dict with success status, title, summary and content length
    """
    try:
        logger.info(f"Task started: scraping {url} for user {user_id}")

        # Scrape the URL
        result = scrape_url(url)

        if not result.success:
            logger.error(f"Scraping failed for {url}: {result.error}")
            return {
                "success": False,
                "error": result.error,
                "url": url,
            }

        # Generate site summary
        summary = generate_site_summary(content=result.content, url=url)

        # Index content to Qdrant
        chunks_count = index_site_content(
            url=url,
            user_id=user_id,
            content=result.content,
        )

        logger.info(f"Task completed: {url} — {chunks_count} chunks indexed")

        return {
            "success": True,
            "url": url,
            "title": result.title,
            "summary": summary,
            "content": result.content,
            "chunks_count": chunks_count,
        }

    except Exception as e:
        logger.error(f"Task failed for {url}: {e}")
        raise self.retry(exc=e, countdown=5, max_retries=3)


@celery_app.task(name="tasks.check_monitors")
def check_monitors_task() -> dict:
    """
    Celery Beat task: check all active site monitors for content changes.
    Runs periodically based on Celery Beat schedule.

    Returns:
        Dict with number of checked and changed sites
    """

    async def _check():
        monitors = await get_active_monitors()
        checked = 0
        changed = 0

        for monitor in monitors:
            # Get site URL from saved_site relationship
            from db.repository import get_site_by_id
            site = await get_site_by_id(
                site_id=monitor.saved_site_id,
                user_id=0,  # bypass user check
            )
            if not site:
                continue

            has_changed, new_content, new_hash = await check_site_for_changes(
                url=site.url,
                old_hash=monitor.last_content_hash,
            )

            await update_monitor_check(
                monitor_id=monitor.id,
                content_hash=new_hash,
            )

            if has_changed and monitor.last_content_hash:
                logger.info(f"Site changed: {site.url}")
                changed += 1

            checked += 1

        return {"checked": checked, "changed": changed}

    return asyncio.run(_check())