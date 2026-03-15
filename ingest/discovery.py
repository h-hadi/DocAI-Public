"""File discovery — walk a folder and classify files by type."""

from pathlib import Path
from dataclasses import dataclass
from enum import Enum


class FileType(Enum):
    DOCX = "docx"
    XLSX = "xlsx"
    CSV = "csv"
    IMAGE = "image"
    PDF = "pdf"
    UNKNOWN = "unknown"


@dataclass
class DiscoveredFile:
    path: Path
    file_type: FileType
    size_bytes: int
    name: str


EXTENSION_MAP = {
    ".docx": FileType.DOCX,
    ".xlsx": FileType.XLSX,
    ".xls": FileType.XLSX,
    ".csv": FileType.CSV,
    ".png": FileType.IMAGE,
    ".jpg": FileType.IMAGE,
    ".jpeg": FileType.IMAGE,
    ".tiff": FileType.IMAGE,
    ".tif": FileType.IMAGE,
    ".bmp": FileType.IMAGE,
    ".pdf": FileType.PDF,
}


def discover_files(folder: Path) -> list[DiscoveredFile]:
    """Walk folder recursively and classify all processable files."""
    files = []
    for path in sorted(folder.rglob("*")):
        if path.is_file() and not path.name.startswith(".") and not path.name.startswith("~$"):
            ext = path.suffix.lower()
            file_type = EXTENSION_MAP.get(ext, FileType.UNKNOWN)
            if file_type != FileType.UNKNOWN:
                files.append(
                    DiscoveredFile(
                        path=path,
                        file_type=file_type,
                        size_bytes=path.stat().st_size,
                        name=path.name,
                    )
                )
    return files
