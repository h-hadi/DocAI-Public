"""Output formatter — structures LLM results into Markdown or JSON."""

import json
from dataclasses import asdict


def format_output(
    llm_response: str,
    fmt: str = "markdown",
    chunk_result=None,
) -> str:
    """Format the LLM response for display.

    Args:
        llm_response: Raw text from the LLM.
        fmt: Output format — 'markdown' or 'json'.
        chunk_result: Optional ChunkResult for metadata.

    Returns:
        Formatted output string.
    """
    if fmt == "json":
        output = {
            "analysis": llm_response,
            "metadata": {},
        }
        if chunk_result:
            output["metadata"] = {
                "total_tokens": chunk_result.total_tokens,
                "strategy": "single-shot" if chunk_result.fits_single_shot else "map-reduce",
                "documents": [
                    {"source": c.source, "tokens": c.tokens}
                    for c in chunk_result.chunks
                ],
            }
        return json.dumps(output, indent=2, ensure_ascii=False)

    # Markdown format (default)
    parts = []

    # Add metadata header
    if chunk_result:
        strategy = "single-shot" if chunk_result.fits_single_shot else "map-reduce"
        parts.append(f"*Analyzed {len(chunk_result.chunks)} documents "
                     f"({chunk_result.total_tokens:,} tokens, {strategy} strategy)*\n")

    parts.append(llm_response)

    return "\n".join(parts)
