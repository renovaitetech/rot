from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
import logging

from config import settings
from es_client import init_es, close_es, init_index, index_documents, search_documents, delete_by_filter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_es()
    await init_index()
    yield
    await close_es()


app = FastAPI(title="Search Service", version="1.0.0", lifespan=lifespan)


# --- Models ---

class InitIndexRequest(BaseModel):
    recreate: bool = False


class DocumentPayload(BaseModel):
    text: str
    text_clean: str
    token_count: int
    index: int
    source: str
    section_title: str
    doc_type: str = ""
    category: str = ""      # drawing, presentation, text_spec, table_spec
    subtype: str = ""       # apartment_plan, facade, chart, title, etc.
    project_id: str = ""


class IndexRequest(BaseModel):
    documents: list[DocumentPayload]


class IndexResponse(BaseModel):
    indexed: int


class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    doc_type: str | None = None
    category: str | None = None
    subtype: str | None = None
    project_id: str | None = None


class SearchResult(BaseModel):
    id: str
    score: float
    text: str
    source: str
    section_title: str
    doc_type: str
    category: str = ""
    subtype: str = ""
    project_id: str


class SearchResponse(BaseModel):
    results: list[SearchResult]
    count: int


class DeleteRequest(BaseModel):
    source: str | None = None
    doc_type: str | None = None
    project_id: str | None = None


# --- Endpoints ---

@app.get("/")
async def root():
    return {
        "service": "Search Service",
        "version": "1.0.0",
        "index": settings.index_name,
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/index/init")
async def init_index_endpoint(req: InitIndexRequest):
    """Create or recreate the index with mapping."""
    try:
        doc_count = await init_index(recreate=req.recreate)
    except Exception as e:
        logger.error(f"Index init failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "index": settings.index_name,
        "recreated": req.recreate,
        "doc_count": doc_count,
    }


@app.post("/documents", response_model=IndexResponse)
async def index_documents_endpoint(req: IndexRequest):
    """Bulk index documents."""
    if not req.documents:
        raise HTTPException(status_code=400, detail="documents list is empty")

    try:
        count = await index_documents([d.model_dump() for d in req.documents])
    except Exception as e:
        logger.error(f"Indexing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return IndexResponse(indexed=count)


@app.post("/search", response_model=SearchResponse)
async def search_endpoint(req: SearchRequest):
    """Full-text search with optional filters."""
    try:
        results = await search_documents(
            query=req.query,
            limit=req.limit,
            doc_type=req.doc_type,
            category=req.category,
            subtype=req.subtype,
            project_id=req.project_id,
        )
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return SearchResponse(
        results=[SearchResult(**r) for r in results],
        count=len(results),
    )


@app.delete("/documents")
async def delete_documents_endpoint(req: DeleteRequest):
    """Delete documents by filter."""
    filters = {}
    if req.source:
        filters["source"] = req.source
    if req.doc_type:
        filters["doc_type"] = req.doc_type
    if req.project_id:
        filters["project_id"] = req.project_id

    if not filters:
        raise HTTPException(status_code=400, detail="At least one filter is required")

    try:
        deleted = await delete_by_filter(filters)
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {"deleted": deleted, "filters": filters}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
