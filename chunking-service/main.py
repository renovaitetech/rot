from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
import httpx
import logging

from config import settings
from chunker import chunk_text, STRATEGIES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

http_client: httpx.AsyncClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(base_url=settings.storage_service_url, timeout=120.0)
    yield
    await http_client.aclose()


app = FastAPI(title="Chunking Service", version="1.0.0", lifespan=lifespan)


class ChunkRequest(BaseModel):
    key: str  # e.g. "markdown/document.md"
    strategy: str = ""  # slumber, semantic, recursive


class ChunkItem(BaseModel):
    text: str
    text_clean: str
    token_count: int
    index: int
    source: str
    section_title: str


class ChunkResponse(BaseModel):
    source: str
    strategy: str
    chunks: list[ChunkItem]
    total_chunks: int


@app.get("/")
async def root():
    return {
        "service": "Chunking Service",
        "version": "1.0.0",
        "strategies": list(STRATEGIES.keys()),
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/chunk", response_model=ChunkResponse)
async def chunk_document(req: ChunkRequest):
    """Download Markdown from storage, chunk it, return results."""
    # Download markdown from storage-service
    logger.info(f"Downloading {req.key} from storage-service")
    resp = await http_client.get(f"/documents/{req.key}")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Document not found: {req.key}")
    resp.raise_for_status()
    text = resp.text

    strategy = req.strategy or settings.default_strategy

    # Chunk the text
    try:
        results = chunk_text(text, source=req.key, strategy=strategy)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Chunking failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chunking failed: {str(e)}")

    chunks = [
        ChunkItem(
            text=r.text,
            text_clean=r.text_clean,
            token_count=r.token_count,
            index=r.index,
            source=r.source,
            section_title=r.section_title,
        )
        for r in results
    ]

    return ChunkResponse(
        source=req.key,
        strategy=strategy,
        chunks=chunks,
        total_chunks=len(chunks),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
