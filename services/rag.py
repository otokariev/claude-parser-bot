import logging

from services.vector_store import save_chunks, search_chunks

logger = logging.getLogger(__name__)

# Chunk size in characters
CHUNK_SIZE = 1000
# Overlap between chunks to preserve context
CHUNK_OVERLAP = 100


def split_text_into_chunks(text: str) -> list[str]:
    """
    Split text into overlapping chunks of fixed size.
    Overlap ensures context is not lost at chunk boundaries.
    """
    chunks = []
    start = 0

    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        chunks.append(chunk)
        start += CHUNK_SIZE - CHUNK_OVERLAP

    logger.info(f"Split text into {len(chunks)} chunks")
    return chunks


def index_site_content(url: str, user_id: int, content: str) -> int:
    """
    Split site content into chunks and save to Qdrant.
    Returns number of chunks saved.
    """
    chunks = split_text_into_chunks(content)
    save_chunks(url=url, user_id=user_id, chunks=chunks)
    return len(chunks)


def get_relevant_context(query: str, url: str, user_id: int, top_k: int = 5) -> str:
    """
    Search for relevant chunks by query and combine into context string.
    This context will be passed to Claude as reference material.
    """
    chunks = search_chunks(
        query=query,
        url=url,
        user_id=user_id,
        top_k=top_k,
    )

    if not chunks:
        return ""

    # Combine chunks into single context string
    context = "\n\n---\n\n".join(chunks)
    logger.info(f"Found {len(chunks)} relevant chunks for query: {query}")
    return context