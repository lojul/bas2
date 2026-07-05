"""Shared LLM helper — Azure OpenAI (primary) with OpenRouter fallback."""

import logging
import os
import time
from typing import Generator

logger = logging.getLogger(__name__)


def openrouter_chat(
    prompt: str,
    model: str = "qwen/qwen-2.5-72b-instruct",
    fallback_model: str = "deepseek/deepseek-chat",
    max_tokens: int = 1000,
    temperature: float = 0.0,
) -> dict:
    """OpenRouter chat call hardened against provider flakiness.

    OpenRouter intermittently returns 400/502/504 or empty responses when an
    upstream provider hiccups (three separate incidents 2026-07-04/05 degraded
    pipeline runs to UNKNOWN). Strategy: primary model, retry once after 2s,
    then try the fallback model before giving up.

    Returns the raw response JSON (callers read choices[0].message.content).
    Raises the last error if all three attempts fail.
    """
    import httpx

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    attempts = [(model, 0), (model, 2), (fallback_model, 2)]
    last_err: Exception | None = None

    for attempt_model, delay in attempts:
        if delay:
            time.sleep(delay)
        try:
            with httpx.Client(timeout=45) as client:
                resp = client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": attempt_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
            if not content:
                raise ValueError(f"Empty response from {attempt_model}")
            return data
        except Exception as e:
            last_err = e
            logger.warning("openrouter_chat: %s failed (%s) — %s", attempt_model, type(e).__name__, str(e)[:120])

    raise last_err  # all attempts exhausted


def azure_openai_available() -> bool:
    return bool(os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_KEY"))


def _get_azure_client():
    from openai import AzureOpenAI
    return AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_KEY"],
        api_version="2025-01-01-preview",
    )


def _deployment() -> str:
    return os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-5-mini")


def _record_usage(response) -> None:
    try:
        from langsmith.run_helpers import get_current_run_tree
        run_tree = get_current_run_tree()
        if run_tree and response.usage:
            run_tree.extra = run_tree.extra or {}
            run_tree.extra["usage_metadata"] = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
    except Exception:
        pass


def chat_complete(
    messages: list[dict],
    max_tokens: int = 2000,
    temperature: float = 0.5,
    fallback_model: str = "deepseek/deepseek-chat",
) -> str:
    """Azure OpenAI when configured, else OpenRouter fallback.

    Args:
        fallback_model: OpenRouter model to use when Azure is not configured.
    """
    if azure_openai_available():
        client = _get_azure_client()
        response = client.chat.completions.create(
            model=_deployment(),
            messages=messages,
            max_completion_tokens=max_tokens,
        )
        _record_usage(response)
        return response.choices[0].message.content

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("Neither AZURE_OPENAI_ENDPOINT/KEY nor OPENROUTER_API_KEY are configured")
    import httpx
    resp = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": fallback_model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def chat_complete_stream(messages: list[dict], max_tokens: int = 2000, temperature: float = 0.5) -> Generator[str, None, None]:
    """Call Azure OpenAI with streaming. Yields text chunks."""
    client = _get_azure_client()
    response = client.chat.completions.create(
        model=_deployment(),
        messages=messages,
        max_completion_tokens=max_tokens,
        stream=True,
    )
    for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
