"""Base pipeline class — all pipelines inherit from this."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ingest.discovery import discover_files, FileType, DiscoveredFile
from ingest.docx_parser import parse_docx
from ingest.xlsx_parser import parse_xlsx
from ingest.csv_parser import parse_csv
from ingest.ocr_parser import parse_image
from ingest.pdf_parser import parse_pdf
from ingest.chunker import chunk_content, format_document


PARSERS = {
    FileType.DOCX: parse_docx,
    FileType.XLSX: parse_xlsx,
    FileType.CSV: parse_csv,
    FileType.IMAGE: parse_image,
    FileType.PDF: parse_pdf,
}


@dataclass
class PipelineResult:
    """Standard output from any pipeline."""
    pipeline_name: str
    success: bool
    output: str  # Markdown-formatted result
    files_processed: int = 0
    errors: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class BasePipeline:
    """Base class for all DocAI pipelines."""

    name: str = "base"
    description: str = "Base pipeline"
    accepted_types: list[FileType] = list(FileType)

    def discover_and_parse(self, folder: Path) -> tuple[list[Any], list[str]]:
        """Discover and parse files from folder, filtering by accepted types."""
        files = discover_files(folder)
        filtered = [f for f in files if f.file_type in self.accepted_types]

        parsed = []
        errors = []
        for f in filtered:
            parser_fn = PARSERS.get(f.file_type)
            if parser_fn:
                try:
                    parsed.append(parser_fn(f.path))
                except Exception as e:
                    errors.append(f"{f.name}: {e}")

        return parsed, errors

    def execute(self, folder_path: str, instruction: str = "", model: str | None = None) -> PipelineResult:
        """Run the pipeline. Override in subclasses."""
        raise NotImplementedError
