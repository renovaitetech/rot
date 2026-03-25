import re
import pymupdf4llm
import tempfile
import logging

logger = logging.getLogger(__name__)


def parse_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF as Markdown using pymupdf4llm."""
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        md_text = pymupdf4llm.to_markdown(tmp.name)

    # Replace page break markers (-----) with <!-- Page N --> comments
    page_num = 1
    def _replace_page_break(match):
        nonlocal page_num
        page_num += 1
        return f"<!-- Page {page_num} -->"
    md_text = re.sub(r'\n-----\n', lambda m: f"\n{_replace_page_break(m)}\n", md_text)

    # Remove trailing page marker and whitespace
    md_text = re.sub(r'\s*<!-- Page \d+ -->\s*$', '\n', md_text)

    return md_text
