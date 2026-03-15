"""DocAI configuration — loads settings from .env file."""

from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()

# Supported providers and their models
PROVIDERS = {
    "openai": {
        "models": ["gpt-4o", "gpt-4.1-mini", "gpt-5-mini", "o3-mini"],
        "base_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
    },
    "anthropic": {
        "models": ["claude-sonnet-4-6", "claude-haiku-4-5", "claude-opus-4-6"],
        "base_url": "https://api.anthropic.com/v1",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "google": {
        "models": ["gemini-2.5-pro", "gemini-2.5-flash"],
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "env_key": "GOOGLE_API_KEY",
    },
}

# Flat list of all available models
AVAILABLE_MODELS = []
for provider_info in PROVIDERS.values():
    AVAILABLE_MODELS.extend(provider_info["models"])

EMBEDDING_MODEL = "text-embedding-ada-002"

# Estimated cost per 1K tokens (input/output)
MODEL_PRICING = {
    "gpt-4o":              {"input": 0.0025, "output": 0.0100},
    "gpt-5-mini":          {"input": 0.0015, "output": 0.0060},
    "gpt-4.1-mini":        {"input": 0.0004, "output": 0.0016},
    "o3-mini":             {"input": 0.0011, "output": 0.0044},
    "claude-sonnet-4-6":   {"input": 0.0030, "output": 0.0150},
    "claude-haiku-4-5":    {"input": 0.0008, "output": 0.0040},
    "claude-opus-4-6":     {"input": 0.0150, "output": 0.0750},
    "gemini-2.5-pro":      {"input": 0.0012, "output": 0.0050},
    "gemini-2.5-flash":    {"input": 0.0002, "output": 0.0010},
}


def get_provider_for_model(model: str) -> dict | None:
    """Return provider config dict for a given model name."""
    for provider_name, provider_info in PROVIDERS.items():
        if model in provider_info["models"]:
            return {
                "name": provider_name,
                "base_url": provider_info["base_url"],
                "env_key": provider_info["env_key"],
            }
    return None


def estimate_cost(model: str, input_tokens: int, output_tokens: int = 4096) -> float:
    """Estimate API cost in USD for a given model and token count."""
    pricing = MODEL_PRICING.get(model, {"input": 0.003, "output": 0.015})
    return (input_tokens / 1000 * pricing["input"]) + (output_tokens / 1000 * pricing["output"])


@dataclass
class Settings:
    api_key: str
    base_url: str
    default_model: str
    embedding_model: str
    max_context_tokens: int
    chroma_persist_dir: str

    @classmethod
    def from_env(cls) -> "Settings":
        # Determine default model and provider
        default_model = os.getenv("DOCAI_MODEL", "gpt-4o")
        provider = get_provider_for_model(default_model)

        # Try to find an API key — check provider-specific, then generic fallback
        api_key = ""
        if provider:
            api_key = os.getenv(provider["env_key"], "")
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")

        base_url = provider["base_url"] if provider else "https://api.openai.com/v1"

        return cls(
            api_key=api_key,
            base_url=base_url,
            default_model=default_model,
            embedding_model=os.getenv("DOCAI_EMBEDDING_MODEL", EMBEDDING_MODEL),
            max_context_tokens=int(os.getenv("DOCAI_MAX_TOKENS", "100000")),
            chroma_persist_dir=os.getenv("DOCAI_CHROMA_DIR", "./.chroma_db"),
        )

    def require_api_key(self):
        """Validate API key is set. Call before LLM operations."""
        if not self.api_key:
            raise ValueError(
                "No API key configured. Set one of: OPENAI_API_KEY, "
                "ANTHROPIC_API_KEY, or GOOGLE_API_KEY in your .env file."
            )


settings = Settings.from_env()
