import logging
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, Filter, FieldCondition, MatchValue, PointStruct, VectorParams
from fastembed import TextEmbedding

from bot.config import settings

logger = logging.getLogger(__name__)

# Initialize Qdrant client
qdrant = QdrantClient(
    host=settings.qdrant_host,
    port=settings.qdrant_port,
    api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
    https=True if settings.qdrant_api_key else False,
)

# Initialize sentence transformer model for embeddings
# This model runs locally — no API key needed
model = TextEmbedding("BAAI/bge-small-en-v1.5")

COLLECTION_NAME = "site_chunks"
VECTOR_SIZE = 384  # all-MiniLM-L6-v2 output size


def embed_text(text: str) -> list[float]:
    """Convert text to embedding vector."""
    return list(model.embed([text]))[0].tolist()


def ensure_collection_exists() -> None:
    """Create Qdrant collection if it doesn't exist, with indexes for filtering."""
    collections = qdrant.get_collections().collections
    names = [c.name for c in collections]

    if COLLECTION_NAME not in names:
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )
        logger.info(f"Created Qdrant collection: {COLLECTION_NAME}")

        # Create indexes for filtering by url and user_id
        qdrant.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="url",
            field_schema="keyword",
        )
        qdrant.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="user_id",
            field_schema="integer",
        )
        logger.info(f"Created payload indexes for {COLLECTION_NAME}")


def save_chunks(url: str, user_id: int, chunks: list[str]) -> None:
    """
    Save text chunks to Qdrant with their embeddings.
    Each chunk is stored with URL and user_id as metadata.
    """
    ensure_collection_exists()

    points = []
    for chunk in chunks:
        vector = embed_text(chunk)
        point = PointStruct(
            id=uuid.uuid4().hex,
            vector=vector,
            payload={
                "url": url,
                "user_id": user_id,
                "text": chunk,
            },
        )
        points.append(point)

    qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
    logger.info(f"Saved {len(chunks)} chunks for {url}")


def search_chunks(query: str, url: str, user_id: int, top_k: int = 5) -> list[str]:
    """
    Search for most relevant chunks by query.
    Filters by URL and user_id to return only relevant content.
    """
    ensure_collection_exists()

    query_vector = embed_text(query)

    results = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=Filter(
            must=[
                FieldCondition(key="url", match=MatchValue(value=url)),
                FieldCondition(key="user_id", match=MatchValue(value=user_id)),
            ]
        ),
        limit=top_k,
    )

    return [hit.payload["text"] for hit in results.points]


def delete_chunks(url: str, user_id: int) -> None:
    """Delete all chunks for a specific URL and user."""
    qdrant.delete(
        collection_name=COLLECTION_NAME,
        points_selector={
            "filter": {
                "must": [
                    {"key": "url", "match": {"value": url}},
                    {"key": "user_id", "match": {"value": user_id}},
                ]
            }
        },
    )
    logger.info(f"Deleted chunks for {url}")