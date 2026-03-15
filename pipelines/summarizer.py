"""Document Summarizer Pipeline.

Summarizes Word/PDF documents into structured summaries with key themes.
"""

from pathlib import Path

from ingest.discovery import FileType
from ingest.chunker import chunk_content, format_document
from analyze.strategies import execute as llm_execute
from analyze.prompts import SUMMARIZATION
from pipelines.base import BasePipeline, PipelineResult


class SummarizerPipeline(BasePipeline):
    name = "summarizer"
    description = "Summarize Word/PDF documents with key themes"
    accepted_types = [FileType.DOCX, FileType.PDF, FileType.CSV, FileType.XLSX]

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
                output="No Word or PDF files found in folder.",
                errors=errors,
            )

        # Build local summary (key stats per document)
        local_summary = self._build_local_summary(parsed)

        # Build content for LLM
        chunk_result = chunk_content(parsed)
        default_instruction = (
            "Summarize all documents. For each document provide key points. "
            "Then provide a cross-document synthesis identifying common themes."
        )
        full_instruction = instruction or default_instruction

        # Try LLM analysis
        try:
            llm_result = llm_execute(chunk_result, full_instruction, folder_path, model)
            output = f"# Document Summary\n\n{llm_result}"
        except Exception as e:
            output = f"# Document Summary\n\n"
            output += f"*LLM analysis unavailable: {e}*\n\n"
            output += "## Local Document Overview\n\n"

        # Always append local summary
        if local_summary:
            output += f"\n\n## Document Overview\n\n{local_summary}"

        return PipelineResult(
            pipeline_name=self.name,
            success=True,
            output=output,
            files_processed=len(parsed),
            errors=errors,
            metadata={"total_tokens": chunk_result.total_tokens},
        )

    def _build_local_summary(self, parsed_docs: list) -> str:
        """Build a local summary without LLM — document stats and structure."""
        sections = []

        for doc in parsed_docs:
            name = getattr(doc, "filename", "Unknown")

            if hasattr(doc, "text") and hasattr(doc, "tables"):
                # Word document
                word_count = len(doc.text.split())
                para_count = doc.text.count("\n\n") + 1
                table_count = len(doc.tables) if doc.tables else 0
                section = f"### {name}\n"
                section += f"- **Words:** {word_count:,}\n"
                section += f"- **Paragraphs:** {para_count}\n"
                section += f"- **Tables:** {table_count}\n"
                if doc.metadata:
                    if doc.metadata.get("author"):
                        section += f"- **Author:** {doc.metadata['author']}\n"
                    if doc.metadata.get("title"):
                        section += f"- **Title:** {doc.metadata['title']}\n"
                # Extract first 200 chars as preview
                preview = doc.text[:200].strip()
                if preview:
                    section += f"- **Preview:** {preview}...\n"
                sections.append(section)

            elif hasattr(doc, "page_count"):
                # PDF
                word_count = len(doc.text.split())
                section = f"### {name}\n"
                section += f"- **Pages:** {doc.page_count}\n"
                section += f"- **Words:** {word_count:,}\n"
                preview = doc.text[:200].strip()
                if preview:
                    section += f"- **Preview:** {preview}...\n"
                sections.append(section)

            elif hasattr(doc, "sheets"):
                # Spreadsheet
                total_rows = sum(len(df) for df in doc.sheets.values())
                section = f"### {name}\n"
                section += f"- **Sheets:** {len(doc.sheets)}\n"
                section += f"- **Total rows:** {total_rows:,}\n"
                for sheet_name, df in doc.sheets.items():
                    section += f"- **{sheet_name}:** {len(df)} rows, {len(df.columns)} columns\n"
                sections.append(section)

        return "\n".join(sections) if sections else ""
