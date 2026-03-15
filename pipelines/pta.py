"""Pattern, Trend, Anomaly (PTA) Detection Pipeline.

Analyzes document sets for recurring patterns, directional trends,
and statistical anomalies.
"""

from pathlib import Path

import pandas as pd
import numpy as np

from ingest.discovery import FileType
from ingest.chunker import chunk_content
from analyze.strategies import execute as llm_execute
from analyze.prompts import PTA_DETECTION
from pipelines.base import BasePipeline, PipelineResult


class PTAPipeline(BasePipeline):
    name = "pta"
    description = "Detect patterns, trends, and anomalies across documents"
    accepted_types = [FileType.XLSX, FileType.CSV, FileType.DOCX, FileType.PDF]

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

        # Run local anomaly detection on numeric data
        anomaly_report = self._detect_anomalies(parsed)

        # Build content for LLM
        chunk_result = chunk_content(parsed)
        default_instruction = (
            "Detect patterns, trends, and anomalies across all documents. "
            "Flag outliers and unexpected values."
        )
        full_instruction = instruction or default_instruction

        # Try LLM analysis
        try:
            llm_result = llm_execute(chunk_result, full_instruction, folder_path, model)
            output = f"# Pattern / Trend / Anomaly Report\n\n{llm_result}"
        except Exception as e:
            output = f"# Pattern / Trend / Anomaly Report\n\n"
            output += f"*LLM analysis unavailable: {e}*\n\n"

        # Always append local anomaly detection
        if anomaly_report:
            output += f"\n\n## Statistical Anomaly Detection\n\n{anomaly_report}"

        return PipelineResult(
            pipeline_name=self.name,
            success=True,
            output=output,
            files_processed=len(parsed),
            errors=errors,
            metadata={"total_tokens": chunk_result.total_tokens, "anomalies_found": anomaly_report.count("ANOMALY:") if anomaly_report else 0},
        )

    def _detect_anomalies(self, parsed_docs: list) -> str:
        """Detect statistical anomalies using IQR method on numeric data."""
        sections = []

        for doc in parsed_docs:
            frames = {}
            if hasattr(doc, "sheets"):
                for sheet_name, df in doc.sheets.items():
                    frames[f"{doc.filename} / {sheet_name}"] = df
            elif hasattr(doc, "data") and hasattr(doc.data, "select_dtypes"):
                frames[doc.filename] = doc.data

            for source_name, df in frames.items():
                numeric_cols = df.select_dtypes(include="number").columns.tolist()
                if not numeric_cols:
                    continue

                anomalies = []
                trends = []
                patterns = []

                for col in numeric_cols:
                    series = df[col].dropna()
                    if len(series) < 3:
                        continue

                    mean = series.mean()
                    std = series.std()
                    q1 = series.quantile(0.25)
                    q3 = series.quantile(0.75)
                    iqr = q3 - q1
                    lower = q1 - 1.5 * iqr
                    upper = q3 + 1.5 * iqr

                    # Anomalies: values outside IQR bounds
                    outliers = series[(series < lower) | (series > upper)]
                    if len(outliers) > 0:
                        for idx, val in outliers.items():
                            anomalies.append(
                                f"- ANOMALY: **{col}** row {idx}: value {val:,.2f} "
                                f"(bounds: {lower:,.2f} — {upper:,.2f})"
                            )

                    # Trends: check if series is monotonically increasing/decreasing
                    if len(series) >= 4:
                        diffs = series.diff().dropna()
                        pos = (diffs > 0).sum()
                        neg = (diffs < 0).sum()
                        total = len(diffs)
                        if pos / total > 0.8:
                            trends.append(f"- TREND UP: **{col}**: upward trend ({pos}/{total} increases)")
                        elif neg / total > 0.8:
                            trends.append(f"- TREND DOWN: **{col}**: downward trend ({neg}/{total} decreases)")

                    # Patterns: check for repeated values
                    value_counts = series.value_counts()
                    repeated = value_counts[value_counts > 1]
                    if len(repeated) > 0 and len(repeated) < len(series) * 0.5:
                        top = repeated.head(3)
                        for val, count in top.items():
                            patterns.append(f"- PATTERN: **{col}**: value {val:,.2f} repeats {count} times")

                if anomalies or trends or patterns:
                    section = f"### {source_name}\n\n"
                    if anomalies:
                        section += "**Anomalies:**\n" + "\n".join(anomalies) + "\n\n"
                    if trends:
                        section += "**Trends:**\n" + "\n".join(trends) + "\n\n"
                    if patterns:
                        section += "**Patterns:**\n" + "\n".join(patterns) + "\n\n"
                    sections.append(section)

        if not sections:
            return "No anomalies, trends, or patterns detected in numeric data."

        return "\n".join(sections)
