from fastapi import FastAPI
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import Optional
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
    doc_type: Optional[str] = None
    project_id: Optional[str] = "proj1"
    limit: Optional[int] = 5


# ============================================================================
# Tool endpoints
# ============================================================================


@app.post("/tools/search_documents")
async def search_documents(req: SearchDocumentsRequest):
    """Search documents via embedding + Qdrant vector search."""
    logger.info(f"search_documents: query='{req.query}', limit={req.limit}")

    # 1. Get embedding for query
    embed_resp = await http_client.post(
        f"{settings.embedding_service_url}/embed",
        json={"text": req.query},
    )
    embed_resp.raise_for_status()
    vector = embed_resp.json()["embedding"]

    # 2. Search in Qdrant
    search_body = {
        "vector": vector,
        "limit": req.limit,
    }
    if req.doc_type:
        search_body["doc_type"] = req.doc_type
    if req.project_id:
        search_body["project_id"] = req.project_id

    search_resp = await http_client.post(
        f"{settings.qdrant_service_url}/search",
        json=search_body,
    )
    search_resp.raise_for_status()
    results = search_resp.json()["results"]

    # 3. Format response
    documents = [
        {
            "text": r["payload"].get("text", ""),
            "source": r["payload"].get("source", ""),
            "section_title": r["payload"].get("section_title", ""),
            "project_id": r["payload"].get("project_id", ""),
            "document_id": r["payload"].get("document_id", ""),
            "score": r["score"],
        }
        for r in results
    ]

    return {"documents": documents, "total": len(documents)}


@app.get("/")
async def root():
    return {
        "service": "MCP Server",
        "version": "1.0.0",
        "tools": ["search_documents"],
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
