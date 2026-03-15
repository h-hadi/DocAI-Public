"""CSV parser — extracts data and statistics from .csv files."""

from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd


@dataclass
class ParsedCSV:
    filename: str
    data: object = None  # pd.DataFrame
    summary_stats: dict = field(default_factory=dict)


def parse_csv(path: Path) -> ParsedCSV:
    """Extract data and compute statistics from CSV file."""
    df = pd.read_csv(path)
    summary_stats = {}

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if numeric_cols:
        for col in numeric_cols:
            col_data = df[col].dropna()
            if len(col_data) > 0:
                summary_stats[col] = {
                    "count": int(col_data.count()),
                    "sum": round(float(col_data.sum()), 2),
                    "mean": round(float(col_data.mean()), 2),
                    "median": round(float(col_data.median()), 2),
                    "min": round(float(col_data.min()), 2),
                    "max": round(float(col_data.max()), 2),
                }

    return ParsedCSV(
        filename=path.name,
        data=df,
        summary_stats=summary_stats,
    )
