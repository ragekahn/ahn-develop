"""Unified chat client for OpenAI and Anthropic.

Exposes a single ``chat()`` method so the rest of your app does not need to
know which provider is configured.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .config import LLMConfig, load_config


class LLMError(RuntimeError):
    """Raised when the client cannot be created or a call fails."""


# A single chat message: {"role": "user" | "assistant" | "system", "content": "..."}
Message = Dict[str, str]


class LLMClient:
    """Small wrapper around the OpenAI / Anthropic chat-completion APIs.

    Example:
        >>> from llm_app import LLMClient
        >>> client = LLMClient()
        >>> print(client.chat([{"role": "user", "content": "Hi!"}], system="Be brief."))
    """

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        client: Optional[object] = None,
    ) -> None:
        self.config = config or load_config()
        if not self.config.api_key:
            raise LLMError(
                f"Missing API key for provider '{self.config.provider}'. "
                "Copy .env.example to .env and set the matching *_API_KEY."
            )
        # ``client`` allows dependency injection (handy for tests / custom SDKs).
        self._client = client if client is not None else self._build_client()

    def _build_client(self):
        if self.config.provider in ("openai", "ollama"):
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover
                raise LLMError("The 'openai' package is required. Install it: pip install openai") from exc
            kwargs: dict = {"api_key": self.config.api_key}
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            return OpenAI(**kwargs)

        if self.config.provider == "anthropic":
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover
                raise LLMError("The 'anthropic' package is required. Install it: pip install anthropic") from exc
            return anthropic.Anthropic(api_key=self.config.api_key)

        raise LLMError(f"Unsupported provider: {self.config.provider}")

    def chat(
        self,
        messages: List[Message],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Send a chat request and return the assistant's text response.

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts.
            system: Optional system prompt (handled per-provider).
            temperature: Override the configured temperature.
            max_tokens: Override the configured max_tokens.
        """
        temperature = self.config.temperature if temperature is None else temperature
        max_tokens = self.config.max_tokens if max_tokens is None else max_tokens

        if self.config.provider in ("openai", "ollama"):
            return self._chat_openai(messages, system, temperature, max_tokens)
        return self._chat_anthropic(messages, system, temperature, max_tokens)

    # ---- provider-specific helpers ----

    def _chat_openai(self, messages, system, temperature, max_tokens) -> str:
        msgs: List[Message] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)

        resp = self._client.chat.completions.create(
            model=self.config.model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    def _chat_anthropic(self, messages, system, temperature, max_tokens) -> str:
        # Anthropic keeps the system prompt as a separate top-level field.
        msgs = [m for m in messages if m.get("role") != "system"]
        system_prompt = system
        if system_prompt is None:
            for m in messages:
                if m.get("role") == "system":
                    system_prompt = m["content"]
                    break

        kwargs = {
            "model": self.config.model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        resp = self._client.messages.create(**kwargs)
        return "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
