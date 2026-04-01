import pymupdf
import logging

logger = logging.getLogger(__name__)


def render_page(pdf_bytes: bytes, page_index: int, target_long_side: int = 4096) -> bytes:
    """Render a single page of PDF to PNG, scaling to target_long_side pixels."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    page = doc[page_index]
    rect = page.rect
    long_side = max(rect.width, rect.height)
    zoom = target_long_side / long_side
    mat = pymupdf.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    png_bytes = pix.tobytes("png")
    logger.info(f"Rendered page {page_index + 1}: {pix.width}x{pix.height}px ({len(png_bytes) // 1024}KB)")
    doc.close()
    return png_bytes


def render_all_pages(pdf_bytes: bytes, target_long_side: int = 4096) -> list[bytes]:
    """Render all pages of a PDF to PNG images."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    doc.close()

    pages = []
    for i in range(page_count):
        pages.append(render_page(pdf_bytes, i, target_long_side))
    logger.info(f"Rendered {len(pages)} pages")
    return pages


def get_page_count(pdf_bytes: bytes) -> int:
    """Get the number of pages in a PDF."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    count = len(doc)
    doc.close()
    return count
