from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
import logging

from config import settings
from es_client import (
    init_es, close_es, init_indices,
    index_documents, search_documents, delete_documents,
    index_chunks, search_chunks, delete_chunks,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_es()
    await init_indices()
    yield
    await close_es()


app = FastAPI(title="Search Service", version="2.0.0", lifespan=lifespan)


# --- Shared models ---

class InitIndexRequest(BaseModel):
    recreate: bool = False


# --- Documents models ---

class DocumentPayload(BaseModel):
    filename: str
    title: str = ""
    description: str = ""
    category: str = ""
    subtype: str = ""
    screenshot_key: str = ""
    pages: int = 0
    status: str = ""
    source_key: str = ""
    project_id: str = ""
    document_id: str = ""


class IndexDocumentsRequest(BaseModel):
    documents: list[DocumentPayload]


class IndexDocumentsResponse(BaseModel):
    indexed: int


class DocumentSearchRequest(BaseModel):
    query: str
    limit: int = 5
    category: str | None = None
    subtype: str | None = None
    project_id: str | None = None


class DocumentSearchResult(BaseModel):
    id: str
    score: float
    document_id: str
    filename: str
    title: str
    description: str
    category: str
    subtype: str
    screenshot_key: str
    pages: int
    status: str
    source_key: str
    project_id: str


class DocumentSearchResponse(BaseModel):
    results: list[DocumentSearchResult]
    count: int


class DeleteDocumentsRequest(BaseModel):
    source_key: str | None = None
    document_id: str | None = None
    category: str | None = None
    project_id: str | None = None


# --- Chunks models ---

class ChunkPayload(BaseModel):
    text: str
    text_clean: str
    token_count: int
    index: int
    source: str
    section_title: str
    doc_type: str = ""
    category: str = ""
    subtype: str = ""
    project_id: str = ""
    document_id: str = ""


class IndexChunksRequest(BaseModel):
    chunks: list[ChunkPayload]


class IndexChunksResponse(BaseModel):
    indexed: int


class ChunkSearchRequest(BaseModel):
    query: str
    limit: int = 5
    doc_type: str | None = None
    category: str | None = None
    subtype: str | None = None
    project_id: str | None = None
    document_id: str | None = None


class ChunkSearchResult(BaseModel):
    id: str
    score: float
    text: str
    source: str
    section_title: str
    doc_type: str
    category: str
    subtype: str
    project_id: str
    document_id: str


class ChunkSearchResponse(BaseModel):
    results: list[ChunkSearchResult]
    count: int


class DeleteChunksRequest(BaseModel):
    source: str | None = None
    doc_type: str | None = None
    project_id: str | None = None
    document_id: str | None = None


# --- Base endpoints ---

@app.get("/")
async def root():
    return {
        "service": "Search Service",
        "version": "2.0.0",
        "indices": {
            "documents": settings.documents_index_name,
            "chunks": settings.chunks_index_name,
        },
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/index/init")
async def init_index_endpoint(req: InitIndexRequest):
    """Create or recreate both indices with mappings."""
    try:
        counts = await init_indices(recreate=req.recreate)
    except Exception as e:
        logger.error(f"Index init failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "recreated": req.recreate,
        "doc_counts": counts,
    }


# --- Documents endpoints ---

@app.post("/documents", response_model=IndexDocumentsResponse)
async def index_documents_endpoint(req: IndexDocumentsRequest):
    """Bulk index document catalog entries."""
    if not req.documents:
        raise HTTPException(status_code=400, detail="documents list is empty")

    try:
        count = await index_documents([d.model_dump() for d in req.documents])
    except Exception as e:
        logger.error(f"Indexing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return IndexDocumentsResponse(indexed=count)


@app.post("/documents/search", response_model=DocumentSearchResponse)
async def search_documents_endpoint(req: DocumentSearchRequest):
    """Search document catalog by title and description."""
    try:
        results = await search_documents(
            query=req.query,
            limit=req.limit,
            category=req.category,
            subtype=req.subtype,
            project_id=req.project_id,
        )
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return DocumentSearchResponse(
        results=[DocumentSearchResult(**r) for r in results],
        count=len(results),
    )


@app.delete("/documents")
async def delete_documents_endpoint(req: DeleteDocumentsRequest):
    """Delete documents from catalog by filter."""
    filters = {}
    if req.source_key:
        filters["source_key"] = req.source_key
    if req.document_id:
        filters["document_id"] = req.document_id
    if req.category:
        filters["category"] = req.category
    if req.project_id:
        filters["project_id"] = req.project_id

    if not filters:
        raise HTTPException(status_code=400, detail="At least one filter is required")

    try:
        deleted = await delete_documents(filters)
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {"deleted": deleted, "filters": filters}


# --- Chunks endpoints ---

@app.post("/chunks", response_model=IndexChunksResponse)
async def index_chunks_endpoint(req: IndexChunksRequest):
    """Bulk index text chunks."""
    if not req.chunks:
        raise HTTPException(status_code=400, detail="chunks list is empty")

    try:
        count = await index_chunks([c.model_dump() for c in req.chunks])
    except Exception as e:
        logger.error(f"Indexing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return IndexChunksResponse(indexed=count)


@app.post("/chunks/search", response_model=ChunkSearchResponse)
async def search_chunks_endpoint(req: ChunkSearchRequest):
    """Full-text search across chunk text with Swedish analyzer."""
    try:
        results = await search_chunks(
            query=req.query,
            limit=req.limit,
            doc_type=req.doc_type,
            category=req.category,
            subtype=req.subtype,
            project_id=req.project_id,
            document_id=req.document_id,
        )
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return ChunkSearchResponse(
        results=[ChunkSearchResult(**r) for r in results],
        count=len(results),
    )


@app.delete("/chunks")
async def delete_chunks_endpoint(req: DeleteChunksRequest):
    """Delete chunks by filter."""
    filters = {}
    if req.source:
        filters["source"] = req.source
    if req.doc_type:
        filters["doc_type"] = req.doc_type
    if req.project_id:
        filters["project_id"] = req.project_id
    if req.document_id:
        filters["document_id"] = req.document_id

    if not filters:
        raise HTTPException(status_code=400, detail="At least one filter is required")

    try:
        deleted = await delete_chunks(filters)
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {"deleted": deleted, "filters": filters}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
