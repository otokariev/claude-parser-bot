import logging

from services.celery_app import celery_app
from services.scraper import scrape_url
from services.rag import index_site_content

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.scrape_and_index")
def scrape_and_index_task(self, url: str, user_id: int) -> dict:
    """
    Celery task: scrape URL and index content to Qdrant.
    Runs in background worker, not in the main bot process.

    Args:
        self: Celery task instance (used for retry)
        url: Website URL to scrape
        user_id: Telegram user ID for filtering in Qdrant

    Returns:
        dict with success status, title and content length
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
            "content": result.content,
            "chunks_count": chunks_count,
        }

    except Exception as e:
        logger.error(f"Task failed for {url}: {e}")
        # Retry task up to 3 times with 5 seconds delay
        raise self.retry(exc=e, countdown=5, max_retries=3)