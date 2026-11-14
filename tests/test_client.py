"""Unit tests for llm_app.client (no network; SDKs are mocked)."""
from unittest import mock

import pytest

from llm_app import LLMClient, LLMError
from llm_app.config import LLMConfig


def _config(provider: str) -> LLMConfig:
    return LLMConfig(
        provider=provider,
        model="test-model",
        api_key="dummy",
        temperature=0.1,
        max_tokens=64,
    )


def test_openai_chat_returns_content():
    fake_msg = mock.Mock()
    fake_msg.content = "Hello from OpenAI"
    fake_choice = mock.Mock()
    fake_choice.message = fake_msg
    fake_resp = mock.Mock()
    fake_resp.choices = [fake_choice]

    sdk = mock.Mock()
    sdk.chat.completions.create.return_value = fake_resp

    client = LLMClient(config=_config("openai"), client=sdk)
    assert client.chat([{"role": "user", "content": "hi"}], system="be brief") == "Hello from OpenAI"

    # The system prompt should be prepended to the message list.
    call = sdk.chat.completions.create.call_args.kwargs
    assert call["messages"][0] == {"role": "system", "content": "be brief"}


def test_anthropic_chat_returns_text():
    block = mock.Mock()
    block.type = "text"
    block.text = "Hello from Anthropic"
    fake_resp = mock.Mock()
    fake_resp.content = [block]

    sdk = mock.Mock()
    sdk.messages.create.return_value = fake_resp

    client = LLMClient(config=_config("anthropic"), client=sdk)
    assert client.chat([{"role": "user", "content": "hi"}], system="be brief") == "Hello from Anthropic"

    # Anthropic keeps `system` as a top-level field, not inside messages.
    call = sdk.messages.create.call_args.kwargs
    assert call["system"] == "be brief"
    assert all(m["role"] != "system" for m in call["messages"])


def test_missing_api_key_raises():
    bad = LLMConfig(provider="openai", model="x", api_key="")
    with pytest.raises(LLMError):
        LLMClient(config=bad)


def test_unsupported_provider_raises():
    with pytest.raises(LLMError):
        LLMClient(config=LLMConfig(provider="google", model="x", api_key="k"))


def test_ollama_chat_returns_content():
    """Ollama uses the OpenAI-compatible API, so it shares the openai path."""
    fake_msg = mock.Mock()
    fake_msg.content = "Hello from Ollama (llama3)"
    fake_choice = mock.Mock()
    fake_choice.message = fake_msg
    fake_resp = mock.Mock()
    fake_resp.choices = [fake_choice]

    sdk = mock.Mock()
    sdk.chat.completions.create.return_value = fake_resp

    cfg = LLMConfig(
        provider="ollama",
        model="llama3",
        api_key="ollama",
        temperature=0.1,
        max_tokens=64,
        base_url="http://localhost:11434/v1",
    )
    client = LLMClient(config=cfg, client=sdk)
    result = client.chat([{"role": "user", "content": "hi"}], system="be brief")
    assert result == "Hello from Ollama (llama3)"

    # Verify the OpenAI-style chat.completions.create was used.
    call = sdk.chat.completions.create.call_args.kwargs
    assert call["model"] == "llama3"
    assert call["messages"][0] == {"role": "system", "content": "be brief"}


def test_ollama_builds_openai_client_with_base_url():
    """Ollama must construct an OpenAI SDK instance with the local base_url."""
    cfg = LLMConfig(
        provider="ollama",
        model="llama3",
        api_key="ollama",
        temperature=0.1,
        max_tokens=64,
        base_url="http://localhost:11434/v1",
    )
    from openai import OpenAI
    client = LLMClient(config=cfg)
    assert isinstance(client._client, OpenAI)
    assert client._client.base_url is not None
    assert "11434" in str(client._client.base_url)


def test_ollama_config_from_env(monkeypatch):
    """load_config() should return a valid ollama config when env vars are set."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "mistral")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

    from llm_app.config import load_config
    cfg = load_config()
    assert cfg.provider == "ollama"
    assert cfg.model == "mistral"
    assert cfg.api_key == "ollama"
    assert cfg.base_url == "http://localhost:11434/v1"
