import hashlib
import json
import logging
import time
import httpx
import redis.asyncio as redis

from config import settings

logger = logging.getLogger(__name__)

redis_client: redis.Redis = None
CACHE_PREFIX = "emb:"


async def init_redis():
    global redis_client
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)


async def close_redis():
    if redis_client:
        await redis_client.aclose()


def _cache_key(text: str) -> str:
    h = hashlib.sha256(text.encode()).hexdigest()
    return f"{CACHE_PREFIX}{h}"


async def _get_cached(text: str) -> list[float] | None:
    if not redis_client:
        return None
    key = _cache_key(text)
    cached = await redis_client.get(key)
    if cached:
        logger.debug(f"Cache hit for {key[:20]}")
        return json.loads(cached)
    return None


async def _set_cached(text: str, vector: list[float]):
    if not redis_client:
        return
    key = _cache_key(text)
    await redis_client.set(key, json.dumps(vector), ex=settings.cache_ttl)


async def _call_jina(texts: list[str], client: httpx.AsyncClient) -> tuple[list[list[float]], float]:
    """Call Jina Embeddings API. Returns (vectors, elapsed_ms)."""
    payload = {
        "model": settings.jina_embedding_model,
        "task": "text-matching",
        "dimensions": settings.embedding_dimensions,
        "normalized": True,
        "input": [{"text": t} for t in texts],
    }

    start = time.monotonic()
    response = await client.post(
        settings.jina_embedding_base_url,
        json=payload,
        headers={
            "Authorization": f"Bearer {settings.jina_embedding_api_key}",
        },
    )
    response.raise_for_status()
    elapsed_ms = (time.monotonic() - start) * 1000
    data = response.json()

    # Jina returns embeddings sorted by index
    embeddings = sorted(data["data"], key=lambda x: x["index"])
    return [e["embedding"] for e in embeddings], elapsed_ms


async def embed_single(text: str, client: httpx.AsyncClient) -> tuple[list[float], float, bool]:
    """Embed a single text with caching. Returns (vector, elapsed_ms, cached)."""
    cached = await _get_cached(text)
    if cached is not None:
        return cached, 0.0, True

    vectors, elapsed_ms = await _call_jina([text], client)
    vector = vectors[0]

    await _set_cached(text, vector)
    return vector, elapsed_ms, False


async def embed_batch(texts: list[str], client: httpx.AsyncClient) -> tuple[list[list[float]], float]:
    """Embed a batch of texts without caching. Returns (vectors, elapsed_ms)."""
    if not texts:
        return [], 0.0

    logger.info(f"Embedding batch of {len(texts)} texts")
    return await _call_jina(texts, client)
