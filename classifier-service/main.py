from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
import httpx
import logging
import unicodedata
from pathlib import PurePosixPath

from config import settings
from renderer import render_first_page, generate_thumbnails
from classifier import classify_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

storage_client: httpx.AsyncClient = None
vision_client: httpx.AsyncClient = None
qdrant_client: httpx.AsyncClient = None
embedding_client: httpx.AsyncClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global storage_client, vision_client, qdrant_client, embedding_client
    storage_client = httpx.AsyncClient(base_url=settings.storage_service_url, timeout=120.0)
    vision_client = httpx.AsyncClient(timeout=300.0)
    qdrant_client = httpx.AsyncClient(base_url=settings.qdrant_service_url, timeout=30.0)
    embedding_client = httpx.AsyncClient(base_url=settings.embedding_service_url, timeout=60.0)
    yield
    await storage_client.aclose()
    await vision_client.aclose()
    await qdrant_client.aclose()
    await embedding_client.aclose()


app = FastAPI(title="Classifier Service", version="1.0.0", lifespan=lifespan)


class ClassifyRequest(BaseModel):
    document_key: str  # e.g. "raw/document.pdf"
    project_id: str = ""


class ClassifyResponse(BaseModel):
    document_key: str
    category: str
    confidence: str
    visual_cues: list[str] = []
    title: str | None = None
    description: str | None = None
    screenshot_key: str
    thumbnails: list[str] = []
    pages: int = 0
    duration_ms: int = 0
    document_id: str | None = None


@app.get("/")
async def root():
    return {"service": "Classifier Service", "version": "1.0.0", "status": "operational"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


async def download_pdf(key: str) -> bytes:
    """Download PDF from storage, trying NFC and NFD unicode normalization."""
    for form in ("NFC", "NFD"):
        normalized_key = unicodedata.normalize(form, key)
        resp = await storage_client.get(f"/documents/{normalized_key}")
        if resp.status_code == 200:
            return resp.content
    raise HTTPException(status_code=404, detail=f"Document not found: {key}")


async def register_document(
    document_key: str,
    filename: str,
    result: dict,
    screenshot_key: str,
    thumbnail_keys: list[str],
    project_id: str = "",
) -> str | None:
    """Register document in Qdrant catalog with embedding of title + description."""
    title = result.get("title", "") or ""
    description = result.get("description", "") or ""
    embed_text = f"{title} {description}".strip()
    if not embed_text:
        logger.warning("No title/description for embedding, skipping catalog registration")
        return None

    # Get embedding
    embed_resp = await embedding_client.post("/embed", json={"text": embed_text})
    embed_resp.raise_for_status()
    embedding = embed_resp.json()["embedding"]

    # Register in catalog
    payload = {
        "filename": filename,
        "category": result.get("category", "unknown"),
        "title": title,
        "description": description,
        "screenshot_key": screenshot_key,
        "thumbnails": thumbnail_keys,
        "pages": len(thumbnail_keys),
        "status": "classified",
        "source_key": document_key,
        "project_id": project_id,
    }
    resp = await qdrant_client.post(
        "/documents",
        json={"embedding": embedding, "payload": payload},
    )
    resp.raise_for_status()
    doc_id = resp.json()["document_id"]
    logger.info(f"Registered document '{doc_id}' in catalog")
    return doc_id


async def upload_screenshot(filename: str, png_bytes: bytes) -> str:
    """Upload screenshot PNG to storage service."""
    screenshot_key = f"screenshots/{filename}.png"
    resp = await storage_client.post(
        "/documents/upload",
        params={"prefix": "screenshots"},
        files={"file": (f"{filename}.png", png_bytes, "image/png")},
    )
    resp.raise_for_status()
    return screenshot_key


@app.post("/classify", response_model=ClassifyResponse)
async def classify_document(req: ClassifyRequest):
    """Download PDF, render first page, classify via vision model, upload screenshot."""
    logger.info(f"Classifying {req.document_key}")

    # Download PDF
    pdf_bytes = await download_pdf(req.document_key)

    # Render first page
    png_bytes = render_first_page(pdf_bytes, settings.target_long_side)

    # Classify via vision model
    result = await classify_image(vision_client, png_bytes)

    # Upload screenshot
    filename = PurePosixPath(req.document_key).stem
    screenshot_key = await upload_screenshot(filename, png_bytes)

    # Generate and upload thumbnails
    logger.info(f"Generating thumbnails for {req.document_key}")
    thumb_images = generate_thumbnails(pdf_bytes)
    thumbnail_keys = []
    for i, thumb_bytes in enumerate(thumb_images):
        thumb_filename = f"{filename}_page_{i + 1}.png"
        resp = await storage_client.post(
            "/documents/upload",
            params={"prefix": f"thumbnails/{filename}"},
            files={"file": (thumb_filename, thumb_bytes, "image/png")},
        )
        resp.raise_for_status()
        thumbnail_keys.append(f"thumbnails/{filename}/{thumb_filename}")

    # Register in document catalog
    document_id = None
    try:
        document_id = await register_document(
            document_key=req.document_key,
            filename=filename,
            result=result,
            screenshot_key=screenshot_key,
            thumbnail_keys=thumbnail_keys,
            project_id=req.project_id,
        )
    except Exception as e:
        logger.error(f"Failed to register document in catalog: {e}")

    logger.info(
        f"Classified {req.document_key}: "
        f"category={result.get('category')}, confidence={result.get('confidence')}, "
        f"{len(thumbnail_keys)} thumbnails, document_id={document_id}"
    )

    return ClassifyResponse(
        document_key=req.document_key,
        category=result.get("category", "unknown"),
        confidence=result.get("confidence", "low"),
        visual_cues=result.get("visual_cues", []),
        title=result.get("title"),
        description=result.get("description"),
        screenshot_key=screenshot_key,
        thumbnails=thumbnail_keys,
        pages=len(thumbnail_keys),
        duration_ms=result.get("duration_ms", 0),
        document_id=document_id,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
