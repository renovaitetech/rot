import pymupdf4llm
import pymupdf
import tempfile
import logging

logger = logging.getLogger(__name__)


def parse_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF as Markdown using pymupdf4llm."""
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        md_text = pymupdf4llm.to_markdown(tmp.name)
    return md_text


def generate_thumbnails(pdf_bytes: bytes, width: int = 300) -> list[bytes]:
    """Render each page of a PDF as a PNG thumbnail."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    thumbnails = []
    for page in doc:
        zoom = width / page.rect.width
        mat = pymupdf.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        thumbnails.append(pix.tobytes("png"))
    doc.close()
    return thumbnails
