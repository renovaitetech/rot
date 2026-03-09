from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
import httpx
import logging
from pathlib import PurePosixPath

from config import settings
from parser import parse_pdf, generate_thumbnails

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

http_client: httpx.AsyncClient = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(base_url=settings.storage_service_url, timeout=120.0)
    yield
    await http_client.aclose()


app = FastAPI(title="Parser Service", version="1.0.0", lifespan=lifespan)


class ParseRequest(BaseModel):
    key: str  # e.g. "raw/document.pdf"


class ParseResponse(BaseModel):
    markdown_key: str
    thumbnails: list[str]
    pages: int


@app.get("/")
async def root():
    return {"service": "Parser Service", "version": "1.0.0", "status": "operational"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/parse", response_model=ParseResponse)
async def parse_document(req: ParseRequest):
    """Download PDF from storage, parse to Markdown, generate thumbnails, save all back."""
    # Download PDF from storage-service
    logger.info(f"Downloading {req.key} from storage-service")
    resp = await http_client.get(f"/documents/{req.key}")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Document not found: {req.key}")
    resp.raise_for_status()
    pdf_bytes = resp.content

    # Derive base filename (without extension)
    filename = PurePosixPath(req.key).stem  # "raw/document.pdf" -> "document"

    # Parse PDF to Markdown
    logger.info(f"Parsing {req.key} ({len(pdf_bytes)} bytes)")
    md_text = parse_pdf(pdf_bytes)

    # Upload Markdown
    markdown_key = f"markdown/{filename}.md"
    logger.info(f"Uploading {markdown_key}")
    upload_resp = await http_client.post(
        "/documents/upload",
        params={"prefix": "markdown"},
        files={"file": (f"{filename}.md", md_text.encode("utf-8"), "text/markdown")},
    )
    upload_resp.raise_for_status()

    # Generate and upload thumbnails
    logger.info(f"Generating thumbnails for {req.key}")
    thumb_images = generate_thumbnails(pdf_bytes)
    thumbnail_keys = []

    for i, png_bytes in enumerate(thumb_images):
        thumb_filename = f"{filename}_page_{i + 1}.png"
        logger.info(f"Uploading thumbnail {thumb_filename}")
        t_resp = await http_client.post(
            "/documents/upload",
            params={"prefix": f"thumbnails/{filename}"},
            files={"file": (thumb_filename, png_bytes, "image/png")},
        )
        t_resp.raise_for_status()
        thumbnail_keys.append(f"thumbnails/{filename}/{thumb_filename}")

    logger.info(f"Done: {markdown_key}, {len(thumbnail_keys)} thumbnails")
    return ParseResponse(
        markdown_key=markdown_key,
        thumbnails=thumbnail_keys,
        pages=len(thumbnail_keys),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
