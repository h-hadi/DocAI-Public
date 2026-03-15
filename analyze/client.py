"""LLM client — multi-provider support via OpenAI-compatible API."""

from openai import OpenAI, APIConnectionError, AuthenticationError, RateLimitError, APIStatusError
from config import settings, get_provider_for_model


def get_client(model: str | None = None) -> OpenAI:
    """Create OpenAI-compatible client for the given model's provider."""
    settings.require_api_key()
    model = model or settings.default_model
    provider = get_provider_for_model(model)

    if provider:
        import os
        api_key = os.getenv(provider["env_key"], "") or settings.api_key
        base_url = provider["base_url"]
    else:
        api_key = settings.api_key
        base_url = settings.base_url

    return OpenAI(api_key=api_key, base_url=base_url)


def call_llm(
    prompt: str,
    system_prompt: str = "",
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> str:
    """Send prompt to the appropriate provider, return response text.

    Automatically routes to the correct API endpoint based on model name.
    Supports OpenAI, Anthropic (Claude), and Google (Gemini) models.

    Args:
        prompt: User message content.
        system_prompt: Optional system message.
        model: Override the default model.
        temperature: Sampling temperature (lower = more deterministic).
        max_tokens: Maximum response length.

    Returns:
        The LLM's response text.

    Raises:
        Exception: On API errors (rate limit, auth, etc.)
    """
    model = model or settings.default_model
    client = get_client(model)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    except AuthenticationError:
        provider = get_provider_for_model(model)
        key_name = provider["env_key"] if provider else "API_KEY"
        raise Exception(
            f"Authentication failed for model '{model}'. "
            f"Check your {key_name} in .env."
        )
    except APIConnectionError as e:
        raise Exception(
            f"Connection error. Verify your API key and network. Detail: {e}"
        )
    except RateLimitError:
        raise Exception(
            "Rate limit exceeded. Wait a moment and try again."
        )
    except APIStatusError as e:
        raise Exception(
            f"API error (HTTP {e.status_code}): {e.message}"
        )
