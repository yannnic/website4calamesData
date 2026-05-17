"""
OpenAI-compatible LLM client for natural-language search and result summarization.

Provider is configurable via environment variables — switching from OpenAI to
Ollama, Mistral, or any other OpenAI-compatible API requires only changing
NL_LLM_BASE_URL, NL_LLM_API_KEY, and NL_LLM_MODEL.
"""

from __future__ import annotations

import os
from pathlib import Path

NL_LLM_BASE_URL = os.getenv("NL_LLM_BASE_URL", "https://api.openai.com/v1")
NL_LLM_API_KEY  = os.getenv("NL_LLM_API_KEY", "")
NL_LLM_MODEL    = os.getenv("NL_LLM_MODEL", "gpt-4o-mini")

_PROMPT_DIR = Path(__file__).parent


def load_nl_prompt() -> str:
    """Return the NL search system prompt, preferring the live (startup-generated) version."""
    live = _PROMPT_DIR / "nl_prompt_live.txt"
    base = _PROMPT_DIR / "nl_prompt.txt"
    return (live if live.exists() else base).read_text(encoding="utf-8").strip()


def load_summarize_prompt() -> str:
    """Return the summarization system prompt."""
    return (_PROMPT_DIR / "summarize_prompt.txt").read_text(encoding="utf-8").strip()


def call_llm(
    system: str,
    user: str,
    max_tokens: int = 400,
    temperature: float = 0,
) -> str:
    """
    Send a chat completion request to the configured LLM and return the raw text.

    Expects a JSON response (response_format="json_object").
    Raises RuntimeError if NL_LLM_API_KEY is not set, or re-raises API errors.
    """
    if not NL_LLM_API_KEY:
        raise RuntimeError("NL_LLM_API_KEY not configured")
    import openai
    client = openai.OpenAI(base_url=NL_LLM_BASE_URL, api_key=NL_LLM_API_KEY)
    resp = client.chat.completions.create(
        model=NL_LLM_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return resp.choices[0].message.content
