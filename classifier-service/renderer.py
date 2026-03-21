import pymupdf
import logging

logger = logging.getLogger(__name__)


def render_first_page(pdf_bytes: bytes, target_long_side: int = 2048) -> bytes:
    """Render first page of PDF to PNG, scaling to target_long_side pixels."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    rect = page.rect
    long_side = max(rect.width, rect.height)
    zoom = target_long_side / long_side
    mat = pymupdf.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    png_bytes = pix.tobytes("png")
    logger.info(f"Rendered first page: {pix.width}x{pix.height}px ({len(png_bytes) // 1024}KB)")
    doc.close()
    return png_bytes
