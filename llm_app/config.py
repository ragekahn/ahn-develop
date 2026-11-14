"""Configuration loading for the LLM app.

Reads provider / model / credentials from environment variables (optionally
loaded from a local `.env` file via python-dotenv).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

try:  # python-dotenv is optional at runtime but recommended.
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - only if dotenv is not installed
    pass

SUPPORTED_PROVIDERS = ("openai", "anthropic", "ollama")


@dataclass
class LLMConfig:
    provider: str
    model: str
    api_key: str
    temperature: float = 0.7
    max_tokens: int = 1024
    base_url: Optional[str] = None  # for OpenAI-compatible local endpoints (e.g. Ollama)


def load_config() -> LLMConfig:
    """Build an :class:`LLMConfig` from environment variables.

    Recognised variables:
      LLM_PROVIDER      "openai" (default), "anthropic", or "ollama"
      OPENAI_API_KEY    key for OpenAI
      ANTHROPIC_API_KEY key for Anthropic
      OPENAI_MODEL      default "gpt-4o-mini"
      ANTHROPIC_MODEL   default "claude-sonnet-4-20250514"
      OLLAMA_MODEL      default "llama3"
      OLLAMA_BASE_URL   default "http://localhost:11434/v1"
      LLM_TEMPERATURE   default 0.7
      LLM_MAX_TOKENS    default 1024
    """
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{provider}'. "
            f"Use one of: {', '.join(SUPPORTED_PROVIDERS)}."
        )

    base_url: Optional[str] = None

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    else:  # ollama
        api_key = "ollama"  # local; any non-empty string works
        model = os.getenv("OLLAMA_MODEL", "llama3")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

    return LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1024")),
        base_url=base_url,
    )
