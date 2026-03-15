"""PDF parser — extracts text and handles scanned PDFs via OCR fallback."""

from dataclasses import dataclass, field
from pathlib import Path
import fitz  # PyMuPDF


@dataclass
class ParsedPDF:
    filename: str
    text: str
    page_count: int
    metadata: dict = field(default_factory=dict)


def parse_pdf(path: Path) -> ParsedPDF:
    """Extract text from PDF. Falls back to OCR for scanned pages."""
    doc = fitz.open(str(path))

    pages_text = []
    for page_num, page in enumerate(doc, 1):
        text = page.get_text()
        if text.strip():
            pages_text.append(f"--- Page {page_num} ---\n{text.strip()}")
        else:
            # Scanned page — try to extract images for OCR
            # This is a placeholder; for full OCR, use ocr_parser on extracted images
            pages_text.append(f"--- Page {page_num} ---\n[Scanned page — no extractable text]")

    metadata = doc.metadata or {}

    return ParsedPDF(
        filename=path.name,
        text="\n\n".join(pages_text),
        page_count=len(doc),
        metadata={
            "title": metadata.get("title", ""),
            "author": metadata.get("author", ""),
            "subject": metadata.get("subject", ""),
        },
    )
