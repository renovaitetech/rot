from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
import httpx
import logging
import unicodedata

from config import settings
from renderer import render_all_pages
from vision import analyze_image
from prompts import (
    PRESENTATION_SLIDE_PROMPT,
    DRAWING_CLASSIFY_PROMPT,
    get_drawing_detail_prompt,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

http_client: httpx.AsyncClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=300.0)
    yield
    await http_client.aclose()


app = FastAPI(title="Vision Service", version="1.0.0", lifespan=lifespan)


# =============================================================================
# Models
# =============================================================================


class AnalyzeRequest(BaseModel):
    document_key: str  # e.g. "raw/drawing.pdf"


class SlideResult(BaseModel):
    page: int
    slide_type: str | None = None
    title: str | None = None
    description: str | None = None
    key_facts: list[str] = []
    has_image: bool | None = None
    image_description: str | None = None
    raw: dict = {}


class PresentationResponse(BaseModel):
    document_key: str
    pages: int
    slides: list[SlideResult]


class DrawingPageResult(BaseModel):
    page: int
    drawing_subtype: str = "other"
    confidence: str = "low"
    description: str | None = None
    details: dict = {}
    raw_classify: dict = {}
    raw_details: dict = {}


class DrawingResponse(BaseModel):
    document_key: str
    pages: int
    drawings: list[DrawingPageResult]


# =============================================================================
# Helpers
# =============================================================================


async def download_pdf(key: str) -> bytes:
    """Download PDF from storage, trying NFC and NFD unicode normalization."""
    for form in ("NFC", "NFD"):
        normalized_key = unicodedata.normalize(form, key)
        resp = await http_client.get(
            f"{settings.storage_service_url}/documents/{normalized_key}"
        )
        if resp.status_code == 200:
            return resp.content
    raise HTTPException(status_code=404, detail=f"Document not found: {key}")


# =============================================================================
# Endpoints
# =============================================================================


@app.get("/")
async def root():
    return {
        "service": "Vision Service",
        "version": "1.0.0",
        "provider": settings.vision_provider,
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/analyze/presentation", response_model=PresentationResponse)
async def analyze_presentation(req: AnalyzeRequest):
    """Analyze each slide of a presentation PDF."""
    logger.info(f"Analyzing presentation: {req.document_key}")

    pdf_bytes = await download_pdf(req.document_key)
    page_images = render_all_pages(pdf_bytes, settings.target_long_side)

    slides = []
    for i, img_bytes in enumerate(page_images):
        page_num = i + 1
        logger.info(f"Analyzing slide {page_num}/{len(page_images)}")

        try:
            result = await analyze_image(http_client, img_bytes, PRESENTATION_SLIDE_PROMPT)
        except Exception as e:
            logger.error(f"Failed to analyze slide {page_num}: {e}")
            result = {"error": str(e)}

        slides.append(SlideResult(
            page=page_num,
            slide_type=result.get("slide_type"),
            title=result.get("title"),
            description=result.get("description"),
            key_facts=result.get("key_facts", []),
            has_image=result.get("has_image"),
            image_description=result.get("image_description"),
            raw=result,
        ))

    logger.info(f"Presentation analysis complete: {len(slides)} slides")
    return PresentationResponse(
        document_key=req.document_key,
        pages=len(page_images),
        slides=slides,
    )


@app.post("/analyze/drawing", response_model=DrawingResponse)
async def analyze_drawing(req: AnalyzeRequest):
    """Analyze each page of a drawing PDF: classify subtype, then extract details."""
    logger.info(f"Analyzing drawing: {req.document_key}")

    pdf_bytes = await download_pdf(req.document_key)
    page_images = render_all_pages(pdf_bytes, settings.target_long_side)

    drawings = []
    for i, img_bytes in enumerate(page_images):
        page_num = i + 1
        logger.info(f"Analyzing drawing page {page_num}/{len(page_images)}")

        # Step 1: Classify drawing subtype
        try:
            classify_result = await analyze_image(
                http_client, img_bytes, DRAWING_CLASSIFY_PROMPT
            )
        except Exception as e:
            logger.error(f"Failed to classify drawing page {page_num}: {e}")
            classify_result = {"drawing_subtype": "other", "confidence": "low", "error": str(e)}

        subtype = classify_result.get("drawing_subtype", "other")
        confidence = classify_result.get("confidence", "low")
        logger.info(f"Page {page_num} classified as '{subtype}' (confidence: {confidence})")

        # Step 2: Extract details with subtype-specific prompt
        detail_prompt = get_drawing_detail_prompt(subtype)
        try:
            detail_result = await analyze_image(http_client, img_bytes, detail_prompt)
        except Exception as e:
            logger.error(f"Failed to extract details for page {page_num}: {e}")
            detail_result = {"error": str(e)}

        drawings.append(DrawingPageResult(
            page=page_num,
            drawing_subtype=subtype,
            confidence=confidence,
            description=detail_result.get("description"),
            details=detail_result,
            raw_classify=classify_result,
            raw_details=detail_result,
        ))

    logger.info(f"Drawing analysis complete: {len(drawings)} pages")
    return DrawingResponse(
        document_key=req.document_key,
        pages=len(page_images),
        drawings=drawings,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8009)
