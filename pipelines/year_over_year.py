"""Year-over-Year Financial Comparison Pipeline.

Compares financial data across multiple Excel/Word files, producing
comparison tables with absolute and percentage changes.
"""

from pathlib import Path

import pandas as pd

from ingest.discovery import FileType
from ingest.chunker import chunk_content, format_document
from analyze.strategies import execute as llm_execute
from analyze.prompts import FINANCIAL_COMPARISON
from pipelines.base import BasePipeline, PipelineResult


class YearOverYearPipeline(BasePipeline):
    name = "year_over_year"
    description = "Compare financials across multiple Excel/Word files"
    accepted_types = [FileType.XLSX, FileType.CSV, FileType.DOCX]

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
                output="No Excel, CSV, or Word files found in folder.",
                errors=errors,
            )

        # Build local comparison table from spreadsheet data
        local_comparison = self._build_comparison_table(parsed)

        # Build content for LLM
        chunk_result = chunk_content(parsed)
        default_instruction = (
            "Compare year-over-year financials. Show a comparison table with "
            "absolute and percentage changes. Highlight anomalies > 20%."
        )
        full_instruction = instruction or default_instruction

        # Try LLM analysis, fall back to local-only
        try:
            llm_result = llm_execute(chunk_result, full_instruction, folder_path, model)
            output = f"# Year-over-Year Financial Comparison\n\n{llm_result}"
        except Exception as e:
            output = f"# Year-over-Year Financial Comparison\n\n"
            output += f"*LLM analysis unavailable: {e}*\n\n"
            output += "## Local Statistical Comparison\n\n"

        # Always append local comparison data
        if local_comparison:
            output += f"\n\n## Data Comparison Table\n\n{local_comparison}"

        return PipelineResult(
            pipeline_name=self.name,
            success=True,
            output=output,
            files_processed=len(parsed),
            errors=errors,
            metadata={"total_tokens": chunk_result.total_tokens, "strategy": "single-shot" if chunk_result.fits_single_shot else "map-reduce"},
        )

    def _build_comparison_table(self, parsed_docs: list) -> str:
        """Build a markdown comparison table from spreadsheet numeric columns."""
        all_data = {}

        for doc in parsed_docs:
            if hasattr(doc, "sheets"):
                for sheet_name, df in doc.sheets.items():
                    label = f"{doc.filename}"
                    if len(doc.sheets) > 1:
                        label += f" / {sheet_name}"
                    numeric = df.select_dtypes(include="number")
                    if not numeric.empty:
                        all_data[label] = {col: numeric[col].sum() for col in numeric.columns}
            elif hasattr(doc, "data") and hasattr(doc.data, "select_dtypes"):
                numeric = doc.data.select_dtypes(include="number")
                if not numeric.empty:
                    all_data[doc.filename] = {col: numeric[col].sum() for col in numeric.columns}

        if len(all_data) < 2:
            return ""

        # Build comparison table
        sources = list(all_data.keys())
        all_metrics = set()
        for data in all_data.values():
            all_metrics.update(data.keys())

        lines = ["| Metric | " + " | ".join(sources) + " | Change | % Change |"]
        lines.append("| --- | " + " | ".join(["---"] * len(sources)) + " | --- | --- |")

        for metric in sorted(all_metrics):
            values = [all_data[s].get(metric, 0) for s in sources]
            row = f"| {metric} | " + " | ".join(f"{v:,.2f}" for v in values)

            # Calculate change between first and last
            if len(values) >= 2 and values[0] != 0:
                change = values[-1] - values[0]
                pct = (change / abs(values[0])) * 100
                flag = " **ANOMALY**" if abs(pct) > 20 else ""
                row += f" | {change:+,.2f} | {pct:+.1f}%{flag} |"
            else:
                row += " | — | — |"

            lines.append(row)

        return "\n".join(lines)
