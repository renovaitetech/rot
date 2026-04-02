from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
import logging

from config import settings
from qdrant_repo import (
    init_client,
    init_collections,
    upsert_document,
    get_document,
    update_document_payload,
    search_documents,
    delete_document,
    upsert_chunks,
    search_chunks,
    delete_chunks_by_filter,
    migrate_to_two_collections,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_client()
    init_collections()
    yield


app = FastAPI(title="Qdrant Service", version="2.0.0", lifespan=lifespan)


# ============================================================================
# Models — Documents (catalog)
# ============================================================================


class DocumentPayload(BaseModel):
    filename: str = ""
    category: str = "unknown"   # drawing, presentation, text_spec, table_spec
    title: str | None = None
    description: str | None = None
    screenshot_key: str | None = None
    thumbnails: list[str] = []
    pages: int = 0
    status: str = "classified"
    source_key: str = ""        # raw/document.pdf
    markdown_key: str = ""      # markdown/document.md
    project_id: str = ""
    subtypes: list[str] = []    # unique subtypes from vision analysis


class UpsertDocumentRequest(BaseModel):
    embedding: list[float]
    payload: DocumentPayload


class UpsertDocumentResponse(BaseModel):
    document_id: str


class SearchDocumentsRequest(BaseModel):
    vector: list[float]
    limit: int = 5
    category: str | None = None
    project_id: str | None = None


class DocumentResult(BaseModel):
    id: str
    score: float
    payload: dict


class SearchDocumentsResponse(BaseModel):
    results: list[DocumentResult]
    count: int


# ============================================================================
# Models — Chunks (RAG)
# ============================================================================


class ChunkPayload(BaseModel):
    text: str
    text_clean: str
    token_count: int
    index: int
    source: str
    section_title: str
    page: int = 0
    document_id: str = ""
    doc_type: str = ""
    category: str = ""      # drawing, presentation, text_spec, table_spec
    subtype: str = ""       # apartment_plan, facade, chart, title, etc.
    project_id: str = ""


class UpsertChunk(BaseModel):
    embedding: list[float]
    payload: ChunkPayload


class UpsertChunksRequest(BaseModel):
    points: list[UpsertChunk]


class UpsertChunksResponse(BaseModel):
    upserted: int


class SearchChunksRequest(BaseModel):
    vector: list[float]
    limit: int = 5
    doc_type: str | None = None
    project_id: str | None = None
    document_id: str | None = None


class ChunkResult(BaseModel):
    id: str
    score: float
    payload: dict


class SearchChunksResponse(BaseModel):
    results: list[ChunkResult]
    count: int


class DeleteChunksRequest(BaseModel):
    source: str | None = None
    doc_type: str | None = None
    project_id: str | None = None
    document_id: str | None = None


# ============================================================================
# Models — Collections
# ============================================================================


class InitCollectionRequest(BaseModel):
    recreate: bool = False


# ============================================================================
# Endpoints — Common
# ============================================================================


@app.get("/")
async def root():
    return {
        "service": "Qdrant Service",
        "version": "2.0.0",
        "collections": {
            "documents": settings.documents_collection,
            "chunks": settings.chunks_collection,
        },
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/collections/init")
async def init_collections_endpoint(req: InitCollectionRequest):
    """Create or recreate both collections."""
    try:
        infos = init_collections(recreate=req.recreate)
    except Exception as e:
        logger.error(f"Collection init failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "recreated": req.recreate,
        "documents": {
            "collection": settings.documents_collection,
            "points_count": infos["documents"].points_count,
        },
        "chunks": {
            "collection": settings.chunks_collection,
            "points_count": infos["chunks"].points_count,
        },
    }


# ============================================================================
# Endpoints — Documents (catalog)
# ============================================================================


@app.post("/documents", response_model=UpsertDocumentResponse)
async def upsert_document_endpoint(req: UpsertDocumentRequest):
    """Add a document to the catalog."""
    try:
        doc_id = upsert_document(req.embedding, req.payload.model_dump())
    except Exception as e:
        logger.error(f"Document upsert failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return UpsertDocumentResponse(document_id=doc_id)


@app.get("/documents/{document_id}")
async def get_document_endpoint(document_id: str):
    """Get a document from the catalog by ID."""
    result = get_document(document_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")
    return result


@app.post("/documents/search", response_model=SearchDocumentsResponse)
async def search_documents_endpoint(req: SearchDocumentsRequest):
    """Semantic search over document catalog."""
    filters = {}
    if req.category:
        filters["category"] = req.category
    if req.project_id:
        filters["project_id"] = req.project_id

    try:
        results = search_documents(
            vector=req.vector,
            limit=req.limit,
            filters=filters if filters else None,
        )
    except Exception as e:
        logger.error(f"Documents search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return SearchDocumentsResponse(
        results=[DocumentResult(**r) for r in results],
        count=len(results),
    )


@app.patch("/documents/{document_id}")
async def update_document_endpoint(document_id: str, fields: dict):
    """Partial update of document payload fields."""
    try:
        update_document_payload(document_id, fields)
    except Exception as e:
        logger.error(f"Document update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    return {"updated": True, "document_id": document_id, "fields": list(fields.keys())}


@app.delete("/documents/{document_id}")
async def delete_document_endpoint(document_id: str):
    """Delete a document from the catalog."""
    try:
        delete_document(document_id)
    except Exception as e:
        logger.error(f"Document delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    return {"deleted": True, "document_id": document_id}


# ============================================================================
# Endpoints — Chunks (RAG)
# ============================================================================


@app.post("/points", response_model=UpsertChunksResponse)
async def upsert_chunks_endpoint(req: UpsertChunksRequest):
    """Upsert chunk points with embeddings and payload."""
    if not req.points:
        raise HTTPException(status_code=400, detail="points list is empty")

    try:
        count = upsert_chunks([
            {"embedding": p.embedding, "payload": p.payload.model_dump()}
            for p in req.points
        ])
    except Exception as e:
        logger.error(f"Chunks upsert failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return UpsertChunksResponse(upserted=count)


@app.post("/search", response_model=SearchChunksResponse)
async def search_chunks_endpoint(req: SearchChunksRequest):
    """Search for similar chunks with optional filters."""
    filters = {}
    if req.doc_type:
        filters["doc_type"] = req.doc_type
    if req.project_id:
        filters["project_id"] = req.project_id
    if req.document_id:
        filters["document_id"] = req.document_id

    try:
        results = search_chunks(
            vector=req.vector,
            limit=req.limit,
            filters=filters if filters else None,
        )
    except Exception as e:
        logger.error(f"Chunks search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return SearchChunksResponse(
        results=[ChunkResult(**r) for r in results],
        count=len(results),
    )


@app.delete("/points")
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
        delete_chunks_by_filter(filters)
    except Exception as e:
        logger.error(f"Chunks delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {"deleted": True, "filters": filters}


# ============================================================================
# Endpoints — Migration
# ============================================================================


@app.post("/migrate")
async def migrate_endpoint():
    """Migrate data from old single-collection layout to documents + chunks."""
    try:
        stats = migrate_to_two_collections()
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "completed", **stats}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
