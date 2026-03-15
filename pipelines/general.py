"""General Q&A Pipeline.

Drop any documents and ask any question — the universal pipeline
for ad-hoc analysis, executive summaries, context-based Q&A,
and any instruction that doesn't fit a specialized pipeline.
"""

from pathlib import Path

from ingest.discovery import FileType
from ingest.chunker import chunk_content, format_document
from analyze.strategies import execute as llm_execute
from analyze.prompts import GENERAL
from pipelines.base import BasePipeline, PipelineResult


class GeneralPipeline(BasePipeline):
    name = "general"
    description = "Ask any question about any documents — universal Q&A"
    accepted_types = [FileType.DOCX, FileType.XLSX, FileType.CSV, FileType.IMAGE, FileType.PDF]

    def execute(self, folder_path: str, instruction: str = "", model: str | None = None) -> PipelineResult:
        folder = Path(folder_path)
        if not folder.exists():
            return PipelineResult(
                pipeline_name=self.name, success=False,
                output=f"Folder not found: {folder_path}",
            )

        parsed, errors = self.discover_and_parse(folder)
        if not parsed:
            return PipelineResult(
                pipeline_name=self.name, success=False,
                output="No processable files found in folder.",
                errors=errors,
            )

        # Build local document overview
        local_overview = self._build_overview(parsed)

        # Build content for LLM
        chunk_result = chunk_content(parsed)
        default_instruction = (
            "Analyze these documents and provide key findings, "
            "relevant statistics, and a summary."
        )
        full_instruction = instruction or default_instruction

        # Try LLM analysis
        try:
            llm_result = llm_execute(chunk_result, full_instruction, folder_path, model)
            output = f"# Analysis\n\n{llm_result}"
        except Exception as e:
            output = f"# Analysis\n\n"
            output += f"*LLM analysis unavailable: {e}*\n\n"
            output += "## Document Overview\n\n"

        # Always append local overview
        if local_overview:
            output += f"\n\n## Document Inventory\n\n{local_overview}"

        return PipelineResult(
            pipeline_name=self.name,
            success=True,
            output=output,
            files_processed=len(parsed),
            errors=errors,
            metadata={
                "total_tokens": chunk_result.total_tokens,
                "strategy": "single-shot" if chunk_result.fits_single_shot else "map-reduce",
            },
        )

    def _build_overview(self, parsed_docs: list) -> str:
        """Build a document inventory table."""
        rows = ["| # | Document | Type | Size |", "| --- | --- | --- | --- |"]

        for i, doc in enumerate(parsed_docs, 1):
            name = getattr(doc, "filename", "Unknown")

            if hasattr(doc, "sheets"):
                total_rows = sum(len(df) for df in doc.sheets.values())
                doc_type = "Excel"
                size = f"{len(doc.sheets)} sheets, {total_rows:,} rows"
            elif hasattr(doc, "tables"):
                words = len(doc.text.split())
                doc_type = "Word"
                size = f"{words:,} words"
            elif hasattr(doc, "page_count"):
                words = len(doc.text.split())
                doc_type = "PDF"
                size = f"{doc.page_count} pages, {words:,} words"
            elif hasattr(doc, "confidence"):
                words = len(doc.text.split())
                doc_type = "Image (OCR)"
                size = f"{words:,} words, {doc.confidence:.0f}% confidence"
            elif hasattr(doc, "data"):
                doc_type = "CSV"
                size = f"{len(doc.data):,} rows"
            else:
                doc_type = "Unknown"
                size = "—"

            rows.append(f"| {i} | {name} | {doc_type} | {size} |")

        return "\n".join(rows)
