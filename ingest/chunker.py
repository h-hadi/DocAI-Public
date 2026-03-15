"""Chunker — token counting, content formatting, and chunking strategy."""

from dataclasses import dataclass, field
from typing import Any
import tiktoken


@dataclass
class ContentChunk:
    source: str
    content: str
    tokens: int


@dataclass
class ChunkResult:
    total_tokens: int
    fits_single_shot: bool
    chunks: list[ContentChunk] = field(default_factory=list)


def _df_to_text(df) -> str:
    """Convert a DataFrame to a markdown table without requiring tabulate."""
    if df is None or len(df) == 0:
        return "(empty)"
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    rows = []
    # Limit to first 100 rows to avoid massive prompts
    for _, row in df.head(100).iterrows():
        cells = " | ".join(str(row[c]) if str(row[c]) != "nan" else "" for c in cols)
        rows.append(f"| {cells} |")
    result = "\n".join([header, sep] + rows)
    if len(df) > 100:
        result += f"\n\n*(Showing first 100 of {len(df)} rows)*"
    return result


def format_document(doc: Any) -> str:
    """Convert any parsed document type to a text representation for the LLM."""
    # Spreadsheet (xlsx)
    if hasattr(doc, "sheets"):
        parts = [f"## Spreadsheet: {doc.filename}\n"]
        for sheet_name, df in doc.sheets.items():
            parts.append(f"### Sheet: {sheet_name}")
            parts.append(_df_to_text(df))
            if sheet_name in doc.summary_stats:
                stats = doc.summary_stats[sheet_name]
                parts.append(f"\n**Statistics:**")
                for col, s in stats.items():
                    parts.append(f"- {col}: mean={s['mean']}, median={s['median']}, min={s['min']}, max={s['max']}, sum={s['sum']}")
        return "\n".join(parts)

    # Word document
    if hasattr(doc, "tables"):
        parts = [f"## Document: {doc.filename}\n", doc.text]
        for i, table in enumerate(doc.tables):
            parts.append(f"\n**Table {i + 1}:**")
            if table:
                header = " | ".join(table[0])
                separator = " | ".join(["---"] * len(table[0]))
                parts.append(f"| {header} |")
                parts.append(f"| {separator} |")
                for row in table[1:]:
                    parts.append(f"| {' | '.join(row)} |")
        return "\n".join(parts)

    # CSV
    if hasattr(doc, "data") and hasattr(doc.data, "columns"):
        parts = [f"## CSV: {doc.filename}\n"]
        parts.append(_df_to_text(doc.data))
        if doc.summary_stats:
            parts.append("\n**Statistics:**")
            for col, s in doc.summary_stats.items():
                parts.append(f"- {col}: mean={s['mean']}, median={s['median']}, min={s['min']}, max={s['max']}")
        return "\n".join(parts)

    # OCR image
    if hasattr(doc, "confidence"):
        return f"## OCR Image: {doc.filename} (confidence: {doc.confidence:.0f}%)\n\n{doc.text}"

    # PDF
    if hasattr(doc, "page_count"):
        return f"## PDF: {doc.filename} ({doc.page_count} pages)\n\n{doc.text}"

    # Fallback
    return f"## {getattr(doc, 'filename', 'Unknown')}\n\n{getattr(doc, 'text', str(doc))}"


def chunk_content(
    parsed_docs: list,
    model: str = "gpt-4o",
    max_context: int = 100_000,
) -> ChunkResult:
    """Count tokens across all docs and decide single-shot vs map-reduce."""
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")

    chunks = []
    total_tokens = 0

    for doc in parsed_docs:
        content = format_document(doc)
        tokens = len(enc.encode(content))
        total_tokens += tokens
        chunks.append(ContentChunk(source=doc.filename, content=content, tokens=tokens))

    return ChunkResult(
        total_tokens=total_tokens,
        fits_single_shot=total_tokens < max_context,
        chunks=chunks,
    )
