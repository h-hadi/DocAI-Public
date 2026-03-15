"""Execution strategies — single-shot vs map-reduce, with vector store context."""

from analyze.client import call_llm
from analyze.prompts import SYSTEM_PROMPT, select_template
from vectorstore.store import query_similar


def _get_vector_context(folder_path: str, instruction: str) -> str:
    """Retrieve relevant context from vector store if available."""
    try:
        matches = query_similar(folder_path, instruction, n_results=3)
        if matches:
            parts = []
            for m in matches:
                parts.append(f"[From {m['source']}]:\n{m['content'][:500]}")
            return "\n\n".join(parts)
    except Exception:
        pass
    return "(No prior context available)"


def single_shot(
    chunks: list,
    instruction: str,
    folder_path: str = "",
    model: str | None = None,
) -> str:
    """All content fits in one prompt — send everything at once."""
    content = "\n\n---\n\n".join(c.content for c in chunks)
    context = _get_vector_context(folder_path, instruction)
    template = select_template(instruction)
    prompt = template.format(
        content=content, instruction=instruction, context=context
    )
    return call_llm(prompt, system_prompt=SYSTEM_PROMPT, model=model)


def map_reduce(
    chunks: list,
    instruction: str,
    folder_path: str = "",
    model: str | None = None,
) -> str:
    """Content too large — summarize each doc individually, then synthesize."""
    # MAP phase: summarize each document
    summaries = []
    for chunk in chunks:
        map_prompt = (
            f"Summarize this document, preserving ALL key data points, "
            f"numbers, dates, and facts relevant to this analysis task:\n"
            f"{instruction}\n\n"
            f"Document:\n{chunk.content}"
        )
        summary = call_llm(map_prompt, system_prompt=SYSTEM_PROMPT, model=model)
        summaries.append(f"## Summary of {chunk.source}\n{summary}")

    # REDUCE phase: synthesize all summaries with vector context
    combined = "\n\n---\n\n".join(summaries)
    context = _get_vector_context(folder_path, instruction)
    template = select_template(instruction)
    prompt = template.format(
        content=combined, instruction=instruction, context=context
    )
    return call_llm(prompt, system_prompt=SYSTEM_PROMPT, model=model)


def execute(
    chunk_result,
    instruction: str,
    folder_path: str = "",
    model: str | None = None,
) -> str:
    """Choose and run the appropriate strategy."""
    if chunk_result.fits_single_shot:
        return single_shot(
            chunk_result.chunks, instruction, folder_path, model
        )
    else:
        return map_reduce(
            chunk_result.chunks, instruction, folder_path, model
        )
