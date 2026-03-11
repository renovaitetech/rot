from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
import httpx
import logging

from config import settings
from embedder import embed_single, embed_batch, init_redis, close_redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

http_client: httpx.AsyncClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=120.0)
    await init_redis()
    yield
    await http_client.aclose()
    await close_redis()


app = FastAPI(title="Embedding Service", version="1.0.0", lifespan=lifespan)


class EmbedRequest(BaseModel):
    text: str


class EmbedResponse(BaseModel):
    embedding: list[float]
    dimensions: int
    elapsed_ms: float
    cached: bool


class EmbedBatchRequest(BaseModel):
    texts: list[str]


class EmbedBatchResponse(BaseModel):
    embeddings: list[list[float]]
    dimensions: int
    count: int
    elapsed_ms: float


@app.get("/")
async def root():
    return {
        "service": "Embedding Service",
        "version": "1.0.0",
        "model": settings.jina_embedding_model,
        "dimensions": settings.embedding_dimensions,
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest):
    """Embed a single text. Results are cached in Redis."""
    try:
        vector, elapsed_ms, cached = await embed_single(req.text, http_client)
    except httpx.HTTPStatusError as e:
        logger.error(f"Jina API error: {e.response.status_code} {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Jina API error: {e.response.text}")
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return EmbedResponse(
        embedding=vector,
        dimensions=len(vector),
        elapsed_ms=round(elapsed_ms, 1),
        cached=cached,
    )


@app.post("/embed/batch", response_model=EmbedBatchResponse)
async def embed_batch_endpoint(req: EmbedBatchRequest):
    """Embed a batch of texts. No caching."""
    if not req.texts:
        raise HTTPException(status_code=400, detail="texts list is empty")

    try:
        vectors, elapsed_ms = await embed_batch(req.texts, http_client)
    except httpx.HTTPStatusError as e:
        logger.error(f"Jina API error: {e.response.status_code} {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Jina API error: {e.response.text}")
    except Exception as e:
        logger.error(f"Batch embedding failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return EmbedBatchResponse(
        embeddings=vectors,
        dimensions=settings.embedding_dimensions,
        count=len(vectors),
        elapsed_ms=round(elapsed_ms, 1),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
