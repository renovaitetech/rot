from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.responses import Response
from contextlib import asynccontextmanager
import logging

from s3 import ensure_bucket, upload_file, download_file, list_files, delete_file

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_bucket()
    yield


app = FastAPI(title="Storage Service", version="1.0.0", lifespan=lifespan)


@app.get("/")
async def root():
    return {"service": "Storage Service", "version": "1.0.0", "status": "operational"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    prefix: str = Query("raw", description="Storage prefix: 'raw' or 'markdown'"),
):
    """Upload a document to the specified prefix."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    data = await file.read()
    key = f"{prefix}/{file.filename}"
    content_type = file.content_type or "application/octet-stream"
    await upload_file(key, data, content_type)

    return {"key": key, "size": len(data), "content_type": content_type}


@app.get("/documents/")
async def list_documents(prefix: str = Query("", description="Filter by prefix, e.g. 'raw/' or 'markdown/'")):
    """List documents in the bucket."""
    files = await list_files(prefix)
    return {"files": files, "count": len(files)}


@app.get("/documents/{path:path}")
async def get_document(path: str):
    """Download a document by key."""
    result = await download_file(path)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {path}")

    return Response(content=result["body"], media_type=result["content_type"])


@app.delete("/documents/{path:path}")
async def delete_document(path: str):
    """Delete a document by key."""
    deleted = await delete_file(path)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Document not found: {path}")

    return {"deleted": path}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
