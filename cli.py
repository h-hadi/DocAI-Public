#!/usr/bin/env python3
"""DocAI — CLI for running document analysis pipelines.

Usage:
    python cli.py /path/to/folder --pipeline year_over_year
    python cli.py /path/to/folder --pipeline pta "Focus on expense anomalies"
    python cli.py /path/to/folder --pipeline summarizer --model gpt-4o
    python cli.py /path/to/folder --pipeline donor_intent --output report.md
    python cli.py --list-pipelines
"""

import argparse
import sys
import io
from pathlib import Path

# Fix Windows console encoding for Unicode output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from pipelines import PIPELINES, PIPELINE_LABELS
from config import AVAILABLE_MODELS, estimate_cost
from history import log_run


def cmd_analyze(args):
    """Run a pipeline on a folder."""
    pipeline_cls = PIPELINES.get(args.pipeline)
    if not pipeline_cls:
        print(f"Error: Unknown pipeline '{args.pipeline}'", file=sys.stderr)
        print(f"Available: {', '.join(PIPELINES.keys())}", file=sys.stderr)
        sys.exit(1)

    folder = Path(args.folder)
    if not folder.exists():
        print(f"Error: Folder not found: {folder}", file=sys.stderr)
        sys.exit(1)

    pipeline = pipeline_cls()
    print(f"\n[DocAI] Running {PIPELINE_LABELS.get(args.pipeline, args.pipeline)}")
    print(f"[DocAI] Folder: {folder}")
    if args.instruction:
        print(f"[DocAI] Instruction: {args.instruction}")
    print()

    result = pipeline.execute(str(folder), args.instruction or "", args.model)

    if result.errors:
        print(f"Warnings ({len(result.errors)}):", file=sys.stderr)
        for err in result.errors:
            print(f"  - {err}", file=sys.stderr)
        print()

    if args.output:
        Path(args.output).write_text(result.output, encoding="utf-8")
        print(f"Report saved to {args.output}")
    else:
        print(result.output)

    # Cost estimation and history logging
    input_tokens = result.metadata.get("total_tokens", 0)
    model_used = args.model or "gpt-4o"
    est_cost = estimate_cost(model_used, input_tokens)

    log_run(
        folder_path=str(folder),
        pipeline=args.pipeline,
        model=model_used,
        instruction=args.instruction or "",
        files_processed=result.files_processed,
        input_tokens=input_tokens,
        success=result.success,
        errors=result.errors,
    )

    print(f"\n[DocAI] Files processed: {result.files_processed}")
    print(f"[DocAI] Input tokens: {input_tokens:,}")
    print(f"[DocAI] Est. cost: ${est_cost:.4f}")
    if result.metadata:
        for k, v in result.metadata.items():
            if k != "total_tokens":
                print(f"[DocAI] {k}: {v}")


def cmd_list_pipelines(args):
    """List available pipelines."""
    print("\nAvailable Pipelines:\n")
    for key, label in PIPELINE_LABELS.items():
        pipeline_cls = PIPELINES[key]
        p = pipeline_cls()
        accepted = ", ".join(t.value for t in p.accepted_types)
        print(f"  {key:20s} {label}")
        print(f"  {'':20s} {p.description}")
        print(f"  {'':20s} Accepts: {accepted}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="DocAI — Local Document Analysis Pipelines",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("folder", nargs="?", type=str, help="Path to document folder")
    parser.add_argument("instruction", nargs="?", default="", help="Analysis instruction")
    parser.add_argument(
        "--pipeline", "-p",
        choices=list(PIPELINES.keys()),
        help="Pipeline to run",
    )
    parser.add_argument(
        "--model", "-m",
        default=None,
        choices=AVAILABLE_MODELS,
        help="LLM model to use",
    )
    parser.add_argument("--output", "-o", type=str, help="Save output to file")
    parser.add_argument(
        "--list-pipelines",
        action="store_true",
        help="List available pipelines",
    )

    args = parser.parse_args()

    if args.list_pipelines:
        cmd_list_pipelines(args)
    elif args.folder and args.pipeline:
        cmd_analyze(args)
    else:
        parser.print_help()
        print("\nExamples:")
        print('  python cli.py ./test_data --pipeline year_over_year')
        print('  python cli.py ./test_data --pipeline pta')
        print('  python cli.py ./test_data --pipeline summarizer')
        print('  python cli.py --list-pipelines')
        sys.exit(1)


if __name__ == "__main__":
    main()
