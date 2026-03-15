"""Image text extraction — uses Gemini 2.5 vision for OCR."""

import base64
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI
from config import settings


@dataclass
class ParsedImage:
    filename: str
    text: str
    confidence: float


# Supported image MIME types
_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

OCR_MODEL = "gemini-2.5-pro"

OCR_SYSTEM_PROMPT = (
    "You are a document text extraction specialist. "
    "Extract ALL text from this image exactly as it appears — "
    "preserve layout, line breaks, paragraphs, tables, and formatting. "
    "If the document is handwritten, do your best to read every word. "
    "If text is in a non-English language (Arabic, Farsi, etc.), "
    "extract it in the original script. "
    "Output ONLY the extracted text, nothing else."
)


def parse_image(path: Path) -> ParsedImage:
    """Extract text from image using Gemini 2.5 vision API."""
    settings.require_api_key()

    # Read and encode image
    image_bytes = path.read_bytes()
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    ext = path.suffix.lower()
    mime_type = _MIME_TYPES.get(ext, "image/png")

    # Call Gemini 2.5 with vision
    client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)

    response = client.chat.completions.create(
        model=OCR_MODEL,
        messages=[
            {"role": "system", "content": OCR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{b64_image}",
                        },
                    },
                    {
                        "type": "text",
                        "text": "Extract all text from this document image.",
                    },
                ],
            },
        ],
        temperature=0.1,
        max_tokens=8192,
    )

    text = response.choices[0].message.content.strip()

    # Gemini vision doesn't return a confidence score,
    # so estimate based on response quality
    confidence = 95.0 if len(text) > 20 else (50.0 if text else 0.0)

    return ParsedImage(
        filename=path.name,
        text=text,
        confidence=confidence,
    )
