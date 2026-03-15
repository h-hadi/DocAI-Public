"""Data visualizer — generates charts and plots from parsed spreadsheet data."""

import io
import base64
from pathlib import Path
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def create_summary_dashboard(parsed_docs: list) -> str | None:
    """Create an HTML dashboard summarizing all parsed data.

    Returns HTML string with embedded Plotly charts, or None if no numeric data.
    """
    all_stats = {}
    all_dataframes = {}

    for doc in parsed_docs:
        # Spreadsheet
        if hasattr(doc, "sheets"):
            for sheet_name, df in doc.sheets.items():
                key = f"{doc.filename} / {sheet_name}"
                all_dataframes[key] = df
                if sheet_name in doc.summary_stats:
                    all_stats[key] = doc.summary_stats[sheet_name]
        # CSV
        elif hasattr(doc, "data") and hasattr(doc.data, "select_dtypes"):
            all_dataframes[doc.filename] = doc.data
            if doc.summary_stats:
                all_stats[doc.filename] = doc.summary_stats

    if not all_dataframes:
        return None

    charts = []

    # 1. File overview bar chart
    file_sizes = {
        name: len(df) for name, df in all_dataframes.items()
    }
    if file_sizes:
        fig = px.bar(
            x=list(file_sizes.keys()),
            y=list(file_sizes.values()),
            title="Rows per Data Source",
            labels={"x": "Source", "y": "Row Count"},
            color_discrete_sequence=["#1A237E"],
        )
        fig.update_layout(height=350, margin=dict(t=40, b=80))
        charts.append(fig.to_html(full_html=False, include_plotlyjs=False))

    # 2. Numeric column distributions
    for source_name, df in all_dataframes.items():
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        if not numeric_cols:
            continue

        # Box plot of numeric columns
        melted = df[numeric_cols].melt(var_name="Column", value_name="Value")
        melted = melted.dropna()
        if len(melted) > 0:
            fig = px.box(
                melted,
                x="Column",
                y="Value",
                title=f"Distribution: {source_name}",
                color_discrete_sequence=["#4CAF50"],
            )
            fig.update_layout(height=350, margin=dict(t=40, b=60))
            charts.append(fig.to_html(full_html=False, include_plotlyjs=False))

        # Correlation heatmap (if 2+ numeric cols)
        if len(numeric_cols) >= 2:
            corr = df[numeric_cols].corr()
            fig = px.imshow(
                corr,
                title=f"Correlation: {source_name}",
                color_continuous_scale="RdBu_r",
                aspect="auto",
                text_auto=".2f",
            )
            fig.update_layout(height=400, margin=dict(t=40, b=40))
            charts.append(fig.to_html(full_html=False, include_plotlyjs=False))

    # 3. Time series detection and plotting
    for source_name, df in all_dataframes.items():
        date_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()
        # Also check for columns that look like dates
        for col in df.columns:
            if any(kw in str(col).lower() for kw in ["date", "year", "month", "time", "period"]):
                try:
                    df[col] = pd.to_datetime(df[col], format="mixed", errors="coerce")
                    if df[col].notna().sum() > 2:
                        date_cols.append(col)
                except Exception:
                    pass

        if date_cols:
            date_col = date_cols[0]
            numeric_cols = df.select_dtypes(include="number").columns.tolist()[:5]
            if numeric_cols:
                fig = px.line(
                    df.sort_values(date_col),
                    x=date_col,
                    y=numeric_cols,
                    title=f"Trends Over Time: {source_name}",
                )
                fig.update_layout(height=400, margin=dict(t=40, b=60))
                charts.append(fig.to_html(full_html=False, include_plotlyjs=False))

    if not charts:
        return None

    # Assemble HTML
    html_parts = [
        '<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>',
        '<div style="font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto;">',
        f'<h2>Data Dashboard — {len(all_dataframes)} sources</h2>',
        f'<p style="color: #666;">Generated {datetime.now().strftime("%B %d, %Y %I:%M %p")}</p>',
    ]

    for chart_html in charts:
        html_parts.append(f'<div style="margin-bottom: 20px;">{chart_html}</div>')

    # Summary stats table
    if all_stats:
        html_parts.append("<h3>Summary Statistics</h3>")
        for source_name, stats in all_stats.items():
            html_parts.append(f"<h4>{source_name}</h4>")
            rows = []
            for col, s in stats.items():
                rows.append(s | {"column": col})
            if rows:
                stats_df = pd.DataFrame(rows)
                stats_df = stats_df.set_index("column")
                html_parts.append(stats_df.to_html(classes="stats-table", float_format=",.2f"))

    html_parts.append("</div>")
    return "\n".join(html_parts)


def create_comparison_chart(
    parsed_docs: list,
    metric_columns: list[str] | None = None,
) -> str | None:
    """Create a comparison chart across documents (e.g., YoY financials).

    Returns HTML with Plotly chart or None.
    """
    all_data = {}
    for doc in parsed_docs:
        if hasattr(doc, "sheets"):
            for sheet_name, df in doc.sheets.items():
                all_data[f"{doc.filename}/{sheet_name}"] = df
        elif hasattr(doc, "data") and hasattr(doc.data, "select_dtypes"):
            all_data[doc.filename] = doc.data

    if not all_data:
        return None

    # Try to find common numeric columns across sources
    all_numeric = {}
    for name, df in all_data.items():
        for col in df.select_dtypes(include="number").columns:
            if col not in all_numeric:
                all_numeric[col] = {}
            all_numeric[col][name] = df[col].sum()

    if not all_numeric:
        return None

    # Filter to requested metrics or top 10
    if metric_columns:
        all_numeric = {k: v for k, v in all_numeric.items() if k in metric_columns}
    else:
        all_numeric = dict(list(all_numeric.items())[:10])

    # Build grouped bar chart
    fig = go.Figure()
    sources = sorted(set(s for metrics in all_numeric.values() for s in metrics.keys()))

    for source in sources:
        values = [all_numeric[metric].get(source, 0) for metric in all_numeric.keys()]
        fig.add_trace(go.Bar(name=source, x=list(all_numeric.keys()), y=values))

    fig.update_layout(
        title="Cross-Document Metric Comparison",
        barmode="group",
        height=450,
        margin=dict(t=40, b=80),
    )

    return (
        '<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>'
        + fig.to_html(full_html=False, include_plotlyjs=False)
    )
