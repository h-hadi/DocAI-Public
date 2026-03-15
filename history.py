"""Project history — tracks all analysis runs with cost estimates."""

import json
from datetime import datetime
from pathlib import Path
from config import estimate_cost

HISTORY_FILE = Path(__file__).parent / "project_history.json"


def _load_history() -> list[dict]:
    """Load history from disk."""
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_history(records: list[dict]):
    """Save history to disk."""
    HISTORY_FILE.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def log_run(
    folder_path: str,
    pipeline: str,
    model: str,
    instruction: str,
    files_processed: int,
    input_tokens: int,
    success: bool,
    errors: list[str] | None = None,
) -> dict:
    """Log an analysis run and return the record."""
    est_cost = estimate_cost(model, input_tokens)

    record = {
        "timestamp": datetime.now().isoformat(),
        "folder": folder_path,
        "pipeline": pipeline,
        "model": model,
        "instruction": instruction[:200],  # truncate long instructions
        "files_processed": files_processed,
        "input_tokens": input_tokens,
        "estimated_cost_usd": round(est_cost, 4),
        "success": success,
        "errors": (errors or [])[:5],  # keep max 5 errors
    }

    records = _load_history()
    records.append(record)
    _save_history(records)

    return record


def get_history() -> list[dict]:
    """Get all history records, newest first."""
    return list(reversed(_load_history()))


def get_spending_summary() -> dict:
    """Get cumulative spending summary."""
    records = _load_history()

    total_cost = sum(r.get("estimated_cost_usd", 0) for r in records)
    total_runs = len(records)
    total_tokens = sum(r.get("input_tokens", 0) for r in records)
    successful = sum(1 for r in records if r.get("success"))
    total_files = sum(r.get("files_processed", 0) for r in records)
    total_errors = sum(len(r.get("errors", [])) for r in records)

    # Per-model breakdown
    by_model = {}
    for r in records:
        m = r.get("model", "unknown")
        if m not in by_model:
            by_model[m] = {"runs": 0, "tokens": 0, "cost": 0.0}
        by_model[m]["runs"] += 1
        by_model[m]["tokens"] += r.get("input_tokens", 0)
        by_model[m]["cost"] += r.get("estimated_cost_usd", 0)

    # Per-pipeline breakdown
    by_pipeline = {}
    for r in records:
        p = r.get("pipeline", "unknown")
        if p not in by_pipeline:
            by_pipeline[p] = {"runs": 0, "tokens": 0, "cost": 0.0}
        by_pipeline[p]["runs"] += 1
        by_pipeline[p]["tokens"] += r.get("input_tokens", 0)
        by_pipeline[p]["cost"] += r.get("estimated_cost_usd", 0)

    # Spending over time (by date)
    by_date = {}
    for r in records:
        date = r.get("timestamp", "")[:10]
        if date not in by_date:
            by_date[date] = 0.0
        by_date[date] += r.get("estimated_cost_usd", 0)

    return {
        "total_runs": total_runs,
        "successful_runs": successful,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 4),
        "total_files": total_files,
        "total_errors": total_errors,
        "by_model": by_model,
        "by_pipeline": by_pipeline,
        "by_date": by_date,
    }


def get_error_log() -> list[dict]:
    """Get all errors from history, newest first."""
    errors = []
    for r in reversed(_load_history()):
        for err in r.get("errors", []):
            errors.append({
                "timestamp": r.get("timestamp", ""),
                "pipeline": r.get("pipeline", ""),
                "model": r.get("model", ""),
                "error": err,
            })
            if len(errors) >= 100:
                return errors
    return errors


def get_aggregate_stats() -> dict:
    """Get aggregate stats for dashboard: total files, total errors."""
    records = _load_history()
    total_files = sum(r.get("files_processed", 0) for r in records)
    total_errors = sum(len(r.get("errors", [])) for r in records)
    return {"total_files": total_files, "total_errors": total_errors}


def clear_history():
    """Clear all history."""
    _save_history([])
