import litellm
import structlog

from aipa.config import get_settings

logger = structlog.get_logger(__name__)


async def embed_text(text: str) -> list[float] | None:
    """Embed text with the platform embedding key.

    Returns None when no embedding key is configured or the call fails,
    so callers can fall back to non-vector skill selection.
    """
    settings = get_settings()
    if not settings.EMBEDDING_API_KEY:
        return None

    try:
        response = await litellm.aembedding(
            model=settings.EMBEDDING_MODEL,
            input=[text],
            api_key=settings.EMBEDDING_API_KEY,
            timeout=10,
        )
        return response.data[0]["embedding"]
    except Exception as exc:
        logger.warning("embedding_failed", error=str(exc))
        return None


def embedding_to_pgvector(embedding: list[float]) -> str:
    """Serialize an embedding for asyncpg params cast with ::vector."""
    return "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"
