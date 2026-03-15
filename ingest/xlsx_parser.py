"""Excel spreadsheet parser — extracts data and statistics from .xlsx files."""

from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd


@dataclass
class ParsedSpreadsheet:
    filename: str
    sheets: dict = field(default_factory=dict)  # sheet_name -> DataFrame
    summary_stats: dict = field(default_factory=dict)  # sheet_name -> stats dict


def parse_xlsx(path: Path) -> ParsedSpreadsheet:
    """Extract data and compute statistics from Excel spreadsheet."""
    sheets = {}
    summary_stats = {}

    xlsx = pd.ExcelFile(path)
    for sheet_name in xlsx.sheet_names:
        df = pd.read_excel(xlsx, sheet_name=sheet_name)
        sheets[sheet_name] = df

        # Generate summary statistics for numeric columns
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        if numeric_cols:
            stats = {}
            for col in numeric_cols:
                col_data = df[col].dropna()
                if len(col_data) > 0:
                    stats[col] = {
                        "count": int(col_data.count()),
                        "sum": round(float(col_data.sum()), 2),
                        "mean": round(float(col_data.mean()), 2),
                        "median": round(float(col_data.median()), 2),
                        "min": round(float(col_data.min()), 2),
                        "max": round(float(col_data.max()), 2),
                        "std": round(float(col_data.std()), 2) if len(col_data) > 1 else 0,
                    }
            summary_stats[sheet_name] = stats

    return ParsedSpreadsheet(
        filename=path.name,
        sheets=sheets,
        summary_stats=summary_stats,
    )
