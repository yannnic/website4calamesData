"""
OpenAI-compatible LLM client for natural-language search and result summarization.

The LLM is configured by the client (page Paramètres of the frontend): base URL,
API key and model are sent with each request (headers X-LLM-Base-Url,
X-LLM-Api-Key, X-LLM-Model). Any OpenAI-compatible API works (OpenAI, Mistral,
Ollama…).

Without client settings, the server's environment applies (NL_LLM_BASE_URL,
NL_LLM_API_KEY, NL_LLM_MODEL; optional). Client settings are never mixed with
the server's: a client-chosen URL never receives the server's key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL    = "gpt-4o-mini"

NL_LLM_BASE_URL = os.getenv("NL_LLM_BASE_URL") or DEFAULT_BASE_URL
NL_LLM_API_KEY  = os.getenv("NL_LLM_API_KEY", "")
NL_LLM_MODEL    = os.getenv("NL_LLM_MODEL") or DEFAULT_MODEL

_PROMPT_DIR = Path(__file__).parent


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    source: str     # "client" or "server"

    @property
    def enabled(self) -> bool:
        # A local server (Ollama…) chosen by the client may need no key.
        return bool(self.api_key) or (self.source == "client" and self.base_url != DEFAULT_BASE_URL)


def llm_config(base_url: str = "", api_key: str = "", model: str = "") -> LLMConfig:
    """Client settings if any were sent, otherwise the server's environment."""
    if base_url or api_key or model:
        return LLMConfig(base_url or DEFAULT_BASE_URL, api_key, model or DEFAULT_MODEL, "client")
    return LLMConfig(NL_LLM_BASE_URL, NL_LLM_API_KEY, NL_LLM_MODEL, "server")


NOT_CONFIGURED = "LLM non configuré : renseignez-le dans la page Paramètres."


def load_nl_prompt() -> str:
    """Return the NL search system prompt, preferring the live (startup-generated) version."""
    live = _PROMPT_DIR / "nl_prompt_live.txt"
    base = _PROMPT_DIR / "nl_prompt.txt"
    return (live if live.exists() else base).read_text(encoding="utf-8").strip()


def load_summarize_prompt() -> str:
    """Return the summarization system prompt."""
    return (_PROMPT_DIR / "summarize_prompt.txt").read_text(encoding="utf-8").strip()


def call_llm(
    config: LLMConfig,
    system: str,
    user: str,
    max_tokens: int = 400,
    temperature: float = 0,
) -> str:
    """
    Send a chat completion request to the configured LLM and return the raw text.

    Expects a JSON response (response_format="json_object").
    Raises RuntimeError if the LLM is not configured, or re-raises API errors.
    """
    if not config.enabled:
        raise RuntimeError(NOT_CONFIGURED)
    import openai
    client = openai.OpenAI(base_url=config.base_url, api_key=config.api_key or "sans-cle", timeout=60)
    resp = client.chat.completions.create(
        model=config.model,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return resp.choices[0].message.content
