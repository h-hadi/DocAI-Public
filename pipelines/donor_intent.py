"""Donor Intent Extraction Pipeline.

Processes scanned images and PDFs through OCR, then extracts
donor intent classification from historical gift correspondence.
"""

from pathlib import Path

from ingest.discovery import FileType, discover_files
from ingest.ocr_parser import parse_image
from ingest.pdf_parser import parse_pdf
from ingest.docx_parser import parse_docx
from ingest.chunker import chunk_content, format_document
from analyze.strategies import execute as llm_execute
from analyze.prompts import DONOR_INTENT
from pipelines.base import BasePipeline, PipelineResult, PARSERS


class DonorIntentPipeline(BasePipeline):
    name = "donor_intent"
    description = "OCR + donor intent extraction from scanned correspondence"
    accepted_types = [FileType.IMAGE, FileType.PDF, FileType.DOCX]

    def execute(self, folder_path: str, instruction: str = "", model: str | None = None) -> PipelineResult:
        folder = Path(folder_path)
        if not folder.exists():
            return PipelineResult(
                pipeline_name=self.name, success=False,
                output=f"Folder not found: {folder_path}",
            )

        # Discover and parse with OCR
        files = discover_files(folder)
        filtered = [f for f in files if f.file_type in self.accepted_types]

        if not filtered:
            return PipelineResult(
                pipeline_name=self.name, success=False,
                output="No images, PDFs, or Word files found in folder.",
            )

        parsed = []
        errors = []
        ocr_results = []

        for f in filtered:
            try:
                if f.file_type == FileType.IMAGE:
                    doc = parse_image(f.path)
                    ocr_results.append({
                        "file": f.name,
                        "text": doc.text,
                        "confidence": doc.confidence,
                    })
                    parsed.append(doc)
                elif f.file_type == FileType.PDF:
                    doc = parse_pdf(f.path)
                    parsed.append(doc)
                elif f.file_type == FileType.DOCX:
                    doc = parse_docx(f.path)
                    parsed.append(doc)
            except Exception as e:
                errors.append(f"{f.name}: {e}")

        if not parsed:
            return PipelineResult(
                pipeline_name=self.name, success=False,
                output="Could not parse any files.",
                errors=errors,
            )

        # Build OCR report
        ocr_report = self._build_ocr_report(ocr_results)

        # Build content for LLM
        chunk_result = chunk_content(parsed)
        default_instruction = (
            "Extract donor intent from these historical gift correspondence documents. "
            "Identify donors, gifts, stated and implied intent, restrictions, and confidence level."
        )
        full_instruction = instruction or default_instruction

        # Try LLM analysis
        try:
            llm_result = llm_execute(chunk_result, full_instruction, folder_path, model)
            output = f"# Donor Intent Extraction\n\n{llm_result}"
        except Exception as e:
            output = f"# Donor Intent Extraction\n\n"
            output += f"*LLM analysis unavailable: {e}*\n\n"

        # Always append OCR report
        if ocr_report:
            output += f"\n\n## OCR Extraction Results\n\n{ocr_report}"

        return PipelineResult(
            pipeline_name=self.name,
            success=True,
            output=output,
            files_processed=len(parsed),
            errors=errors,
            metadata={
                "total_tokens": chunk_result.total_tokens,
                "ocr_files": len(ocr_results),
                "avg_confidence": (
                    sum(r["confidence"] for r in ocr_results) / len(ocr_results)
                    if ocr_results else 0
                ),
            },
        )

    def _build_ocr_report(self, ocr_results: list[dict]) -> str:
        """Build a report of OCR extraction results."""
        if not ocr_results:
            return ""

        sections = []
        for r in ocr_results:
            section = f"### {r['file']}\n"
            section += f"- **OCR Confidence:** {r['confidence']:.0f}%\n"
            section += f"- **Extracted Text:**\n\n"
            # Show full text in blockquote
            text_lines = r["text"].split("\n")
            for line in text_lines[:50]:  # Limit display
                section += f"> {line}\n"
            if len(text_lines) > 50:
                section += f"\n*({len(text_lines) - 50} more lines truncated)*\n"
            sections.append(section)

        return "\n\n".join(sections)
