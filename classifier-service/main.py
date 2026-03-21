from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
import httpx
import logging
import unicodedata
from pathlib import PurePosixPath

from config import settings
from renderer import render_first_page
from classifier import classify_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

storage_client: httpx.AsyncClient = None
vision_client: httpx.AsyncClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global storage_client, vision_client
    storage_client = httpx.AsyncClient(base_url=settings.storage_service_url, timeout=120.0)
    vision_client = httpx.AsyncClient(timeout=300.0)
    yield
    await storage_client.aclose()
    await vision_client.aclose()


app = FastAPI(title="Classifier Service", version="1.0.0", lifespan=lifespan)


class ClassifyRequest(BaseModel):
    document_key: str  # e.g. "raw/document.pdf"


class ClassifyResponse(BaseModel):
    document_key: str
    document_type: str
    confidence: str
    visual_cues: list[str] = []
    title: str | None = None
    description_ru: str | None = None
    screenshot_key: str
    duration_ms: int = 0


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
    result = await classify_image(
        vision_client,
        png_bytes,
        settings.ollama_url,
        settings.ollama_model,
    )

    # Upload screenshot
    filename = PurePosixPath(req.document_key).stem
    screenshot_key = await upload_screenshot(filename, png_bytes)

    logger.info(
        f"Classified {req.document_key}: "
        f"type={result.get('document_type')}, confidence={result.get('confidence')}"
    )

    return ClassifyResponse(
        document_key=req.document_key,
        document_type=result.get("document_type", "unknown"),
        confidence=result.get("confidence", "low"),
        visual_cues=result.get("visual_cues", []),
        title=result.get("title"),
        description_ru=result.get("description_ru"),
        screenshot_key=screenshot_key,
        duration_ms=result.get("duration_ms", 0),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
