from fastapi import FastAPI
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import Optional
import asyncio
import httpx
import uvicorn
import logging

from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

http_client: httpx.AsyncClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=120.0)
    yield
    await http_client.aclose()


app = FastAPI(title="MCP Server", version="1.0.0", lifespan=lifespan)


# ============================================================================
# Models
# ============================================================================


class SearchDocumentsRequest(BaseModel):
    query: str
    category: Optional[str] = None
    project_id: Optional[str] = None
    limit: Optional[int] = 5


class SearchChunksRequest(BaseModel):
    query: str
    document_id: Optional[str] = None
    project_id: Optional[str] = None
    limit: Optional[int] = 5


# ============================================================================
# Tool endpoints
# ============================================================================


@app.post("/tools/search_documents")
async def search_documents(req: SearchDocumentsRequest):
    """Search document catalog by title and description via ElasticSearch."""
    logger.info(f"search_documents: query='{req.query}', category={req.category}, project_id={req.project_id}")

    body = {
        "query": req.query,
        "limit": req.limit,
    }
    if req.category:
        body["category"] = req.category
    if req.project_id:
        body["project_id"] = req.project_id

    resp = await http_client.post(
        f"{settings.search_service_url}/documents/search",
        json=body,
    )
    resp.raise_for_status()
    data = resp.json()

    documents = [
        {
            "document_id": r["document_id"],
            "title": r["title"],
            "description": r["description"],
            "category": r["category"],
            "filename": r["filename"],
            "score": r["score"],
        }
        for r in data.get("results", [])
    ]

    return {"documents": documents, "total": len(documents)}


@app.post("/tools/search_chunks")
async def search_chunks(req: SearchChunksRequest):
    """Search chunk content via hybrid ES + Qdrant semantic search."""
    logger.info(f"search_chunks: query='{req.query}', document_id={req.document_id}, project_id={req.project_id}")

    # Build shared filters
    es_body = {
        "query": req.query,
        "limit": req.limit,
    }
    if req.project_id:
        es_body["project_id"] = req.project_id
    if req.document_id:
        es_body["document_id"] = req.document_id

    # Run ES and embedding in parallel
    es_task = http_client.post(
        f"{settings.search_service_url}/chunks/search",
        json=es_body,
    )
    embed_task = http_client.post(
        f"{settings.embedding_service_url}/embed",
        json={"text": req.query},
    )

    es_resp, embed_resp = await asyncio.gather(es_task, embed_task)
    es_resp.raise_for_status()
    embed_resp.raise_for_status()

    vector = embed_resp.json()["embedding"]

    # Qdrant semantic search
    qdrant_body = {
        "vector": vector,
        "limit": req.limit,
    }
    if req.project_id:
        qdrant_body["project_id"] = req.project_id
    if req.document_id:
        qdrant_body["document_id"] = req.document_id

    qdrant_resp = await http_client.post(
        f"{settings.qdrant_service_url}/search",
        json=qdrant_body,
    )
    qdrant_resp.raise_for_status()

    # Merge results, deduplicate by text hash
    seen_texts: set[str] = set()
    merged: list[dict] = []

    for r in es_resp.json().get("results", []):
        text = r.get("text", "")
        key = text[:200]
        if key not in seen_texts:
            seen_texts.add(key)
            merged.append({
                "text": text,
                "source": r.get("source", ""),
                "section_title": r.get("section_title", ""),
                "document_id": r.get("document_id", ""),
                "score": r.get("score", 0.0),
            })

    for r in qdrant_resp.json().get("results", []):
        payload = r.get("payload", {})
        text = payload.get("text", "")
        key = text[:200]
        if key not in seen_texts:
            seen_texts.add(key)
            merged.append({
                "text": text,
                "source": payload.get("source", ""),
                "section_title": payload.get("section_title", ""),
                "document_id": payload.get("document_id", ""),
                "score": r.get("score", 0.0),
            })

    merged.sort(key=lambda x: x["score"], reverse=True)
    chunks = merged[: req.limit]

    return {"chunks": chunks, "total": len(chunks)}


@app.get("/")
async def root():
    return {
        "service": "MCP Server",
        "version": "1.0.0",
        "tools": ["search_documents", "search_chunks"],
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
