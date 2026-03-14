from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
import logging

from config import settings
from qdrant_repo import init_client, init_collection, upsert_points, search_points, delete_by_filter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_client()
    init_collection()
    yield


app = FastAPI(title="Qdrant Service", version="1.0.0", lifespan=lifespan)


# --- Models ---

class InitCollectionRequest(BaseModel):
    recreate: bool = False


class PointPayload(BaseModel):
    text: str
    text_clean: str
    token_count: int
    index: int
    source: str
    section_title: str
    doc_type: str = "FU"
    project_id: str = ""


class UpsertPoint(BaseModel):
    embedding: list[float]
    payload: PointPayload


class UpsertRequest(BaseModel):
    points: list[UpsertPoint]


class UpsertResponse(BaseModel):
    upserted: int


class SearchRequest(BaseModel):
    vector: list[float]
    limit: int = 5
    doc_type: str | None = None
    project_id: str | None = None


class SearchResult(BaseModel):
    id: str
    score: float
    payload: dict


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
        "service": "Qdrant Service",
        "version": "1.0.0",
        "collection": settings.collection_name,
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/collections/init")
async def init_collection_endpoint(req: InitCollectionRequest):
    """Create or recreate the collection."""
    try:
        info = init_collection(recreate=req.recreate)
    except Exception as e:
        logger.error(f"Collection init failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "collection": settings.collection_name,
        "recreated": req.recreate,
        "points_count": info.points_count,
        "vectors_count": info.vectors_count,
    }


@app.post("/points", response_model=UpsertResponse)
async def upsert_points_endpoint(req: UpsertRequest):
    """Upsert points with embeddings and payload."""
    if not req.points:
        raise HTTPException(status_code=400, detail="points list is empty")

    try:
        count = upsert_points([
            {"embedding": p.embedding, "payload": p.payload.model_dump()}
            for p in req.points
        ])
    except Exception as e:
        logger.error(f"Upsert failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return UpsertResponse(upserted=count)


@app.post("/search", response_model=SearchResponse)
async def search_endpoint(req: SearchRequest):
    """Search for similar vectors with optional filters."""
    filters = {}
    if req.doc_type:
        filters["doc_type"] = req.doc_type
    if req.project_id:
        filters["project_id"] = req.project_id

    try:
        results = search_points(
            vector=req.vector,
            limit=req.limit,
            filters=filters if filters else None,
        )
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return SearchResponse(
        results=[SearchResult(**r) for r in results],
        count=len(results),
    )


@app.delete("/points")
async def delete_points_endpoint(req: DeleteRequest):
    """Delete points by filter."""
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
        delete_by_filter(filters)
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {"deleted": True, "filters": filters}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
