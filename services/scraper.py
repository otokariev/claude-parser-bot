import logging
from dataclasses import dataclass

from firecrawl import FirecrawlApp

from bot.config import settings

logger = logging.getLogger(__name__)

# Initialize Firecrawl client
firecrawl = FirecrawlApp(api_key=settings.firecrawl_api_key)


@dataclass
class ScrapeResult:
    """Result of a website scraping operation."""

    url: str
    title: str | None
    content: str
    success: bool
    error: str | None = None


def scrape_url(url: str) -> ScrapeResult:
    """
    Scrape a single URL using Firecrawl.
    Returns clean Markdown content of the page.
    """
    try:
        logger.info(f"Scraping URL: {url}")

        result = firecrawl.scrape(
            url,
            formats=["markdown"],
        )

        # Extract Markdown content and title
        content = result.markdown or ""
        title = result.metadata.title if result.metadata else None

        if not content:
            return ScrapeResult(
                url=url,
                title=title,
                content="",
                success=False,
                error="No content found on the page",
            )

        logger.info(f"Successfully scraped {url} — {len(content)} chars")

        return ScrapeResult(
            url=url,
            title=title,
            content=content,
            success=True,
        )

    except Exception as e:
        logger.error(f"Failed to scrape {url}: {e}")
        return ScrapeResult(
            url=url,
            title=None,
            content="",
            success=False,
            error=str(e),
        )


def scrape_multiple_urls(urls: list[str]) -> list[ScrapeResult]:
    """
    Scrape multiple URLs and return list of results.
    Used for multi-site mode (Step 15).
    """
    results = []
    for url in urls:
        result = scrape_url(url)
        results.append(result)
    return results